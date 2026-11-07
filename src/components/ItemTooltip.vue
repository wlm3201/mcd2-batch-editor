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
      ><template v-if="item.enchant"> · {{ t('detail.ench') }}</template> · {{ item.totalFx }}
      {{ t('detail.fxCount') }} · {{ t('detail.level') }} {{ item.power ?? '?'
      }}<template v-if="item.equipped"> · {{ t('detail.equipped') }}</template>
    </div>
    <div v-for="r in item.ownFx" :key="r.template" class="tsub tooltip-effect">
      {{ r.name }}<template v-if="r.description">：{{ r.description }}</template>
    </div>
  </div>
</template>
