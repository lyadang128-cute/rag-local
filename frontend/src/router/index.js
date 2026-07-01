import { createRouter, createWebHistory } from 'vue-router'
import Layout from '../views/Layout.vue'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
  },
  {
    path: '/',
    component: Layout,
    redirect: '/chat',
    children: [
      { path: 'chat', name: 'Chat', component: () => import('../views/Chat.vue') },
      { path: 'search', name: 'Search', component: () => import('../views/Search.vue') },
      { path: 'documents', name: 'Documents', component: () => import('../views/Documents.vue') },
      { path: 'kb', name: 'KB', component: () => import('../views/KBManagement.vue') },
      { path: 'settings', name: 'Settings', component: () => import('../views/Settings.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const token = localStorage.getItem('rag_token')
  if (to.path !== '/login' && !token) {
    return '/login'
  }
  if (to.path === '/login' && token) {
    return '/chat'
  }
})

export default router
