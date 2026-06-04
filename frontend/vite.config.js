import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:9090',
        changeOrigin: true,
        timeout: 300000,       // 5min — model loading + embedding + LLM streaming
        proxyTimeout: 300000,  // same for the proxy→backend leg
      },
    },
  },
})
