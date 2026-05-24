import { createApp } from 'vue'
import './styles/theme.css'
import App from './App.vue'

const API_BASE = '/api'

export { API_BASE }

try {
  const app = createApp(App)
  app.config.errorHandler = (err) => {
    console.error(err)
    const root = document.getElementById('app')
    if (root && !root.querySelector('.boot-error')) {
      const box = document.createElement('div')
      box.className = 'boot-error'
      box.style.cssText = 'padding:16px;font-family:sans-serif;color:#842;'
      box.textContent = `页面加载出错：${err instanceof Error ? err.message : String(err)}`
      root.appendChild(box)
    }
  }
  app.mount('#app')
} catch (err) {
  const root = document.getElementById('app')
  if (root) {
    root.textContent = `页面加载失败：${err instanceof Error ? err.message : String(err)}`
  }
  throw err
}
