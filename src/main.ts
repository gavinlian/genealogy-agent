import { createApp } from 'vue'
import './styles/theme.css'
import App from './App.vue'

const API_BASE = '/api'

export { API_BASE }

const app = createApp(App)
app.mount('#app')