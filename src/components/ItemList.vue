<script setup>
import { ref } from 'vue'
import { iconUrl } from '../lib/files.js'
import { t } from '../lib/i18n.js'
const multiPick = ref(false)

defineProps({
  groups: Array,
  active: Number,
  selected: Set,
  total: Number,
  classes: Array,
  filters: Object,
  highlight: Set,
})
const emit = defineEmits(['open', 'filter'])

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
        <button
          class="chip"
          :class="{ on: multiPick }"
          :aria-pressed="multiPick"
          :title="t('list.multiTip')"
          @click="multiPick = !multiPick"
        >
          {{ t('list.multi') }}
        </button>
      </div>
      <input
        :value="filters.q"
        type="search"
        :aria-label="t('list.search')"
        :placeholder="t('list.search')"
        @input="emit('filter', { q: $event.target.value })"
      />
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

    <div class="list">
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
            @click="emit('open', it.index, multiPick || $event.ctrlKey || $event.metaKey)"
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
  </aside>
</template>
