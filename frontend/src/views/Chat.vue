<template>
  <div class="chat-page">
    <div class="card chat-container">
      <div class="chat-header">
        <h2>AI 对话</h2>
        <div class="chat-controls">
          <label class="fast-toggle" title="跳过查询改写，直接搜索">
            <input type="checkbox" v-model="fastMode" />
            <span>⚡快速</span>
          </label>
          <select v-model="kbName">
            <option value="">全部知识库</option>
            <option v-for="kb in kbList" :key="kb" :value="kb">{{ kb }}</option>
          </select>
        </div>
      </div>

      <div class="messages" ref="msgContainer">
        <div v-if="messages.length === 0" class="empty-state">
          基于知识库文档提问，我会从文档中查找相关上下文来回答
        </div>

        <div v-for="(msg, i) in messages" :key="i" :class="['msg', msg.role]">
          <div class="msg-avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
          <div class="msg-body">
            <div class="msg-text">{{ msg.content }}</div>
            <div v-if="msg.role === 'assistant' && !msg.error && msg.content" class="msg-actions">
              <button
                v-if="!msg.saved"
                class="btn-save"
                @click="doSave(msg, i)"
              >保存到记忆</button>
              <span v-else class="saved-tag">已保存</span>
            </div>
            <div v-if="msg.error" class="msg-error">{{ msg.error }}</div>
            <div v-if="msg.sources && msg.sources.length" class="msg-sources">
              <div class="sources-title">参考来源：</div>
              <div v-for="(s, j) in msg.sources" :key="j" class="source-item">
                <span class="source-file">{{ s.filename }}</span>
                <span class="source-score">{{ (s.score * 100).toFixed(0) }}%</span>
                <p class="source-text">{{ s.text.slice(0, 200) }}{{ s.text.length > 200 ? '...' : '' }}</p>
              </div>
            </div>
          </div>
        </div>

        <div v-if="streaming" class="msg assistant">
          <div class="msg-avatar">🤖</div>
          <div class="msg-body">
            <div v-if="!firstTokenReceived" class="msg-thinking">思考中...</div>
            <div v-else class="msg-text">{{ streamingText }}<span class="cursor">|</span></div>
          </div>
        </div>
      </div>

      <form class="chat-input" @submit.prevent="send">
        <textarea
          v-model="question"
          placeholder="输入你的问题..."
          rows="2"
          :disabled="streaming"
          @keydown.enter.exact.prevent="send"
        />
        <button v-if="streaming" type="button" class="btn-stop" @click="abort">停止</button>
        <button v-else type="submit" class="btn-primary" :disabled="!question.trim()">发送</button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { getKBList, getConfig, chatStream, saveMemory } from '../api/index.js'

const kbList = ref([])
const kbName = ref('')
const question = ref('')
const fastMode = ref(false)
const messages = ref([])
const streaming = ref(false)
const streamingText = ref('')
const firstTokenReceived = ref(false)
const msgContainer = ref(null)
let abortController = null
let topK = 5

onMounted(async () => {
  try {
    const [kbRes, cfgRes] = await Promise.all([getKBList(), getConfig()])
    kbList.value = (kbRes.data?.kbs || []).map(kb => kb.name)
    topK = parseInt(cfgRes.data?.rerank_top_k) || 5
  } catch {
    kbList.value = []
  }
})

