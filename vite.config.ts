import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    host: '0.0.0.0',
    headers: {
      'Cache-Control': 'no-store',
    },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
        timeout: 300_000,
        proxyTimeout: 300_000,
      },
    },
  },
  preview: {
    port: 4173,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
        timeout: 300_000,
        proxyTimeout: 300_000,
      },
    },
  },
})