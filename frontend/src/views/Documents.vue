<template>
  <div class="docs-page">
    <div class="card">
      <h2>文档管理</h2>

      <div class="upload-section">
        <div class="upload-tabs">
          <button :class="['tab', { active: tab === 'file' }]" @click="tab = 'file'">上传文件</button>
          <button :class="['tab', { active: tab === 'url' }]" @click="tab = 'url'">导入网页</button>
        </div>

        <div v-if="tab === 'file'" class="upload-area">
          <div
            class="drop-zone"
            @dragover.prevent="dragover = true"
            @dragleave.prevent="dragover = false"
            @drop.prevent="onDrop"
            :class="{ dragover }"
          >
            <p>拖拽文件到这里，或点击选择</p>
            <p class="hint">支持 txt / pdf / docx / md / xlsx / pptx / 图片</p>
            <input
              type="file"
              multiple
              ref="fileInput"
              @change="onFileSelect"
              class="file-input-hidden"
            />
            <button class="btn-outline" @click="$refs.fileInput.click()">选择文件</button>
          </div>
          <div v-if="selectedFiles.length" class="file-list">
            <div v-for="(f, i) in selectedFiles" :key="i" class="file-tag">
              {{ f.name }} ({{ formatSize(f.size) }})
              <span class="file-remove" @click="removeFile(i)">×</span>
            </div>
          </div>
          <div class="upload-actions" v-if="selectedFiles.length">
            <select v-model="uploadKB">
              <option value="">默认知识库</option>
              <option v-for="kb in kbList" :key="kb" :value="kb">{{ kb }}</option>
            </select>
            <button class="btn-primary" @click="doUpload" :disabled="uploading">
              {{ uploading ? '上传中...' : '上传并索引' }}
            </button>
          </div>
        </div>

        <div v-if="tab === 'url'" class="url-form">
          <div class="url-row">
            <input v-model="importUrl" type="url" placeholder="https://example.com/article" />
            <select v-model="uploadKB">
              <option value="">默认知识库</option>
              <option v-for="kb in kbList" :key="kb" :value="kb">{{ kb }}</option>
            </select>
            <button class="btn-primary" @click="doImport" :disabled="importing || !importUrl.trim()">
              {{ importing ? '导入中...' : '导入' }}
            </button>
          </div>
        </div>
      </div>

      <div v-if="message" :class="['msg-banner', messageType]">{{ message }}</div>

      <div v-if="progress" class="progress-bar-wrap">
        <div class="progress-label">{{ progressLabel }} — {{ progress.done ? '✅ 完成' : progress.failed ? '❌ 失败' : `处理中 ${progress.current}/${progress.total}` }}</div>
        <div class="progress-bar">
          <div class="progress-fill" :class="{ done: progress.done, failed: progress.failed }" :style="{ width: progress.total ? (progress.current / progress.total * 100) + '%' : '0%' }"></div>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top: 16px;">
      <div class="doc-filter">
        <h3>文档列表</h3>
        <select v-model="filterKB" @change="loadDocuments">
          <option value="">全部知识库</option>
          <option v-for="kb in kbList" :key="kb" :value="kb">{{ kb }}</option>
        </select>
        <button class="btn-outline" @click="loadDocuments">刷新</button>
      </div>

      <div v-if="error" class="error-msg">{{ error }}</div>

      <table v-else-if="documents.length" class="doc-table">
        <thead>
          <tr>
            <th>文件名</th>
            <th>知识库</th>
            <th>状态</th>
            <th>大小</th>
            <th>上传时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="doc in documents" :key="doc.id">
            <td class="doc-filename">{{ doc.filename }}</td>
            <td><span class="badge badge-info">{{ doc.kb_name || '-' }}</span></td>
            <td><span :class="['badge', doc.status === 'indexed' ? 'badge-success' : 'badge-warn']">{{ doc.status }}</span></td>
            <td>{{ formatSize(doc.size || 0) }}</td>
            <td>{{ doc.created_at ? new Date(doc.created_at).toLocaleString('zh-CN') : '-' }}</td>
            <td>
              <button class="btn-outline btn-sm" @click="doPreview(doc.id, doc.filename)">预览</button>
              <button class="btn-danger btn-sm" @click="doDelete(doc.id)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-else class="empty-state">暂无文档，请上传文件</div>
    </div>

    <!-- Preview Modal -->
    <div v-if="previewVisible" class="modal-overlay" @click.self="previewVisible = false">
      <div class="modal preview-modal">
        <div class="modal-header">
          <h3>{{ previewFilename }}</h3>
          <button class="btn-close" @click="previewVisible = false">×</button>
        </div>
        <div class="preview-body">
          <div v-if="previewLoading" class="empty-state">加载中...</div>
          <div v-else-if="previewChunks.length">
            <div v-for="(chunk, i) in previewChunks" :key="i" class="preview-chunk">
              <div class="preview-chunk-label">片段 {{ i + 1 }}</div>
              <p class="preview-text">{{ chunk }}</p>
            </div>
          </div>
          <div v-else class="empty-state">暂无内容</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { getKBList, getDocuments, uploadDocuments, importURL, deleteDocument } from '../api/index.js'

