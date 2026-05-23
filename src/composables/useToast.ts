import { ref } from 'vue'

export type ToastType = 'success' | 'error' | 'info'

export interface ToastItem {
  id: number
  message: string
  type: ToastType
}

const toasts = ref<ToastItem[]>([])
let seq = 0

export function useToast() {
  function show(message: string, type: ToastType = 'info', durationMs = 2800) {
    const id = ++seq
    toasts.value = [...toasts.value, { id, message, type }]
    window.setTimeout(() => {
      toasts.value = toasts.value.filter((t) => t.id !== id)
    }, durationMs)
  }

  return { toasts, show }
}
