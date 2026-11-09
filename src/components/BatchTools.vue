<script setup>
import { ref, watch } from 'vue'
import { t, rarityLabel } from '../lib/i18n.js'

const props = defineProps({
  counts: Object, // slotKey -> number of owned items (shop excluded)
})
const emit = defineEmits(['op'])

const SLOTS = [
  ['melee', 'batch.slotMelee'],
  ['ranged', 'batch.slotRanged'],
  ['helmet', 'batch.slotHelmet'],
  ['chest', 'batch.slotChest'],
  ['leggings', 'batch.slotLeggings'],
  ['boots', 'batch.slotBoots'],
  ['artifact', 'batch.slotArtifact'],
  ['talisman', 'batch.slotTalisman'],
  ['book', 'batch.slotBook'],
]
const slot = ref('melee')
const rarity = ref('Unique')
const power = ref(150)
const talismanLevel = ref(3)

const GEAR_SLOTS = new Set(['melee', 'ranged', 'helmet', 'chest', 'leggings', 'boots'])
const noRarity = () => slot.value === 'talisman' || slot.value === 'book'
const isTalisman = () => slot.value === 'talisman'
const isBook = () => slot.value === 'book'
const isArtifact = () => slot.value === 'artifact'
const rarityOptions = () =>
  isArtifact() ? ['Common', 'Rare', 'Special'] : ['Common', 'Rare', 'Special', 'Unique']

// keep rarity/power in valid range when switching slots
watch(slot, () => {
  if (isArtifact() && rarity.value === 'Unique') rarity.value = 'Special'
})

function go(op, value) {
  emit('op', { op, slot: slot.value, value })
}
function heroOp(op, value) {
  emit('op', { op, slot: '', value })
}
function clearAll() {
  const n = props.counts[slot.value] || 0
  const slotName = t(SLOTS.find((s) => s[0] === slot.value)[1])
  if (
    window.confirm(
      `${t('batch.confirmClear')} ${slotName}${t('batch.confirmClearMsg')} ${n} ${t('batch.confirmClearEnd')}`,
    )
  )
    go('clear')
}
</script>

<template>
  <div class="batch-layout">
    <section class="card hero-tools">
      <h2>{{ t('batch.hero') }}</h2>
      <div class="acts">
        <button class="primary" @click="heroOp('maxStats')">{{ t('batch.maxStats') }}</button>
        <button :title="t('batch.questsTip')" @click="heroOp('completeQuests')">
          {{ t('batch.quests') }}
        </button>
        <button @click="heroOp('completeSideQuests')">{{ t('batch.sideQuests') }}</button>
        <button @click="heroOp('completeAchievements')">{{ t('batch.achievements') }}</button>
        <button :title="t('batch.travelTip')" @click="heroOp('unlockTravel')">
          {{ t('batch.travel') }}
        </button>
        <button @click="heroOp('discoverMap')">{{ t('batch.map') }}</button>
      </div>
    </section>
    <section class="card">
      <h2>{{ t('batch.gear') }}</h2>
      <small>{{ t('batch.scope') }}</small>
      <h3></h3>
      <div class="chips">
        <button
          v-for="[key, label] in SLOTS"
          :key="key"
          class="chip"
          :class="{ on: slot === key }"
          @click="slot = key"
        >
          {{ t(label) }} <i>{{ counts[key] || 0 }}</i>
        </button>
      </div>

      <div class="acts">
        <button class="danger" :disabled="!counts[slot]" @click="clearAll">
          {{ t('batch.clear') }}
        </button>
        <button v-if="GEAR_SLOTS.has(slot)" @click="go('add')">{{ t('batch.addUnique') }}</button>
        <button v-if="slot === 'artifact'" @click="go('add')">{{ t('batch.addArtifact') }}</button>
        <button v-if="isTalisman()" @click="go('add')">{{ t('batch.addTalisman') }}</button>
        <button v-if="isBook()" @click="go('add')">{{ t('batch.addBook') }}</button>
      </div>

      <div v-if="noRarity()" class="muted">{{ t('batch.noRarity') }}</div>
      <div v-else class="acts">
        <button
          v-for="r in rarityOptions()"
          :key="r"
          class="chip"
          :class="{ on: rarity === r }"
          @click="rarity = r"
        >
          {{ rarityLabel(r) }}
        </button>
        <button class="primary" @click="go('rarity', rarity)">
          {{ t('batch.setAll') }} {{ rarityLabel(rarity) }}
        </button>
      </div>

      <div v-if="noRarity()" class="muted">{{ t('batch.noStorm') }}</div>
      <div v-else class="acts">
        <button class="primary" @click="go('storm', true)">{{ t('batch.addStorm') }}</button>
        <button class="danger" @click="go('storm', false)">{{ t('batch.clearStorm') }}</button>
      </div>

      <div v-if="isBook()" class="muted">{{ t('batch.noLevel') }}</div>
      <div v-else class="acts">
        <input
          v-if="isTalisman()"
          v-model.number="talismanLevel"
          type="number"
          min="1"
          max="3"
          :aria-label="t('batch.talismanLevel')"
          style="width: 110px"
        />
        <input
          v-else
          v-model.number="power"
          :aria-label="t('batch.power')"
          type="number"
          min="0"
          max="1000000"
          style="width: 110px"
        />
        <button
          class="primary"
          @click="go(isTalisman() ? 'level' : 'power', isTalisman() ? talismanLevel : power)"
        >
          {{ t('batch.setLevel') }}
        </button>
      </div>
    </section>
  </div>
</template>
