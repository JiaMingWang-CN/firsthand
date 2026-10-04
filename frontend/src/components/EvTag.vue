<script setup>
import { inject } from 'vue'
import { evLabel } from '../lib/sim.js'
import { openDrawer } from '../lib/store.js'
const props = defineProps({ ev: Object, text: String })
const inDrawer = inject('inDrawer', false)
function open() { openDrawer({ type: 'evidence', ev: props.ev }, { fromDrawer: inDrawer }) }
</script>

<template>
  <button class="ev" type="button" @click.stop="open">▸ {{ text || evLabel(ev) }}</button>
</template>
