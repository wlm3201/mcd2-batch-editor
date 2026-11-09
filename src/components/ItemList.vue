<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { iconUrl } from '../lib/files.js'
import { t } from '../lib/i18n.js'

const props = defineProps({
  groups: Array,
  active: Number,
  selected: Set,
  total: Number,
  classes: Array,
  filters: Object,
  highlight: Set,
})
const emit = defineEmits(['open', 'filter', 'select', 'marquee'])

const listEl = ref(null)
const marquee = ref(null)
let drag = null
let suppressClick = false

const boxOf = (x0, y0, x1, y1) => ({
  left: Math.min(x0, x1),
  top: Math.min(y0, y1),
  right: Math.max(x0, x1),
  bottom: Math.max(y0, y1),
})
function tilesIn(box) {
  const hits = new Set()
  for (const tile of listEl.value?.querySelectorAll('.tile[data-gear-index]') || []) {
    const r = tile.getBoundingClientRect()
    if (r.right > box.left && r.left < box.right && r.bottom > box.top && r.top < box.bottom)
      hits.add(Number(tile.dataset.gearIndex))
  }
  return hits
}
function syncSelection(hits) {
  let ids
  if (drag.mode === 'toggle') {
    const next = new Set(drag.base)
    for (const id of hits) {
      if (next.has(id)) next.delete(id)
      else next.add(id)
    }
    ids = [...next]
  } else {
    ids = [...new Set([...drag.base, ...hits])]
  }
  const key = ids.slice().sort((a, b) => a - b).join(',')
  if (key === drag.lastKey) return
  drag.lastKey = key
  emit('select', ids, false)
}
function onPointerDown(event) {
  if (event.button !== 0 || event.pointerType === 'touch') return
  drag = {
    x0: event.clientX,
    y0: event.clientY,
    mode: event.ctrlKey || event.metaKey ? 'toggle' : event.shiftKey ? 'add' : 'replace',
    active: false,
  }
  window.addEventListener('pointermove', onPointerMove, true)
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointercancel', onPointerUp)
}
function onPointerMove(event) {
  if (!drag) return
  if (!drag.active && Math.hypot(event.clientX - drag.x0, event.clientY - drag.y0) < 5) return
  if (!drag.active) {
    drag.active = true
    drag.base = drag.mode === 'replace' ? new Set() : new Set(props.selected || [])
    drag.lastKey = null
    emit('marquee', true)
    syncSelection(new Set())
  }
  const box = boxOf(drag.x0, drag.y0, event.clientX, event.clientY)
  marquee.value = {
    left: box.left,
    top: box.top,
    width: box.right - box.left,
    height: box.bottom - box.top,
  }
  syncSelection(tilesIn(box))
}
function onPointerUp(event) {
  stopDrag()
  if (!drag?.active) {
    drag = null
    return
  }
  emit('marquee', false)
  suppressClick = true
  setTimeout(() => (suppressClick = false), 0)
  const box = boxOf(drag.x0, drag.y0, event.clientX, event.clientY)
  const indices = tilesIn(box)
  marquee.value = null
  syncSelection(indices)
  drag = null
}
function stopDrag() {
  window.removeEventListener('pointermove', onPointerMove, true)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)
}
function onClickCapture(event) {
  if (!suppressClick) return
  suppressClick = false
  event.preventDefault()
  event.stopPropagation()
}
onBeforeUnmount(() => {
  stopDrag()
  if (drag?.active) emit('marquee', false)
})

// deterministic color from the full archetype set: identical tags = identical color.
// Hash derives hue, saturation AND lightness so nearby hues don't collide.
function archetypeColor(it) {
  const key = [...it.archetypes].sort().join('+')
  if (!key) return '#6b7280'
  let h = 0
  for (const ch of key) h = (h * 31 + ch.charCodeAt(0)) % 360
  // secondary hash for saturation (48-82%) and lightness (42-62%)
  let h2 = 7
  for (const ch of key) h2 = (h2 * 37 + ch.charCodeAt(0)) % 360
  const s = 48 + (h2 % 35)
  const l = 42 + ((h2 * 7 + 13) % 21)
  return `hsl(${h}, ${s}%, ${l}%)`
}

function fxBorder(n) {
  return ['#6b7280', '#4a90d9', '#7fd18a', '#e6b45a', '#e06c6c', '#a855f7'][Math.min(n, 5)]
}
</script>

<template>
  <aside class="items">
    <div class="filters">
      <div class="panel-heading">
        <h2>{{ t('list.inventory') }}</h2>
        <input
          :value="filters.q"
          type="search"
          :aria-label="t('list.search')"
          :placeholder="t('list.search')"
          @input="emit('filter', { q: $event.target.value })"
        />
      </div>
      <div class="chips">
        <button
          v-for="c in classes"
          :key="c.value"
          class="chip"
          :class="{ on: filters.cls === c.value }"
          @click="emit('filter', { cls: c.value })"
        >
          {{ c.label }} <i>{{ c.count }}</i>
        </button>
      </div>
    </div>

    <div
      ref="listEl"
      class="list"
      :class="{ 'marquee-active': marquee }"
      @pointerdown="onPointerDown"
      @click.capture="onClickCapture"
    >
      <template v-for="g in groups" :key="g.key">
        <div class="grp">
          <img v-if="g.icon" :src="iconUrl(g.icon)" alt="" />
          <b>{{ g.title }}</b>
          <span>{{ g.items.length }}</span>
        </div>
        <div class="grid">
          <button
            v-for="it in g.items"
            :key="g.key + it.index"
            class="tile"
            :data-gear-index="it.index"
            :aria-label="it.zhName || it.name"
            :aria-pressed="selected?.has(it.index)"
            :class="[
              {
                sel: active === it.index,
                multi: selected?.size > 1 && selected?.has(it.index),
                hl: highlight?.has(it.index),
              },
            ]"
            :style="{ borderColor: archetypeColor(it) }"
            @click="emit('open', it.index, $event.ctrlKey || $event.metaKey)"
          >
            <img v-if="it.icon" :src="iconUrl(it.icon)" alt="" />
            <span
              class="fxcount"
              :class="{ enchanted: it.enchant }"
              :style="{
                borderColor: fxBorder(it.totalFx),
                color: it.enchant ? '#fff' : fxBorder(it.totalFx),
                background: it.enchant ? fxBorder(it.totalFx) : 'var(--panel)',
              }"
              >{{ it.totalFx }}</span
            >
            <span class="tile-name">{{ it.zhName || it.name }}</span>
          </button>
        </div>
      </template>
      <div v-if="!groups.length || !groups.some((g) => g.items.length)" class="grp">
        {{ t(total ? 'list.noMatch' : 'list.empty') }}
      </div>
    </div>
    <Teleport to="body">
      <div
        v-if="marquee"
        class="marquee"
        :style="{
          left: marquee.left + 'px',
          top: marquee.top + 'px',
          width: marquee.width + 'px',
          height: marquee.height + 'px',
        }"
      ></div>
    </Teleport>
  </aside>
</template>