const kbList = ref([])
const tab = ref('file')
const selectedFiles = ref([])
const uploadKB = ref('')
const uploading = ref(false)
const importing = ref(false)
const importUrl = ref('')
const documents = ref([])
const filterKB = ref('')
const fileInput = ref(null)
const dragover = ref(false)
const message = ref('')
const messageType = ref('success')
const error = ref('')
const progress = ref(null)
const progressLabel = ref('')

// Preview
const previewVisible = ref(false)
const previewLoading = ref(false)
const previewFilename = ref('')
const previewChunks = ref([])

onMounted(async () => {
  try {
    const res = await getKBList()
    kbList.value = (res.data?.kbs || []).map(kb => kb.name)
  } catch { /* ignore */ }
  loadDocuments()
})

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1048576).toFixed(1) + ' MB'
}

function onFileSelect(e) {
  const incoming = Array.from(e.target.files)
  selectedFiles.value = [...selectedFiles.value, ...incoming]
  e.target.value = ''
}

function onDrop(e) {
  dragover.value = false
  const incoming = Array.from(e.dataTransfer.files)
  selectedFiles.value = [...selectedFiles.value, ...incoming]
}

function removeFile(i) {
  selectedFiles.value.splice(i, 1)
}

async function doUpload() {
  if (!selectedFiles.value.length) return
  uploading.value = true
  message.value = ''
  progress.value = null
  try {
    const res = await uploadDocuments(selectedFiles.value, uploadKB.value || null)
    const docs = res.data?.documents || []
    message.value = `成功上传 ${docs.length} 个文件，状态：${docs.map(d => d.status).join(', ')}`
    messageType.value = 'success'
    selectedFiles.value = []

    // Start polling progress for processing documents
    for (const doc of docs) {
      if (doc.status === 'processing' && doc.id) {
        pollProgress(doc.id, doc.filename)
      }
    }

    loadDocuments()
    const kbRes = await getKBList()
    kbList.value = (kbRes.data?.kbs || []).map(kb => kb.name)
  } catch (e) {
    message.value = '上传失败：' + (e.response?.data?.message || e.message)
    messageType.value = 'error'
  } finally {
    uploading.value = false
  }
}

async function doImport() {
  if (!importUrl.value.trim()) return
  importing.value = true
  message.value = ''
  try {
    const res = await importURL(importUrl.value.trim(), uploadKB.value || null)
    const docs = res.data?.documents || []
    message.value = `成功导入，文档：${docs.map(d => d.filename).join(', ')}`
    messageType.value = 'success'
    importUrl.value = ''
    loadDocuments()
    const kbRes = await getKBList()
    kbList.value = (kbRes.data?.kbs || []).map(kb => kb.name)
  } catch (e) {
    message.value = '导入失败：' + (e.response?.data?.message || e.message)
    messageType.value = 'error'
  } finally {
    importing.value = false
  }
}

async function loadDocuments() {
  try {
    const res = await getDocuments(filterKB.value || null)
    documents.value = res.data?.items || []
    error.value = ''
  } catch (e) {
    error.value = '加载文档列表失败：' + (e.response?.data?.message || e.message)
  }
}

async function doDelete(docId) {
  if (!confirm('确定删除此文档？相关向量数据也会被清除。')) return
  try {
    await deleteDocument(docId)
    loadDocuments()
  } catch (e) {
    alert('删除失败：' + (e.response?.data?.message || e.message))
  }
}

async function pollProgress(docId, filename) {
  progressLabel.value = filename
  for (let i = 0; i < 120; i++) {
    try {
      const res = await axios.get(`/api/v1/documents/${docId}/progress`)
      const p = res.data.data
      if (p.status === 'done') {
        progress.value = { current: p.total, total: p.total, done: true }
        setTimeout(() => { progress.value = null }, 3000)
        loadDocuments()
        return
      }
      if (p.status === 'failed') {
        progress.value = { current: 0, total: 0, done: false, failed: true }
        setTimeout(() => { progress.value = null }, 5000)
        return
      }
      progress.value = { current: p.current || 0, total: p.total || 0, done: false }
    } catch {
      // ignore polling errors
    }
    await new Promise(r => setTimeout(r, 1000))
  }
  progress.value = null
}

