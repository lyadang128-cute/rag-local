<template>
  <div class="search-page">
    <div class="card">
      <h2>语义搜索</h2>

      <form class="search-form" @submit.prevent="doSearch">
        <div class="search-row">
          <input
            v-model="query"
            type="text"
            placeholder="输入搜索内容..."
            class="search-input"
            autofocus
          />
          <button type="submit" class="btn-primary" :disabled="searching || !query.trim()">
            搜索
          </button>
        </div>
        <div class="search-opts">
          <select v-model="kbName">
            <option value="">全部知识库</option>
            <option v-for="kb in kbList" :key="kb" :value="kb">{{ kb }}</option>
          </select>
          <select v-model="topK">
            <option :value="3">Top 3</option>
            <option :value="5">Top 5</option>
            <option :value="10">Top 10</option>
          </select>
        </div>
      </form>
    </div>

    <div v-if="searching" class="loading">搜索中...</div>
    <div v-if="error" class="error-msg">{{ error }}</div>

    <div v-if="results.length" class="results">
      <div v-for="(hit, i) in results" :key="i" class="card result-item">
        <div class="result-header">
          <span class="result-index">#{{ i + 1 }}</span>
          <span class="result-file">{{ hit.filename }}</span>
          <span class="badge badge-success">相似度 {{ (hit.score * 100).toFixed(1) }}%</span>
        </div>
        <p class="result-text">{{ hit.text }}</p>
      </div>
    </div>

    <div v-if="searched && results.length === 0" class="empty-state">
      未找到相关结果
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getKBList, search } from '../api/index.js'

const kbList = ref([])
const kbName = ref('')
const query = ref('')
const topK = ref(5)
const results = ref([])
const searching = ref(false)
const searched = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    const res = await getKBList()
    kbList.value = res.data?.kb_names || []
  } catch {
    error.value = '加载知识库列表失败，请确认后端已启动'
  }
})

async function doSearch() {
  if (!query.value.trim()) return
  searching.value = true
  searched.value = true
  error.value = ''
  try {
    const res = await search(query.value.trim(), kbName.value || null, topK.value)
    results.value = res.data?.results || []
  } catch (e) {
    error.value = '搜索失败：' + (e.response?.data?.message || e.message)
  } finally {
    searching.value = false
  }
}
</script>

<style scoped>
.search-page { max-width: 860px; margin: 0 auto; }

h2 { font-size: 18px; font-weight: 600; margin-bottom: 16px; }

.search-row {
  display: flex;
  gap: 10px;
}

.search-input {
  flex: 1;
  font-size: 15px;
  padding: 10px 14px;
}

.search-opts {
  display: flex;
  gap: 10px;
  margin-top: 12px;
}

.search-opts select { width: 160px; }

.loading {
  text-align: center;
  color: var(--text-secondary);
  padding: 40px 0;
}

.results { margin-top: 20px; display: flex; flex-direction: column; gap: 12px; }

.result-item {
  padding: 16px 20px;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.result-index {
  font-weight: 700;
  color: var(--primary);
}

.result-file {
  font-weight: 500;
  font-size: 14px;
}

.result-text {
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.error-msg {
  text-align: center;
  color: var(--danger);
  font-size: 14px;
  padding: 16px;
  background: #fee2e2;
  border-radius: var(--radius);
  margin-top: 16px;
}

.empty-state {
  text-align: center;
  color: var(--text-secondary);
  font-size: 14px;
  margin-top: 40px;
}
</style>
