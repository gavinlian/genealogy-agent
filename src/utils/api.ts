const API_BASE = '/api'

/** 常规读写（列表、详情、保存） */
const API_TIMEOUT = 60_000

/** Agent 对话 / LLM 选工具（可能多轮） */
const API_TIMEOUT_AGENT = 180_000

/** OCR、AI 整理、融合、重建等重任务 */
const API_TIMEOUT_LONG = 300_000

/** 多页 PDF 逐页 OCR（页数多时可较久） */
const API_TIMEOUT_PDF = 900_000

const LONG_PATH =
  /smart-suggest|ai-organize|source-fusion|scan-ocr|regenerate-relation|regenerate-pipeline|\/ocr\/|\/rebuild|parse-import|clear-genealogy|\/agent\/(genealogy-scan|generate|pdf\/scan-ocr|batch\/scan-ocr)/i

const PDF_PATH = /\/agent\/(pdf\/scan-ocr|batch\/scan-ocr)/i

const AGENT_PATH = /\/agent\/(chat|home\/chat|confirm)/i

function resolveApiTimeout(path: string, explicit?: number): number {
  if (explicit != null) return explicit
  if (PDF_PATH.test(path)) return API_TIMEOUT_PDF
  if (AGENT_PATH.test(path)) return API_TIMEOUT_AGENT
  if (LONG_PATH.test(path)) return API_TIMEOUT_LONG
  return API_TIMEOUT
}

function apiHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  try {
    const uid = localStorage.getItem('genealogy_user_id')
    if (uid) headers['X-User-Id'] = uid
  } catch {
    /* ignore */
  }
  return headers
}

function formatFetchError(err: unknown, timeoutMs: number, path: string): string {
  const e = err as { name?: string; message?: string }
  if (e?.name === 'AbortError') {
    const sec = Math.round(timeoutMs / 1000)
    if (AGENT_PATH.test(path) || LONG_PATH.test(path)) {
      return `请求超时（${sec} 秒）。AI/OCR 较慢，请稍等或检查网络；若持续失败请确认 backend 在 8080 端口运行`
    }
    return `请求超时（${sec} 秒）。请确认 backend 已启动（8080），或稍后重试`
  }
  if (e?.message?.includes('Failed to fetch') || e?.message?.includes('NetworkError')) {
    return '无法连接后端。请在 backend 目录运行：python main.py（默认 http://127.0.0.1:8080）'
  }
  return e?.message || '网络请求失败'
}

export async function api(
  method: string,
  path: string,
  data?: unknown,
  timeoutMs?: number,
) {
  const timeout = resolveApiTimeout(path, timeoutMs)
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: apiHeaders(),
      body: data ? JSON.stringify(data) : undefined,
      signal: controller.signal,
    })
    const text = await res.text()
    try {
      const json = JSON.parse(text)
      if (!res.ok && !json.message && !json.error) {
        json.success = false
        const detail = typeof json.detail === 'string'
          ? json.detail
          : Array.isArray(json.detail)
            ? json.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join('；')
            : ''
        json.message = detail || `HTTP ${res.status}`
      }
      return json
    } catch {
      return { success: false, message: res.ok ? '响应解析失败' : `HTTP ${res.status}: ${text.slice(0, 120)}` }
    }
  } catch (err: unknown) {
    return { success: false, message: formatFetchError(err, timeout, path) }
  } finally {
    clearTimeout(timer)
  }
}

/** 轻量健康检查（3 秒超时） */
export async function pingBackend(): Promise<{ ok: boolean; message?: string; families?: number }> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 3000)
  try {
    const res = await fetch(`${API_BASE}/health`, { signal: controller.signal })
    const json = await res.json()
    if (!res.ok || !json.success) {
      return { ok: false, message: '后端异常' }
    }
    return { ok: true, families: json.families }
  } catch {
    return { ok: false, message: '后端未响应（请启动 python main.py）' }
  } finally {
    clearTimeout(timer)
  }
}

export { API_TIMEOUT, API_TIMEOUT_AGENT, API_TIMEOUT_LONG, API_TIMEOUT_PDF, resolveApiTimeout }
