import { reactive, watch } from 'vue'
import { DAY } from './sim.js'

// —— 主题 ——
function systemTheme() {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}
export const ui = reactive({
  theme: document.documentElement.getAttribute('data-theme') || systemTheme(),
  navCollapsed: false,
})
export function toggleTheme() {
  ui.theme = ui.theme === 'dark' ? 'light' : 'dark'
  document.documentElement.setAttribute('data-theme', ui.theme)
  try { localStorage.setItem('mh-theme', ui.theme) } catch (e) { /* 存储不可用时只在本次会话生效 */ }
}

// —— 模拟时钟（回放） ——
export const SPEEDS = [
  { id: 1, label: '1×', perSec: 2 },
  { id: 4, label: '4×', perSec: 8 },
  { id: 16, label: '16×', perSec: 32 },
]
export const clock = reactive({ t: DAY, playing: false, speed: 4, stopped: false })
let raf = 0
let last = 0
function tick(now) {
  if (!clock.playing) return
  const dt = (now - last) / 1000
  last = now
  const perSec = SPEEDS.find((s) => s.id === clock.speed).perSec
  clock.t = Math.min(DAY, clock.t + dt * perSec)
  if (clock.t >= DAY) { clock.playing = false; return }
  raf = requestAnimationFrame(tick)
}
export function play() {
  if (clock.stopped) return
  if (clock.t >= DAY) clock.t = 0
  clock.playing = true
  last = performance.now()
  cancelAnimationFrame(raf)
  raf = requestAnimationFrame(tick)
}
export function pause() { clock.playing = false; cancelAnimationFrame(raf) }
export function togglePlay() { clock.playing ? pause() : play() }
export function seek(t) { clock.t = Math.max(0, Math.min(DAY, t)) }

// —— 抽屉：最多叠两层，第三层起在第二层内替换并保留返回 ——
export const drawers = reactive({ stack: [] })
export function openDrawer(item, { fromDrawer = false } = {}) {
  const entry = { ...item, history: [] }
  if (!fromDrawer || drawers.stack.length === 0) { drawers.stack = [entry]; return }
  if (drawers.stack.length === 1) { drawers.stack.push(entry); return }
  const top = drawers.stack[1]
  const { history, ...rest } = top
  drawers.stack[1] = { ...item, history: [...history, rest] }
}
export function drawerBack(level) {
  const layer = drawers.stack[level]
  if (!layer?.history.length) return
  const prev = layer.history[layer.history.length - 1]
  drawers.stack[level] = { ...prev, history: layer.history.slice(0, -1) }
}
export function closeDrawer(level = drawers.stack.length - 1) { drawers.stack.splice(level) }
export function closeAllDrawers() { drawers.stack = [] }

// —— 确认弹窗 ——
export const confirmState = reactive({ open: false, title: '', body: '', confirmText: '', danger: false, resolve: null })
export function askConfirm({ title, body, confirmText, danger = false }) {
  return new Promise((resolve) => Object.assign(confirmState, { open: true, title, body, confirmText, danger, resolve }))
}
export function settleConfirm(ok) {
  confirmState.resolve?.(ok)
  confirmState.open = false
}

// —— 轻提示：3 秒后消失 ——
export const toasts = reactive({ list: [] })
let toastId = 0
export function toast(text, action) {
  const id = ++toastId
  toasts.list.push({ id, text, action })
  setTimeout(() => { toasts.list = toasts.list.filter((x) => x.id !== id) }, 3000)
}

watch(() => drawers.stack.length, (n) => document.body.classList.toggle('has-drawer', n > 0))
