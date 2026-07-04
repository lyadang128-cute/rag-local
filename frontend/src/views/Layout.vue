<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="logo">RAG 知识库</div>
      <nav>
        <router-link to="/chat" class="nav-item">
          <span class="nav-icon">💬</span> AI 对话
        </router-link>
        <router-link to="/search" class="nav-item">
          <span class="nav-icon">🔍</span> 语义搜索
        </router-link>
        <router-link to="/documents" class="nav-item">
          <span class="nav-icon">📄</span> 文档管理
        </router-link>
        <router-link to="/kb" class="nav-item">
          <span class="nav-icon">📚</span> 知识库
        </router-link>
        <router-link v-if="isAdmin" to="/users" class="nav-item">
          <span class="nav-icon">👥</span> 用户管理
        </router-link>
        <router-link to="/settings" class="nav-item">
          <span class="nav-icon">⚙️</span> 系统设置
        </router-link>
      </nav>

      <div class="sidebar-footer" v-if="user">
        <div class="user-info">
          <span class="user-role-dot" :class="user.role"></span>
          <div>
            <div class="user-name">{{ user.username }}</div>
            <div class="user-dept">{{ user.department || user.role }}</div>
          </div>
        </div>
        <div class="sidebar-actions">
          <button class="btn-chpwd" @click="showPwdModal = true">改密</button>
          <button class="btn-logout" @click="doLogout">退出</button>
        </div>
      </div>
    </aside>
    <main class="main">
      <router-view v-slot="{ Component }">
        <keep-alive>
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>

    <!-- Change Password Modal -->
    <div v-if="showPwdModal" class="modal-overlay" @click.self="showPwdModal = false">
      <div class="modal">
        <h3>修改密码</h3>
        <form @submit.prevent="doChangePassword">
          <div class="form-group">
            <label>原密码</label>
            <input v-model="pwdForm.old" type="password" required />
          </div>
          <div class="form-group">
            <label>新密码</label>
            <input v-model="pwdForm.new1" type="password" required minlength="4" />
          </div>
          <div class="form-group">
            <label>确认新密码</label>
            <input v-model="pwdForm.new2" type="password" required minlength="4" />
          </div>
          <div v-if="pwdError" class="error-msg" style="margin-bottom:12px">{{ pwdError }}</div>
          <div v-if="pwdOk" class="ok-msg" style="margin-bottom:12px">{{ pwdOk }}</div>
          <div class="modal-actions">
            <button type="button" class="btn-ghost" @click="showPwdModal = false; resetPwdForm()">取消</button>
            <button type="submit" class="btn-primary" :disabled="pwdLoading">{{ pwdLoading ? '修改中...' : '确认修改' }}</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import { useAuth } from '../composables/useAuth.js'
import axios from 'axios'

const { user: authUser, logout, fetchMe } = useAuth()
const user = ref(authUser.value)
const isAdmin = computed(() => user.value?.role === 'admin')

// Password change
const showPwdModal = ref(false)
const pwdLoading = ref(false)
const pwdError = ref('')
const pwdOk = ref('')
const pwdForm = reactive({ old: '', new1: '', new2: '' })

function resetPwdForm() {
  pwdForm.old = ''; pwdForm.new1 = ''; pwdForm.new2 = ''
  pwdError.value = ''; pwdOk.value = ''
}

async function doChangePassword() {
  if (pwdForm.new1 !== pwdForm.new2) {
    pwdError.value = '两次输入的新密码不一致'
    return
  }
  pwdLoading.value = true
  pwdError.value = ''
  pwdOk.value = ''
  try {
    await axios.post('/api/v1/auth/change-password', {
      old_password: pwdForm.old,
      new_password: pwdForm.new1,
    })
    pwdOk.value = '密码修改成功'
    setTimeout(() => { showPwdModal.value = false; resetPwdForm() }, 1500)
  } catch (e) {
    pwdError.value = e.response?.data?.detail || e.message || '修改失败'
  } finally {
    pwdLoading.value = false
  }
}

onMounted(async () => {
  if (!user.value) {
    user.value = await fetchMe()
  }
})

function doLogout() {
  logout()
}
</script>

<style scoped>
.layout {
  display: flex;
  height: 100%;
}

.sidebar {
  width: 220px;
  background: #1e1b4b;
  color: #e0e7ff;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.logo {
  padding: 20px 20px 16px;
  font-size: 18px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 1px;
}

nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 8px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 8px;
  color: #c7d2fe;
  font-size: 14px;
  text-decoration: none;
  transition: all 0.15s;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
  text-decoration: none;
}

.nav-item.router-link-active {
  background: var(--primary);
  color: #fff;
}

.nav-icon { font-size: 16px; }

.sidebar-footer {
  margin-top: auto;
  padding: 16px;
  border-top: 1px solid rgba(255,255,255,0.1);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.user-role-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.user-role-dot.admin { background: #f87171; }
.user-role-dot.manager { background: #fbbf24; }
.user-role-dot.employee { background: #34d399; }

.user-name {
  font-size: 13px;
  font-weight: 600;
  color: #fff;
}

.user-dept {
  font-size: 11px;
  color: #a5b4fc;
}

.sidebar-actions {
  display: flex;
  gap: 6px;
}

.btn-chpwd {
  flex: 1;
  padding: 6px 0;
  background: rgba(255,255,255,0.08);
  color: #c7d2fe;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}

.btn-chpwd:hover { background: rgba(255,255,255,0.15); color: #fff; }

.btn-logout {
  flex: 1;
  padding: 6px 0;
  background: rgba(255,255,255,0.1);
  color: #c7d2fe;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}

.btn-logout:hover { background: rgba(255,255,255,0.2); color: #fff; }

/* Modal shared styles */
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
  width: 400px;
  max-width: 90vw;
  box-shadow: 0 8px 30px rgba(0,0,0,0.18);
}

.modal h3 { font-size: 16px; font-weight: 600; margin-bottom: 20px; }

.form-group { margin-bottom: 14px; }

.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
  color: var(--text-secondary, #555);
}

.form-group input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border, #ddd);
  border-radius: 6px;
  font-size: 14px;
}

.modal-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 20px;
}

.btn-ghost {
  padding: 8px 18px;
  background: transparent;
  border: 1px solid var(--border, #ddd);
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  color: var(--text-secondary, #888);
}

.ok-msg {
  text-align: center;
  color: #166534;
  font-size: 13px;
  padding: 8px;
  background: #dcfce7;
  border-radius: 6px;
}

.main {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}
</style>
