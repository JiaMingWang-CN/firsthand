<script setup>
import { ref, computed, inject } from 'vue'
import { P } from '../lib/sim.js'
import { openDrawer } from '../lib/store.js'
import Avatar from './Avatar.vue'
import PersonaCard from './PersonaCard.vue'

const props = defineProps({ pid: String, noHover: Boolean })
const inDrawer = inject('inDrawer', false)
const p = computed(() => P[props.pid])
const show = ref(false)
const above = ref(false)
const el = ref(null)
let timer = 0
function enter() {
  if (props.noHover) return
  clearTimeout(timer)
  timer = setTimeout(() => {
    const r = el.value?.getBoundingClientRect()
    above.value = r ? r.bottom > window.innerHeight - 220 : false
    show.value = true
  }, 350)
}
function leave() { clearTimeout(timer); show.value = false }
function open() {
  leave()
  openDrawer({ type: 'persona', pid: props.pid }, { fromDrawer: inDrawer })
}
</script>

<template>
  <span class="chip-wrap" ref="el" @mouseenter="enter" @mouseleave="leave">
    <button class="pchip" type="button" @click.stop="open" @focus="enter" @blur="leave" :aria-label="`打开人物档案：${p.realname}（模拟）`">
      <Avatar :pid="pid" size="sm" />{{ p.realname }}
    </button>
    <Transition name="fade">
      <div v-if="show" class="hovercard" :class="{ above }" role="tooltip">
        <PersonaCard :pid="pid" compact />
      </div>
    </Transition>
  </span>
</template>

<style scoped>
.chip-wrap { position: relative; display: inline-flex; }
.hovercard {
  position: absolute; left: 0; top: calc(100% + 6px); z-index: 60; width: 340px;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg);
  box-shadow: var(--shadow-2); padding: var(--sp-4); pointer-events: none;
  white-space: normal; text-align: left; font-weight: 400;
}
.hovercard.above { top: auto; bottom: calc(100% + 6px); }
</style>
