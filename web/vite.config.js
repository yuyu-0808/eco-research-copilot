import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发期把 /api 与 /ws 代理到 FastAPI 后端（127.0.0.1:8010），
// 前端只需请求同源相对路径，避免跨域。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8010',
        ws: true,
      },
    },
  },
})
