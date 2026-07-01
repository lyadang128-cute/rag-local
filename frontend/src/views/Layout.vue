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
        <button class="btn-logout" @click="doLogout">退出</button>
      </div>
    </aside>
    <main class="main">
      <router-view v-slot="{ Component }">
        <keep-alive>
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAuth } from '../composables/useAuth.js'

const { user: authUser, logout, fetchMe } = useAuth()
const user = ref(authUser.value)

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

.btn-logout {
  width: 100%;
  padding: 6px 0;
  background: rgba(255,255,255,0.1);
  color: #c7d2fe;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-logout:hover {
  background: rgba(255,255,255,0.2);
  color: #fff;
}

.main {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}
</style>
