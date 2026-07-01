<template>
  <div class="login-page">
    <div class="login-card">
      <h1>RAG 知识库</h1>
      <p class="subtitle">{{ isRegister ? '创建账号' : '登录' }}</p>

      <form @submit.prevent="doSubmit">
        <div class="form-group">
          <label>用户名</label>
          <input v-model="form.username" type="text" placeholder="输入用户名" required maxlength="30" />
        </div>

        <div class="form-group">
          <label>密码</label>
          <input v-model="form.password" type="password" placeholder="输入密码" required minlength="4" />
        </div>

        <template v-if="isRegister">
          <div class="form-group">
            <label>角色</label>
            <select v-model="form.role">
              <option value="employee">普通员工</option>
              <option value="manager">部门主管</option>
              <option value="admin">管理员</option>
            </select>
          </div>
          <div class="form-group">
            <label>部门</label>
            <input v-model="form.department" type="text" placeholder="如：技术部" maxlength="50" />
          </div>
        </template>

        <div v-if="error" class="error-msg">{{ error }}</div>

        <button type="submit" class="btn-primary" :disabled="loading">
          {{ loading ? '处理中...' : (isRegister ? '注册' : '登录') }}
        </button>
      </form>

      <p class="switch-mode">
        {{ isRegister ? '已有账号？' : '没有账号？' }}
        <a href="#" @click.prevent="toggleMode">{{ isRegister ? '去登录' : '去注册' }}</a>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth.js'

const router = useRouter()
const { login, register } = useAuth()

const isRegister = ref(false)
const loading = ref(false)
const error = ref('')

const form = reactive({
  username: '',
  password: '',
  role: 'employee',
  department: '',
})

function toggleMode() {
  isRegister.value = !isRegister.value
  error.value = ''
  form.username = ''
  form.password = ''
  form.role = 'employee'
  form.department = ''
}

async function doSubmit() {
  loading.value = true
  error.value = ''
  try {
    if (isRegister.value) {
      await register(form.username, form.password, form.role, form.department)
      // After register, auto login
      await login(form.username, form.password)
    } else {
      await login(form.username, form.password)
    }
    router.push('/chat')
  } catch (e) {
    error.value = (e.response?.data?.detail || e.response?.data?.message || e.message || '操作失败').toString()
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
}

.login-card {
  background: #fff;
  border-radius: 12px;
  padding: 40px;
  width: 400px;
  max-width: 90vw;
  box-shadow: 0 4px 24px rgba(0,0,0,0.08);
}

h1 {
  font-size: 22px;
  font-weight: 700;
  text-align: center;
  color: var(--primary, #1e3a5f);
}

.subtitle {
  text-align: center;
  color: var(--text-secondary, #666);
  font-size: 14px;
  margin: 6px 0 24px;
}

.form-group {
  margin-bottom: 14px;
}

.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
  color: var(--text-secondary, #555);
}

.form-group input,
.form-group select {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border, #ddd);
  border-radius: 6px;
  font-size: 14px;
}

.btn-primary {
  width: 100%;
  padding: 12px;
  background: var(--primary, #1e3a5f);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 15px;
  cursor: pointer;
  margin-top: 8px;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-msg {
  text-align: center;
  color: var(--danger, #d32f2f);
  font-size: 13px;
  padding: 8px;
  background: #fee2e2;
  border-radius: 6px;
  margin-bottom: 8px;
}

.switch-mode {
  text-align: center;
  margin-top: 18px;
  font-size: 13px;
  color: var(--text-secondary, #888);
}

.switch-mode a {
  color: var(--primary, #1e3a5f);
  text-decoration: none;
  font-weight: 500;
}
</style>
