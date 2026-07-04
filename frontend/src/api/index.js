import axios from 'axios'
import { createRouter } from 'vue-router'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 300000,  // 5min — first request loads embedding+reranker models
})

// Auth interceptor — attach Bearer token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('rag_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 401 interceptor — redirect to login
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('rag_token')
      localStorage.removeItem('rag_user')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)

// KB management
export function getKBList() {
  return api.get('/kb/list').then(r => r.data)
}

export function getKBStats(name) {
  return api.get(`/kb/${encodeURIComponent(name)}`).then(r => r.data)
}

export function createKB(name, department, accessLevel, description) {
  return api.post('/kb/create', { name, department, access_level: accessLevel, description }).then(r => r.data)
}

export function deleteKB(name) {
  return api.delete(`/kb/${encodeURIComponent(name)}`).then(r => r.data)
}

// Documents
export function uploadDocuments(files, kbName) {
  const form = new FormData()
  for (const f of files) form.append('files', f)
  if (kbName) form.append('kb_name', kbName)
  return api.post('/documents/upload', form, { timeout: 300000 }).then(r => r.data)
}

export function importURL(url, kbName) {
  return api.post('/documents/import', { url, kb_name: kbName }).then(r => r.data)
}

export function getDocuments(kbName) {
  const params = kbName ? { kb_name: kbName } : {}
  return api.get('/documents', { params }).then(r => r.data)
}

export function getDocument(docId) {
  return api.get(`/documents/${docId}`).then(r => r.data)
}

export function deleteDocument(docId) {
  return api.delete(`/documents/${docId}`).then(r => r.data)
}

// Search
export function search(query, kbName, topK = 5) {
  const body = { query, top_k: topK }
  if (kbName) body.kb_name = kbName
  return api.post('/search', body).then(r => r.data)
}

// Config
export function getConfig() {
  return api.get('/config').then(r => r.data)
}

export function updateConfig(data) {
  return api.post('/config', data).then(r => r.data)
}

// Chat (SSE streaming)
export function chatStream(question, kbName, topK, history, signal, fastMode = false) {
  const body = { question, top_k: topK, history, fast_mode: fastMode }
  if (kbName) body.kb_name = kbName
  const token = localStorage.getItem('rag_token')
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  return fetch('/api/v1/chat', {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal,
  })
}

// QA memory
export function saveMemory(question, answer, kbName) {
  const body = { question, answer }
  if (kbName) body.kb_name = kbName
  return api.post('/chat/correct', body).then(r => r.data)
}

// User management (admin)
export function getUsers() {
  return api.get('/auth/users').then(r => r.data)
}

export function deleteUser(username) {
  return api.delete(`/auth/users/${encodeURIComponent(username)}`).then(r => r.data)
}