async function doPreview(docId, filename) {
  previewVisible.value = true
  previewLoading.value = true
  previewFilename.value = filename
  previewChunks.value = []
  try {
    const res = await axios.get(`/api/v1/documents/${docId}/preview`)
    previewChunks.value = res.data.data?.chunks || []
  } catch {
    previewChunks.value = []
  } finally {
    previewLoading.value = false
  }
}
</script>

<style scoped>
.docs-page { max-width: 960px; margin: 0 auto; }

h2 { font-size: 18px; font-weight: 600; margin-bottom: 16px; }
h3 { font-size: 16px; font-weight: 600; }

.upload-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 16px;
  border-bottom: 2px solid var(--border);
}

.tab {
  padding: 8px 20px;
  border-radius: 0;
  background: none;
  color: var(--text-secondary);
  font-size: 14px;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
}

.tab.active {
  color: var(--primary);
  border-bottom-color: var(--primary);
}

.drop-zone {
  border: 2px dashed var(--border);
  border-radius: var(--radius);
  padding: 32px;
  text-align: center;
  color: var(--text-secondary);
  transition: all 0.2s;
}

.drop-zone.dragover {
  border-color: var(--primary);
  background: #eef2ff;
}

.drop-zone p { margin-bottom: 8px; font-size: 14px; }

.hint { font-size: 12px !important; }

.file-input-hidden { display: none; }

.file-list { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 6px; }

.file-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: #eef2ff;
  border-radius: 4px;
  font-size: 13px;
}

.file-remove { cursor: pointer; color: var(--danger); font-weight: 700; }

.upload-actions {
  display: flex;
  gap: 10px;
  margin-top: 14px;
  align-items: center;
}

.upload-actions select { width: 160px; }

.url-row {
  display: flex;
  gap: 10px;
}

.url-row input { flex: 1; }
.url-row select { width: 160px; }

.msg-banner {
  margin-top: 14px;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
}

.msg-banner.success { background: #dcfce7; color: #166534; }
.msg-banner.error { background: #fee2e2; color: #991b1b; }

.error-msg {
  text-align: center;
  color: var(--danger);
  font-size: 14px;
  padding: 16px;
  background: #fee2e2;
  border-radius: var(--radius);
}

.doc-filter {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.doc-filter select { width: 160px; }
.doc-filter h3 { flex: 1; }

.doc-table {
  width: 100%;
  border-collapse: collapse;
}

.doc-table th, .doc-table td {
  text-align: left;
  padding: 10px 12px;
  font-size: 13px;
  border-bottom: 1px solid var(--border);
}

.doc-table th {
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 12px;
  text-transform: uppercase;
}

.doc-filename {
  font-weight: 500;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.btn-sm { padding: 4px 10px; font-size: 12px; }

.empty-state {
  text-align: center;
  color: var(--text-secondary);
  font-size: 14px;
  padding: 40px 0;
}

.progress-bar-wrap { margin-top: 12px; }

.progress-label {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.progress-bar {
  height: 8px;
  background: var(--border);
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--primary);
  border-radius: 4px;
  transition: width 0.5s ease;
}

.progress-fill.done { background: #22c55e; }
.progress-fill.failed { background: var(--danger); }

/* Preview modal */
.preview-modal {
  width: 640px;
  display: flex;
  flex-direction: column;
  max-height: 80vh;
}

.preview-body {
  overflow-y: auto;
  flex: 1;
  max-height: 60vh;
  padding-right: 4px;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.modal-header h3 { font-size: 16px; font-weight: 600; }

.btn-close {
  background: none;
  border: none;
  font-size: 22px;
  cursor: pointer;
  color: var(--text-secondary);
}

.preview-chunk {
  margin-bottom: 16px;
  padding: 12px;
  background: #f8fafc;
  border-radius: 8px;
}

.preview-chunk-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--primary);
  text-transform: uppercase;
  margin-bottom: 6px;
}

.preview-text {
  font-size: 13px;
  line-height: 1.8;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
}

/* Modal shared (mirrors Layout.vue) */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal {
  background: var(--bg, #fff);
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 8px 30px rgba(0,0,0,0.18);
}

.btn-outline {
  padding: 4px 10px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary);
  margin-right: 6px;
}

.btn-outline:hover { background: var(--accent-subtle, #eef2ff); }
</style>
