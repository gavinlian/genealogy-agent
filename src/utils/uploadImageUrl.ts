import { API_BASE } from '../main'

const IMAGE_EXT = /\.(jpe?g|png|gif|webp|bmp)$/i

/** 是否可作为 <img> 显示的上传文件（排除 PDF 等） */
export function isDisplayableUploadPath(path: string | null | undefined): boolean {
  const p = (path || '').trim()
  if (!p || p.startsWith('data:')) return Boolean(p)
  if (p.startsWith('http://') || p.startsWith('https://')) return true
  const name = p.replace(/^uploads[\\/]/, '')
  return IMAGE_EXT.test(name)
}

/** 将 uploads 目录中的文件名转为可访问 URL；dataUrl 优先（本地预览）。 */
export function uploadImageUrl(path: string | null | undefined, dataUrl?: string): string {
  if (dataUrl?.trim()) return dataUrl.trim()
  const p = (path || '').trim()
  if (!p) return ''
  if (p.startsWith('http://') || p.startsWith('https://') || p.startsWith('data:')) return p
  if (!isDisplayableUploadPath(p)) return ''
  const name = p.replace(/^uploads[\\/]/, '')
  return `${API_BASE}/uploads/${encodeURIComponent(name)}`
}
