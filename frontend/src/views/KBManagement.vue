<template>
  <div class="kb-page">
    <div class="card">
      <div class="page-header">
        <h2>知识库管理</h2>
        <button class="btn-primary" @click="showCreate = true">+ 新建知识库</button>
      </div>

      <table v-if="kbList.length" class="kb-table">
        <thead>
          <tr>
            <th>知识库名称</th>
            <th>部门</th>
            <th>权限</th>
            <th>向量数</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="kb in kbList" :key="kb.name">
            <td>
              <span class="kb-name">{{ kb.name || '(默认)' }}</span>
              <div v-if="kb.description" class="kb-desc">{{ kb.description }}</div>
            </td>
            <td>{{ kb.department || '-' }}</td>
            <td>
              <span class="level-tag" :class="'level-' + (kb.access_level || 1)">
                {{ levelLabel(kb.access_level) }}
              </span>
            </td>
            <td>{{ kb.chunk_count ?? kb.count ?? '-' }}</td>
            <td>
              <button class="btn-danger btn-sm" @click="doDelete(kb.name)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="error" class="error-msg">{{ error }}</div>
      <div v-else-if="!kbList.length && !loading" class="empty-state">
        暂无知识库，点击上方按钮创建第一个知识库
      </div>
    </div>

    <!-- Create KB Modal -->
    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal">
        <h3>新建知识库</h3>
        <form @submit.prevent="doCreate">
          <div class="form-group">
            <label>知识库名称 <span class="required">*</span></label>
            <input v-model="form.name" type="text" placeholder="如：技术部、人事部、财务部" required maxlength="50" />
          </div>
          <div class="form-group">
            <label>所属部门</label>
            <input v-model="form.department" type="text" placeholder="如：技术部" maxlength="50" />
          </div>
          <div class="form-group">
            <label>权限级别</label>
            <select v-model.number="form.access_level">
              <option :value="1">全员可见</option>
              <option :value="2">部门可见</option>
              <option :value="3">仅管理员</option>
            </select>
            <span class="form-hint">级别1=全员可搜，级别2=本部门可搜，级别3=仅管理员</span>
          </div>
          <div class="form-group">
            <label>描述</label>
            <input v-model="form.description" type="text" placeholder="这个知识库用来存什么内容？" maxlength="200" />
          </div>
          <div v-if="createError" class="error-msg" style="margin-bottom:12px">{{ createError }}</div>
          <div class="modal-actions">
            <button type="button" class="btn-ghost" @click="showCreate = false">取消</button>
            <button type="submit" class="btn-primary" :disabled="creating">{{ creating ? '创建中...' : '创建' }}</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getKBList, getKBStats, deleteKB, createKB } from '../api/index.js'

const kbList = ref([])
const loading = ref(false)
const error = ref('')

// Create modal
const showCreate = ref(false)
const creating = ref(false)
const createError = ref('')
const form = ref({
  name: '',
  department: '',
  access_level: 1,
  description: '',
})

function levelLabel(level) {
  const map = { 1: '全员', 2: '部门', 3: '管理员' }
  return map[level] || '全员'
}

// Match access_level icon from schema: 1=green (public), 2=yellow (dept), 3=red (admin)

function resetForm() {
  form.value = { name: '', department: '', access_level: 1, description: '' }
  createError.value = ''
}

onMounted(() => { loadData() })

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const res = await getKBList()
    const kbs = res.data?.kbs || []
    // Load chunk counts per KB
    const enriched = await Promise.all(
      kbs.map(async (kb) => {
        try {
          const stats = await getKBStats(kb.name)
          return { ...kb, chunk_count: stats.data?.chunk_count ?? 0 }
        } catch {
          return { ...kb, chunk_count: 0 }
        }
      })
    )
    kbList.value = enriched
  } catch (e) {
    error.value = '加载知识库失败：' + (e.response?.data?.message || e.message)
  } finally {
    loading.value = false
  }
}

async function doCreate() {
  creating.value = true
  createError.value = ''
  try {
    await createKB(form.value.name, form.value.department, form.value.access_level, form.value.description)
    showCreate.value = false
    resetForm()
    loadData()
  } catch (e) {
    createError.value = e.response?.data?.detail || e.response?.data?.message || e.message || '创建失败'
  } finally {
    creating.value = false
  }
}

async function doDelete(name) {
  if (!confirm(`确定删除知识库「${name}」？所有文档和向量数据将被永久删除。`)) return
  try {
    await deleteKB(name)
    loadData()
  } catch (e) {
    alert('删除失败：' + (e.response?.data?.message || e.message))
  }
}
</script>

<style scoped>
.kb-page { max-width: 780px; margin: 0 auto; }

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

h2 { font-size: 18px; font-weight: 600; }

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

.kb-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.level-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 12px;
  font-weight: 500;
}

.level-1 { background: #d4edda; color: #155724; }
.level-2 { background: #fff3cd; color: #856404; }
.level-3 { background: #f8d7da; color: #721c24; }

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

/* Modal */
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
  background: var(--bg);
  border-radius: 12px;
  padding: 24px;
  width: 440px;
  max-width: 90vw;
  box-shadow: 0 8px 30px rgba(0,0,0,0.18);
}

.modal h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 20px;
}

.form-group {
  margin-bottom: 14px;
}

.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
  color: var(--text-secondary);
}

.required { color: var(--danger); }

.form-group input, .form-group select {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 14px;
  background: var(--bg);
  color: var(--text);
}

.form-hint {
  display: block;
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.modal-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 20px;
}

.btn-primary {
  padding: 8px 18px;
  background: var(--primary);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
}

.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-danger {
  background: var(--danger);
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}

.btn-ghost {
  padding: 8px 18px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  color: var(--text-secondary);
}
</style>
