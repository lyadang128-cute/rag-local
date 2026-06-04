<template>
  <div class="settings-page">
    <h2>⚙️ 系统设置</h2>
    <p class="hint">修改后即时生效。切换嵌入模式后建议重新上传文档。</p>

    <div class="card" v-if="loading">加载中...</div>

    <template v-if="!loading">
      <!-- Embedding Mode -->
      <div class="card">
        <h3>嵌入模型</h3>
        <div class="row">
          <label>模式</label>
          <select v-model="form.embed_mode" @change="markDirty('embed_mode')">
            <option value="local">🏠 本地 (免费 / bge-small-zh-v1.5 / 512维)</option>
            <option value="api">☁️ DeepSeek API (付费 / 4096维 / 更精准)</option>
          </select>
        </div>
        <div class="row">
          <label>本地模型</label>
          <input v-model="form.embed_local_model" placeholder="BAAI/bge-small-zh-v1.5" />
        </div>
        <div class="tip">
          💡 切换后需重启后端才能生效（维度不同：512 ↔ 4096）
        </div>
      </div>

      <!-- Chunking -->
      <div class="card">
        <h3>分块设置</h3>
        <div class="row">
          <label>块大小 (tokens)</label>
          <input v-model.number="form.chunk_size" type="number" min="128" max="2048" />
        </div>
        <div class="row">
          <label>重叠 (tokens)</label>
          <input v-model.number="form.chunk_overlap" type="number" min="0" max="512" />
        </div>
        <div class="tip">
          💡 越小检索越精准，但块数越多处理越慢
        </div>
      </div>

      <!-- Retrieval -->
      <div class="card">
        <h3>检索设置</h3>
        <div class="row">
          <label>返回块数 (Top-K)</label>
          <input v-model.number="form.top_k" type="number" min="1" max="20" />
        </div>
        <div class="row">
          <label>最小相关性 (MIN_SCORE)</label>
          <input v-model.number="form.min_score" type="number" step="0.05" min="0" max="1" />
        </div>
        <div class="row">
          <label>初检候选数 (RECALL_TOP_K)</label>
          <input v-model.number="form.recall_top_k" type="number" min="5" max="100" />
        </div>
        <div class="row">
          <label>Reranker 输出数</label>
          <input v-model.number="form.rerank_top_k" type="number" min="1" max="20" />
        </div>
      </div>

      <!-- API -->
      <div class="card">
        <h3>API 容错</h3>
        <div class="row">
          <label>重试次数</label>
          <input v-model.number="form.api_retry_times" type="number" min="0" max="10" />
        </div>
        <div class="tip">
          💡 API 调用失败时的指数退避重试次数
        </div>
      </div>

      <!-- Save -->
      <div class="actions">
        <button class="btn-save" @click="saveAll">
          💾 保存设置
        </button>
        <span v-if="saved" class="saved-msg">✅ 已保存</span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { getConfig, updateConfig } from '../api/index.js'

const loading = ref(true)
const saved = ref(false)
const dirtyKeys = reactive(new Set())

const form = reactive({
  embed_mode: 'local',
  embed_local_model: 'BAAI/bge-small-zh-v1.5',
  chunk_size: 512,
  chunk_overlap: 64,
  top_k: 5,
  min_score: 0.35,
  recall_top_k: 20,
  rerank_top_k: 5,
  api_retry_times: 3,
})

onMounted(async () => {
  try {
    const res = await getConfig()
    if (res.code === 0 && res.data) {
      Object.keys(form).forEach(k => {
        if (res.data[k] !== undefined) form[k] = res.data[k]
      })
    }
  } catch (e) {
    console.warn('Load config failed', e)
  } finally {
    loading.value = false
  }
})

function markDirty(key) {
  dirtyKeys.add(key.toUpperCase())
}

// Treat any change as dirty (simplifies the logic)
function saveAll() {
  const payload = {}
  for (const key of Object.keys(form)) {
    payload[key.toUpperCase()] = String(form[key])
  }
  updateConfig(payload).then(res => {
    dirtyKeys.clear()
    saved.value = true
    setTimeout(() => saved.value = false, 3000)
    if (res.message) alert(res.message)
  }).catch(e => alert('保存失败: ' + e.message))
}
</script>

<style scoped>
.settings-page { max-width: 680px; }
.settings-page h2 { margin-bottom: 4px; }
.hint { color: #888; font-size: 13px; margin-bottom: 20px; }

.card {
  background: #fff;
  border-radius: 10px;
  padding: 18px 22px;
  margin-bottom: 14px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
.card h3 { margin: 0 0 12px; font-size: 15px; }

.row {
  display: flex; align-items: center; gap: 12px;
  margin-bottom: 10px;
}
.row label { width: 160px; font-size: 13px; color: #555; flex-shrink: 0; }
.row select, .row input {
  flex: 1; padding: 6px 10px; border: 1px solid #ddd; border-radius: 6px;
  font-size: 13px;
}
.row input[type="number"] { max-width: 100px; }

.tip { font-size: 12px; color: #999; margin-top: 4px; }

.actions { display: flex; align-items: center; gap: 14px; margin-top: 8px; }
.btn-save {
  padding: 10px 22px; background: #4f46e5; color: #fff;
  border: none; border-radius: 8px; font-size: 14px; cursor: pointer;
}
.btn-save:disabled { opacity: 0.4; cursor: default; }
.saved-msg { font-size: 14px; color: #16a34a; }
</style>
