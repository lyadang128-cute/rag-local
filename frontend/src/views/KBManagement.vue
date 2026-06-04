<template>
  <div class="kb-page">
    <div class="card">
      <h2>知识库管理</h2>

      <table v-if="kbData.length" class="kb-table">
        <thead>
          <tr>
            <th>知识库名称</th>
            <th>向量数量</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="kb in kbData" :key="kb.name">
            <td>
              <span class="kb-name">{{ kb.name || '(默认)' }}</span>
            </td>
            <td>{{ kb.count || 0 }}</td>
            <td>
              <button class="btn-danger btn-sm" @click="doDelete(kb.name)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="error" class="error-msg">{{ error }}</div>
      <div v-else class="empty-state">
        暂无知识库数据，请先上传文档
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getKBList, getKBStats, deleteKB } from '../api/index.js'

const kbData = ref([])
const error = ref('')

onMounted(() => { loadKBData() })

async function loadKBData() {
  error.value = ''
  try {
    const listRes = await getKBList()
    const names = listRes.data?.kb_names || []
    const stats = await Promise.all(
      names.map(async (name) => {
        try {
          const res = await getKBStats(name)
          return { name: name || '(默认)', count: res.data?.chunk_count ?? res.data?.count ?? 0 }
        } catch {
          return { name, count: 0 }
        }
      })
    )
    kbData.value = stats
  } catch (e) {
    error.value = '加载知识库失败：' + (e.response?.data?.message || e.message)
  }
}

async function doDelete(name) {
  if (!confirm(`确定删除知识库「${name}」？所有文档和向量数据将被永久删除。`)) return
  try {
    await deleteKB(name)
    loadKBData()
  } catch (e) {
    alert('删除失败：' + (e.response?.data?.message || e.message))
  }
}
</script>

<style scoped>
.kb-page { max-width: 700px; margin: 0 auto; }

h2 { font-size: 18px; font-weight: 600; margin-bottom: 16px; }

.kb-table {
  width: 100%;
  border-collapse: collapse;
}

.kb-table th, .kb-table td {
  text-align: left;
  padding: 12px 14px;
  font-size: 14px;
  border-bottom: 1px solid var(--border);
}

.kb-table th {
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 12px;
  text-transform: uppercase;
}

.kb-name {
  font-weight: 600;
  color: var(--primary);
}

.btn-sm { padding: 4px 10px; font-size: 12px; }

.error-msg {
  text-align: center;
  color: var(--danger);
  font-size: 14px;
  padding: 16px;
  background: #fee2e2;
  border-radius: var(--radius);
}

.empty-state {
  text-align: center;
  color: var(--text-secondary);
  font-size: 14px;
  padding: 40px 0;
}
</style>
