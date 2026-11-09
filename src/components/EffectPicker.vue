<script setup>
import { iconUrl } from '../lib/files.js'
import { t, poolLabel, poolColor, slotLabel, slotColor } from '../lib/i18n.js'

defineProps({
  groups: Array,
})
const emit = defineEmits(['add', 'remove'])

</script>

<template>
  <div class="candidates">
    <p v-if="!groups.length" class="muted">{{ t('picker.empty') }}</p>
    <div v-for="g in groups" :key="g.key" class="catgroup">
      <h4>
        {{ g.zh }} <small>{{ g.effects.length }}</small>
      </h4>
      <div v-for="c in g.effects" :key="c.id || c.effect" class="fx" :class="{ taken: c.taken }">
        <img v-if="c.icon" class="ico" :src="iconUrl(c.icon)" alt="" />
        <div class="n">
          <span class="fxname">{{ c.zhName || c.name }}</span>
          <span
            v-for="slot in c.slots"
            :key="'slot-' + slot"
            class="tag slot-tag"
            :class="{ here: c.matchedSlots?.includes(slot) }"
            :style="c.matchedSlots?.includes(slot) ? { '--tag-color': slotColor(slot) } : undefined"
            :title="t('detail.slots')"
            >{{ slotLabel(slot) }}</span
          >
          <span
            v-for="p in c.pools"
            :key="p"
            class="tag"
            :title="t('detail.pools')"
            :class="{ here: c.matched?.includes(p) }"
            :style="c.matched?.includes(p) ? { '--tag-color': poolColor(p) } : undefined"
            >{{ poolLabel(p) }}</span
          >
          <div class="t">{{ c.desc }}</div>
        </div>
        <button
          v-if="!c.taken"
          class="tierbtn add"
          :disabled="c.disabled"
          :title="t('picker.add')"
          @click="emit('add', c.effect, c.tier, c)"
        >
          ＋
        </button>
        <button
          v-else
          class="tierbtn remove"
          :title="t('common.remove')"
          @click="emit('remove', c.effect)"
        >
          ✕
        </button>
      </div>
    </div>
  </div>
</template>
