import { onMounted, onUnmounted, ref } from 'vue'

const COMPACT_MQ = '(max-width: 959px)'
const TOUCH_COMPACT_MQ = '(hover: none) and (pointer: coarse) and (max-width: 1279px)'

function readCompact(): boolean {
  if (typeof window === 'undefined') return true
  if (window.matchMedia('(max-width: 959px)').matches) return true
  if (window.matchMedia(TOUCH_COMPACT_MQ).matches) return true
  if (navigator.maxTouchPoints > 0 && window.innerWidth < 1280) return true
  return false
}

export function useChatSidebar() {
  const isCompact = ref(readCompact())
  const chatOpen = ref(true)
  const edgeDrag = ref({ active: false, startX: 0, offset: 0 })

  function applyMq(compact: boolean) {
    isCompact.value = compact
    edgeDrag.value = { active: false, startX: 0, offset: 0 }
  }

  onMounted(() => {
    applyMq(readCompact())
    const mqWidth = window.matchMedia(COMPACT_MQ)
    const mqTouch = window.matchMedia(TOUCH_COMPACT_MQ)
    const onChange = () => applyMq(readCompact())
    mqWidth.addEventListener('change', onChange)
    mqTouch.addEventListener('change', onChange)
    window.addEventListener('resize', onChange)
    onUnmounted(() => {
      mqWidth.removeEventListener('change', onChange)
      mqTouch.removeEventListener('change', onChange)
      window.removeEventListener('resize', onChange)
    })
  })

  function openChat() {
    chatOpen.value = true
  }

  function closeChat() {
    if (isCompact.value) chatOpen.value = false
  }

  function toggleChat() {
    chatOpen.value = !chatOpen.value
  }

  function onEdgePointerDown(e: PointerEvent) {
    edgeDrag.value = { active: true, startX: e.clientX, offset: 0 }
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  }

  function onEdgePointerMove(e: PointerEvent) {
    if (!edgeDrag.value.active) return
    edgeDrag.value.offset = Math.max(0, Math.min(e.clientX - edgeDrag.value.startX, 360))
  }

  function onEdgePointerUp() {
    if (edgeDrag.value.offset >= 40) chatOpen.value = true
    else if (edgeDrag.value.offset < 8 && edgeDrag.value.active) chatOpen.value = true
    edgeDrag.value = { active: false, startX: 0, offset: 0 }
  }

  function onEdgeTap() {
    openChat()
  }

  function sidebarStyle(): Record<string, string> | undefined {
    if (!isCompact.value || !edgeDrag.value.active || chatOpen.value) return undefined
    return { transform: `translateX(calc(-100% + ${edgeDrag.value.offset}px))` }
  }

  return {
    isCompact,
    chatOpen,
    openChat,
    closeChat,
    toggleChat,
    onEdgePointerDown,
    onEdgePointerMove,
    onEdgePointerUp,
    onEdgeTap,
    sidebarStyle,
  }
}
