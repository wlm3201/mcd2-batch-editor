<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { iconUrl } from '../lib/files.js'
import { t, categoryLabel } from '../lib/i18n.js'

const props = defineProps({ options: Array })
const emit = defineEmits(['select', 'close'])
const q = ref('')
function onKey(e) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
const FILTERS = [
  ['melee', 'batch.slotMelee'],
  ['ranged', 'batch.slotRanged'],
  ['helmet', 'batch.slotHelmet'],
  ['chest', 'batch.slotChest'],
  ['leggings', 'batch.slotLeggings'],
  ['boots', 'batch.slotBoots'],
]
const CATEGORIES = ['offensive', 'defensive', 'utility']
const activeSlot = ref(null)
const activeCategory = ref(null)
function toggleSlot(slot) {
  activeSlot.value = activeSlot.value === slot ? null : slot
}
function toggleCategory(category) {
  activeCategory.value = activeCategory.value === category ? null : category
}
function visibleItems(o) {
  const all = o.items || []
  if (!activeSlot.value) return all
  return all.filter((it) => it.slot === activeSlot.value)
}
function fromLabel(o) {
  const list = visibleItems(o)
  if (!list.length) return ''
  return list.length > 1 ? `${list[0].name} +${list.length - 1}` : list[0].name
}
function fromTitle(o) {
  return visibleItems(o).map((it) => it.name).join(' / ')
}
function fromIcon(o) {
  return visibleItems(o)[0]?.icon || ''
}
const filtered = computed(() => {
  const text = q.value.trim().toLowerCase()
  return props.options.filter((o) => {
    if (activeSlot.value && !(o.slots || []).includes(activeSlot.value)) return false
    if (activeCategory.value && (o.category || 'other') !== activeCategory.value) return false
    if (!text) return true
    return [o.name, o.description, o.from, ...o.itemNames].some((v) =>
      String(v || '').toLowerCase().includes(text),
    )
  })
})
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('close')">
    <div class="modal-card" role="dialog" aria-modal="true" :aria-label="t('unique.title')">
      <div class="modal-head">
        <h3>{{ t('unique.title') }}</h3>
        <button class="iconbtn" :aria-label="t('common.close')" @click="emit('close')">✕</button>
      </div>
      <div class="unique-controls">
        <input
          v-model="q"
          type="search"
          :placeholder="t('unique.search')"
          :aria-label="t('unique.search')"
        />
        <div class="unique-filters">
          <div class="filter-group">
            <button
              v-for="[slot, label] in FILTERS"
              :key="slot"
              class="tierbtn"
              :class="{ on: activeSlot === slot }"
              :aria-pressed="activeSlot === slot"
              type="button"
              @click="toggleSlot(slot)"
            >
              {{ t(label) }}
            </button>
          </div>
          <div class="filter-group category-filters">
            <button
              v-for="c in CATEGORIES"
              :key="c"
              class="tierbtn"
              :class="{ on: activeCategory === c }"
              :aria-pressed="activeCategory === c"
              type="button"
              @click="toggleCategory(c)"
            >
              {{ categoryLabel(c) }}
            </button>
          </div>
        </div>
      </div>
      <div class="unique-list">
        <p v-if="!filtered.length" class="muted">{{ t('unique.empty') }}</p>
        <button
          v-for="o in filtered"
          :key="o.template"
          class="unique-card"
          type="button"
          @click="emit('select', o)"
        >
          <div class="unique-effect">
            <img v-if="o.icon" class="unique-ico" :src="iconUrl(o.icon)" alt="" />
            <div class="unique-text">
              <div class="unique-name">{{ o.name }}</div>
              <div class="unique-desc">{{ o.description }}</div>
            </div>
          </div>
          <div class="unique-from">
            <span class="unique-from-name" :title="fromTitle(o)">{{ fromLabel(o) }}</span>
            <img v-if="fromIcon(o)" :src="iconUrl(fromIcon(o))" alt="" />
          </div>
        </button>
      </div>
    </div>
  </div>
</template>
