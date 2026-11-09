<script setup>
import { computed, ref, watchPostEffect } from 'vue'
import {
  t,
  classLabel,
  pieceLabel,
  rarityLabel,
  kindLabel,
  classColor,
  slotColor,
} from '../lib/i18n.js'
import { iconUrl } from '../lib/files.js'

const props = defineProps({ items: Array })
const index = ref(null)
const pointer = ref({ x: 0, y: 0 })
const box = ref(null)
const item = computed(() =>
  index.value == null ? null : props.items.find((g) => g.index === index.value),
)

function hide() {
  index.value = null
}
function track(event) {
  const tile = event.pointerType !== 'touch' && event.target.closest('[data-gear-index]')
  if (!tile) return hide()
  index.value = Number(tile.dataset.gearIndex)
  pointer.value = { x: event.clientX, y: event.clientY }
}
watchPostEffect(() => {
  if (!box.value || !item.value) return
  const { x, y } = pointer.value
  const { width, height } = box.value.getBoundingClientRect()
  const clamp = (v, max) => Math.max(6, Math.min(v, max - 6))
  box.value.style.left =
    clamp(x + 14 + width <= innerWidth - 6 ? x + 14 : x - width - 14, innerWidth - width) + 'px'
  box.value.style.top =
    clamp(y + 14 + height <= innerHeight - 6 ? y + 14 : y - height - 14, innerHeight - height) +
    'px'
})
defineExpose({ track, hide })
</script>

<template>
  <div v-if="item" ref="box" class="itemtip" role="tooltip">
    <div class="tip-head">
      <div v-if="item.icon" class="tip-art">
        <img :src="iconUrl(item.icon)" alt="" />
      </div>
      <div class="tip-info">
        <div class="tname">{{ item.zhName || item.name }}</div>
        <div class="tiptags">
          <span class="piecetag" :style="{ '--tag-color': slotColor(item.slotKey) }">{{
            item.piece ? pieceLabel(item.piece) : kindLabel(item.kind)
          }}</span>
          <span
            v-for="a in item.archetypes"
            :key="a"
            class="tag here"
            :style="{ '--tag-color': classColor(a) }"
            >{{ classLabel(a) }}</span
          >
        </div>
        <div class="tsub">
          {{ rarityLabel(item.rarity)
          }}<template v-if="item.soulstorm"> · {{ t('detail.storm') }}</template
          > · {{ t('detail.level') }} {{ item.power ?? '?'
          }}<template v-if="item.equipped"> · {{ t('detail.equipped') }}</template>
        </div>
      </div>
    </div>
    <div v-if="item.desc" class="tip-desc">{{ item.desc }}</div>
    <div
      v-for="(line, i) in item.fxLines || item.ownFx"
      :key="(line.kind || 'own') + line.template + '-' + i"
      class="tsub tooltip-effect"
      :class="'fx-' + (line.kind || 'own')"
    >
      {{ line.name }}<template v-if="line.description">：{{ line.description }}</template>
    </div>
  </div>
</template>
