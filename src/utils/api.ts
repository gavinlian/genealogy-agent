const API_BASE = '/api'
const API_TIMEOUT = 15000
const API_TIMEOUT_LONG = 300000

export async function api(
  method: string,
  path: string,
  data?: unknown,
  timeoutMs = API_TIMEOUT,
) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: data ? JSON.stringify(data) : undefined,
      signal: controller.signal,
    })
    const text = await res.text()
    try {
      const json = JSON.parse(text)
      if (!res.ok && !json.message && !json.error) {
        json.success = false
        json.message = `HTTP ${res.status}`
      }
      return json
    } catch {
      return { success: false, message: res.ok ? '响应解析失败' : `HTTP ${res.status}: ${text.slice(0, 120)}` }
    }
  } catch (err: unknown) {
    const e = err as { name?: string }
    if (e?.name === 'AbortError') {
      return { success: false, message: '请求超时，请确认后端已启动' }
    }
    return { success: false, message: '无法连接后端，请确认 backend 已启动' }
  } finally {
    clearTimeout(timer)
  }
}

export { API_TIMEOUT_LONG }
