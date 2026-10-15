import { ref, watchPostEffect, onMounted, onBeforeUnmount } from 'vue'

// 在两行截断状态下测量；展开时也保留按钮，并在尺寸变化后重新判断。
export function useClamp(elements, content) {
  const expanded = ref(false)
  const truncated = ref(false)
  function measure() {
    truncated.value = elements().some((el) => {
      if (!el) return false
      const clamped = el.classList.contains('clamped')
      el.classList.add('clamped')
      const overflow = el.scrollHeight > el.clientHeight
      if (!clamped) el.classList.remove('clamped')
      return overflow
    })
  }
  watchPostEffect(() => {
    content()
    measure()
  })
  onMounted(() => window.addEventListener('resize', measure))
  onBeforeUnmount(() => window.removeEventListener('resize', measure))
  return { expanded, truncated }
}
