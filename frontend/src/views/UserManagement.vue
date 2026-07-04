<template>
  <div class="users-page">
    <div class="card">
      <div class="page-header">
        <h2>用户管理</h2>
        <span class="count-badge">{{ users.length }} 个用户</span>
      </div>

      <div v-if="loading" class="empty-state">加载中...</div>
      <div v-if="error" class="error-msg">{{ error }}</div>

      <table v-if="users.length" class="user-table">
        <thead>
          <tr>
            <th>用户名</th>
            <th>角色</th>
            <th>部门</th>
            <th>注册时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td class="user-name-cell">{{ u.username }}</td>
            <td>
              <span class="role-tag" :class="u.role">
                {{ u.role === 'admin' ? '管理员' : u.role === 'manager' ? '部门主管' : '普通员工' }}
              </span>
            </td>
            <td>{{ u.department || '-' }}</td>
            <td class="date-cell">{{ u.created_at ? new Date(u.created_at).toLocaleString('zh-CN') : '-' }}</td>
            <td>
              <button
                class="btn-danger btn-sm"
                @click="doDelete(u.username)"
                :disabled="u.username === currentUser"
              >{{ u.username === currentUser ? '当前用户' : '删除' }}</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-else-if="!loading" class="empty-state">暂无用户</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getUsers, deleteUser } from '../api/index.js'

const users = ref([])
const loading = ref(false)
const error = ref('')
const currentUser = ref('')

onMounted(async () => {
  const stored = localStorage.getItem('rag_user')
  if (stored) {
    try { currentUser.value = JSON.parse(stored).username } catch {}
  }
  await loadUsers()
})

async function loadUsers() {
  loading.value = true
  error.value = ''
  try {
    const res = await getUsers()
    users.value = res.data?.users || []
  } catch (e) {
    error.value = '加载用户列表失败：' + (e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

async function doDelete(username) {
  if (!confirm(`确定删除用户「${username}」？此操作不可撤销。`)) return
  try {
    await deleteUser(username)
    users.value = users.value.filter(u => u.username !== username)
  } catch (e) {
    alert('删除失败：' + (e.response?.data?.detail || e.response?.data?.message || e.message))
  }
}
</script>

<style scoped>
.users-page { max-width: 800px; margin: 0 auto; }

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

h2 { font-size: 18px; font-weight: 600; }

.count-badge {
  font-size: 13px;
  padding: 4px 12px;
  background: var(--accent-subtle, #eef2ff);
  color: var(--primary, #1e3a5f);
  border-radius: 12px;
  font-weight: 500;
}

.user-table {
  width: 100%;
  border-collapse: collapse;
}

.user-table th, .user-table td {
  text-align: left;
  padding: 12px 14px;
  font-size: 14px;
  border-bottom: 1px solid var(--border);
}

.user-table th {
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 12px;
  text-transform: uppercase;
}

.user-name-cell { font-weight: 600; }

.date-cell { font-size: 12px; color: var(--text-secondary); }

.role-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 12px;
  font-weight: 500;
}

.role-tag.admin { background: #f8d7da; color: #721c24; }
.role-tag.manager { background: #fff3cd; color: #856404; }
.role-tag.employee { background: #d4edda; color: #155724; }

.btn-sm { padding: 4px 10px; font-size: 12px; }

.btn-danger {
  background: var(--danger, #d32f2f);
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}

.btn-danger:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

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