function scrollBottom() {
  nextTick(() => {
    const el = msgContainer.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function doSave(msg, i) {
  let q = msg.question
  if (q.length < 15 || !/[?？疑问吗呢]/.test(q)) {
    for (let j = i - 1; j >= 0; j--) {
      if (messages.value[j].role === 'user') { q = messages.value[j].content; break }
    }
  }
  try {
    await saveMemory(q, msg.content, kbName.value)
    msg.saved = true
  } catch {
    // silently fail — user can retry by clicking again
  }
}

function abort() {
  if (abortController) {
    abortController.abort()
    abortController = null
  }
}

async function send() {
  const q = question.value.trim()
  if (!q || streaming.value) return

  const history = messages.value.map(m => ({ role: m.role, content: m.content }))
  messages.value.push({ role: 'user', content: q })
  question.value = ''
  streaming.value = true
  streamingText.value = ''
  firstTokenReceived.value = false
  scrollBottom()

  let sources = []
  let content = ''

  abortController = new AbortController()
  const timeoutId = setTimeout(() => abortController.abort(), 300000)

  try {
    const resp = await chatStream(q, kbName.value, topK, history, abortController.signal, fastMode.value)

    if (!resp.ok) {
      throw new Error(`服务器错误 (${resp.status})`)
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let lineBuf = ''
    let eventType = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      lineBuf += decoder.decode(value, { stream: true })

      const lines = lineBuf.split('\n')
      lineBuf = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('event:')) {
          eventType = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          try {
            const payload = JSON.parse(line.slice(5).trim())
            if (eventType === 'chunk' && payload.content) {
              if (!firstTokenReceived.value) firstTokenReceived.value = true
              content += payload.content
              streamingText.value = content
              scrollBottom()
            } else if (eventType === 'sources') {
              sources = payload.items || []
            }
          } catch { /* skip unparseable line */ }
        }
      }
    }
  } catch (e) {
    if (e.name === 'AbortError') {
      content += '\n[已停止生成]'
    } else {
      content = content || `[请求失败: ${e.message}]`
    }
  } finally {
    clearTimeout(timeoutId)
    abortController = null
  }

  const isError = content.startsWith('[请求失败')
  messages.value.push({
    role: 'assistant',
    content: content || '[未收到回复]',
    sources,
    error: isError,
    question: q,
    saved: false,
  })
  streamingText.value = ''
  streaming.value = false
  firstTokenReceived.value = false
  scrollBottom()
}
</script>

<style scoped>
.chat-page { max-width: 860px; margin: 0 auto; height: 100%; }

.chat-container {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 48px);
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 16px;
}

.chat-header h2 { font-size: 18px; font-weight: 600; }

.chat-controls { display: flex; align-items: center; gap: 12px; }

.chat-controls select { width: 160px; }

.fast-toggle {
  display: flex; align-items: center; gap: 4px;
  font-size: 13px; color: var(--text-secondary); cursor: pointer;
  white-space: nowrap; user-select: none;
}

.fast-toggle input { cursor: pointer; }

.messages {
  flex: 1;
  overflow-y: auto;
  padding-right: 8px;
}

.empty-state {
  text-align: center;
  color: var(--text-secondary);
  font-size: 14px;
  margin-top: 80px;
}

.msg {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.msg-avatar { font-size: 20px; flex-shrink: 0; margin-top: 2px; }

.msg-body { min-width: 0; }

.msg-text {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.65;
}

.msg.user .msg-text {
  background: var(--primary);
  color: #fff;
  padding: 10px 14px;
  border-radius: 12px 12px 2px 12px;
  display: inline-block;
}

.msg-thinking {
  color: var(--text-secondary);
  font-style: italic;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}

.msg-error {
  margin-top: 6px;
  color: var(--danger);
  font-size: 13px;
}

.msg-actions { margin-top: 8px; }

.btn-save {
  background: none;
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 4px 12px;
  border-radius: var(--radius);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-save:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.saved-tag {
  font-size: 12px;
  color: var(--success);
}

.msg-sources {
  margin-top: 10px;
  padding: 12px;
  background: #f8fafc;
  border-radius: var(--radius);
  border: 1px solid var(--border);
}

.sources-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.source-item {
  font-size: 13px;
  margin-bottom: 6px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}

.source-item:last-child { margin-bottom: 0; padding-bottom: 0; border-bottom: none; }

.source-file { font-weight: 500; }
.source-score { color: var(--success); margin-left: 8px; font-size: 12px; }
.source-text { color: var(--text-secondary); margin-top: 2px; font-size: 12px; }

.chat-input {
  display: flex;
  gap: 10px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
  margin-top: 14px;
}

.chat-input textarea {
  flex: 1;
  resize: none;
}

.chat-input button { align-self: flex-end; }

.btn-stop {
  background: var(--danger);
  color: #fff;
  border: none;
  border-radius: var(--radius);
  padding: 8px 16px;
  font-size: 14px;
  cursor: pointer;
}

.btn-stop:hover { opacity: 0.85; }

.cursor {
  display: inline-block;
  animation: blink 0.8s infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>
