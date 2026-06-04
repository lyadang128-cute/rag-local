import { createRouter, createWebHistory } from 'vue-router'
import Layout from '../views/Layout.vue'

const routes = [
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

export default createRouter({
  history: createWebHistory(),
  routes,
})
