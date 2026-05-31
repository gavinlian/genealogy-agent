/** 上传前压缩大图，避免请求过大导致 500/超时 */
export async function compressImageFile(
  file: File,
  maxSide = 2048,
  quality = 0.85,
): Promise<File> {
  if (!file.type.startsWith('image/') || file.size < 900_000) {
    return file
  }
  if (file.type === 'image/gif') {
    return file
  }

  const bitmap = await createImageBitmap(file)
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height))
  const w = Math.max(1, Math.round(bitmap.width * scale))
  const h = Math.max(1, Math.round(bitmap.height * scale))

  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    bitmap.close()
    return file
  }
  ctx.drawImage(bitmap, 0, 0, w, h)
  bitmap.close()

  const blob = await new Promise<Blob | null>((resolve) => {
    canvas.toBlob((b) => resolve(b), 'image/jpeg', quality)
  })
  if (!blob) return file
  const name = file.name.replace(/\.[^.]+$/, '') + '.jpg'
  return new File([blob], name, { type: 'image/jpeg' })
}
