import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

const TOKEN_KEY = 'rag_token'
const USER_KEY = 'rag_user'

// Shared reactive state (singleton pattern)
const token = ref(localStorage.getItem(TOKEN_KEY) || '')
const user = ref(JSON.parse(localStorage.getItem(USER_KEY) || 'null'))

export function useAuth() {
  const router = useRouter()
  const isLoggedIn = computed(() => !!token.value && !!user.value)

  async function login(username, password) {
    const res = await axios.post('/api/v1/auth/login', { username, password })
    const data = res.data.data
    token.value = data.token
    user.value = data.user
    localStorage.setItem(TOKEN_KEY, data.token)
    localStorage.setItem(USER_KEY, JSON.stringify(data.user))
    return data.user
  }

  async function register(username, password, role, department) {
    await axios.post('/api/v1/auth/register', { username, password, role, department })
  }

  async function fetchMe() {
    if (!token.value) return null
    try {
      const res = await axios.get('/api/v1/auth/me', {
        headers: { Authorization: `Bearer ${token.value}` },
      })
      user.value = res.data.data
      localStorage.setItem(USER_KEY, JSON.stringify(user.value))
      return user.value
    } catch {
      logout()
      return null
    }
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    router.push('/login')
  }

  return { token, user, isLoggedIn, login, register, fetchMe, logout }
}
