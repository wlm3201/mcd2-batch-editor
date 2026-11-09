<script setup>
import { computed, ref } from 'vue'
import { iconUrl } from '../lib/files.js'
import {
  t,
  pieceLabel,
  classLabel,
  rarityLabel,
  kindLabel,
  classColor,
  poolColor,
  poolLabel,
  slotLabel,
  slotColor,
} from '../lib/i18n.js'

const props = defineProps({
  gear: Object,
  multi: Boolean,
  multiItems: Array,
  rows: Array,
  ownFx: Array,
  identicalCount: Number,
  unlocked: Boolean,
  enchOptions: Array,
  enchantDraft: Object,
  extraEnchants: Array,
})
const emit = defineEmits([
  'tier',
  'remove',
  'applyFx',
  'setEnchant',
  'applyEnchant',
  'hoverTargets',
  'copy',
  'delete',
  'pickOwn',
  'setRarity',
  'addOwn',
  'removeOwn',
  'removeExtra',
  'changeExtraTier',
])

const RARITIES = ['Common', 'Rare', 'Special', 'Unique']
const ENCHANT_SLOT_FILTERS = [
  ['melee', 'batch.slotMelee'],
  ['ranged', 'batch.slotRanged'],
  ['armor', 'detail.enchantArmor'],
]
const activeEnchantSlot = ref(null)
function toggleEnchantSlot(kind) {
  activeEnchantSlot.value = activeEnchantSlot.value === kind ? null : kind
}
function matchesEnchantSlot(e, filter) {
  const slots = e.slots || []
  if (filter === 'melee') return slots.includes('melee-weapon')
  if (filter === 'ranged') return slots.includes('ranged-weapon')
  if (filter === 'armor') return slots.some((s) => s.startsWith('armor-'))
  return true
}
const candidateEnchants = computed(() => {
  const filter = props.unlocked ? activeEnchantSlot.value : null
  const taken = props.unlocked
    ? new Set()
    : new Set([props.enchantDraft?.effect, ...(props.extraEnchants || []).map((e) => e.effect)])
  return props.enchOptions.filter(
    (e) => !taken.has(e.effect) && (!filter || matchesEnchantSlot(e, filter)),
  )
})
const rarityTargets = computed(() =>
  props.multi ? props.multiItems || [] : props.gear ? [props.gear] : [],
)
const commonRarity = computed(() => {
  const list = rarityTargets.value
  return list.length && list.every((g) => g.rarity === list[0].rarity) ? list[0].rarity : null
})
const canBeUnique = computed(() => rarityTargets.value.some((g) => g.canBeUnique))
</script>

<template>
  <div class="card item-detail">
    <div class="detail-head">
    <!-- multi-select mode -->
    <template v-if="multi">
      <div class="name-row" style="margin-bottom: 8px">
        <h2 style="flex: 1">{{ multiItems.length }} {{ t('detail.selected') }}</h2>
        <button
          v-for="r in RARITIES"
          :key="r"
          class="tierbtn"
          :class="{ on: commonRarity === r }"
          :disabled="r === 'Unique' && !canBeUnique"
          :title="r === 'Unique' && !canBeUnique ? t('detail.noUnique') : rarityLabel(r)"
          @click="emit('setRarity', r)"
        >
          {{ rarityLabel(r) }}
        </button>
        <button
          class="iconbtn"
          :title="t('common.copy')"
          :aria-label="t('common.copy')"
          @click="emit('copy')"
        >
          ⧉
        </button>
        <button
          class="iconbtn danger"
          :title="t('common.delete')"
          :aria-label="t('common.delete')"
          @click="emit('delete')"
        >
          ✕
        </button>
      </div>
      <div class="multi-grid">
        <div v-for="g in multiItems" :key="g.index" class="multi-tile" :data-gear-index="g.index">
          <img v-if="g.icon" :src="iconUrl(g.icon)" alt="" />
        </div>
      </div>
    </template>
    <template v-else>
      <div class="head">
        <img v-if="gear.icon" class="big" :src="iconUrl(gear.icon)" alt="" />
        <h2 class="gear-title">{{ gear.zhName || gear.name }}</h2>
        <div class="headinfo">
          <div class="tags">
            <span class="piecetag" :style="{ '--tag-color': slotColor(gear.slotKey) }">{{
              gear.piece ? pieceLabel(gear.piece) : kindLabel(gear.kind)
            }}</span>
            <span
              v-for="a in gear.archetypes"
              :key="a"
              class="archtag"
              :style="{ '--tag-color': classColor(a) }"
              >{{ classLabel(a) }}</span
            >
          </div>
          <div class="sub">
            {{ rarityLabel(gear.rarity)
            }}<template v-if="gear.soulstorm"> · {{ t('detail.storm') }}</template
            > · {{ t('detail.level') }} {{ gear.power ?? '?' }}
            <template v-if="gear.equipped"> · {{ t('detail.equipped') }}</template>
            <template v-if="gear.stock"> · {{ t('detail.stock') }}</template>
          </div>
        </div>
        <div class="detail-actions">
          <div class="action-row">
            <button
              v-for="r in RARITIES"
              :key="r"
              class="tierbtn"
              :class="{ on: commonRarity === r }"
              :disabled="r === 'Unique' && !canBeUnique"
              :title="r === 'Unique' && !canBeUnique ? t('detail.noUnique') : rarityLabel(r)"
              @click="emit('setRarity', r)"
            >
              {{ rarityLabel(r) }}
            </button>
            <button
              class="iconbtn"
              :title="t('common.copy')"
              :aria-label="t('common.copy')"
              @click="emit('copy')"
            >
              ⧉
            </button>
            <button
              class="iconbtn danger"
              :title="t('common.delete')"
              :aria-label="t('common.delete')"
              @click="emit('delete')"
            >
              ✕
            </button>
          </div>
          <div class="action-row">
            <button
              class="apply-btn"
              :disabled="identicalCount < 2"
              :title="t('detail.applyTip')"
              @click="emit('applyFx')"
              @mouseenter="emit('hoverTargets', true)"
              @mouseleave="emit('hoverTargets', false)"
            >
              {{ t('detail.apply') }} ×{{ identicalCount }}
            </button>
            <button
              class="apply-btn"
              :disabled="identicalCount < 2 || !enchOptions.length"
              :title="t('detail.enchantTip')"
              @click="emit('applyEnchant')"
              @mouseenter="emit('hoverTargets', true)"
              @mouseleave="emit('hoverTargets', false)"
            >
              {{ t('detail.applyEnchant') }} ×{{ identicalCount }}
            </button>
          </div>
        </div>
      </div>
      <div v-if="gear?.desc" class="gear-desc">{{ gear.desc }}</div>
    </template>
    </div>

    <div class="detail-body">
    <!-- shared: own effects + rolled effects + enchantment -->
    <h3 class="ownfx-heading">
      {{ t('detail.ownFx') }} <span>{{ ownFx?.filter((r) => !r.talisman).length || 0 }}</span>
      <button
        v-if="unlocked"
        class="tierbtn add"
        :title="t('detail.addOwn')"
        @click="emit('addOwn')"
      >
        {{ t('unique.append') }}
      </button>
    </h3>
    <div
      v-for="(r, k) in ownFx || []"
      v-show="!r.talisman"
      :key="r.template + '-' + k"
      class="fx own"
    >
      <img v-if="r.icon" class="ico" :src="iconUrl(r.icon)" alt="" />
      <div class="n" :title="r.name">
        {{ r.name }}
        <div v-if="r.description" class="t">{{ r.description }}</div>
      </div>
      <button
        v-if="unlocked"
        class="tierbtn"
        :title="t('unique.pick')"
        :aria-label="t('unique.pick')"
        @click="emit('pickOwn', k)"
      >
        {{ t('unique.swap') }}
      </button>
      <button
        v-if="unlocked"
        class="danger"
        :aria-label="t('common.remove') + ' ' + r.name"
        @click="emit('removeOwn', k, r.template, r.occurrence)"
      >
        ✕
      </button>
    </div>

    <h3>
      {{ t(multi ? 'detail.shared' : 'detail.effects') }}
      <span
        >{{ rows.filter((r) => !r.talisman).length
        }}<template v-if="gear"> / {{ unlocked ? '∞' : gear.rollLimit }}</template></span
      >
    </h3>
    <div v-if="!rows.length" class="muted">{{ t('detail.noRolled') }}</div>
    <div v-for="(r, k) in rows" :key="r.effect + '-' + k" class="fx">
      <img v-if="r.icon" class="ico" :src="iconUrl(r.icon)" alt="" />
      <div class="n" :title="r.name">
        {{ r.zhName || r.name }}
        <span
          v-for="slot in r.slots"
          :key="slot"
          class="tag slot-tag"
          :title="t('detail.slots')"
          :class="{ here: r.matchedSlots?.includes(slot) }"
          :style="r.matchedSlots?.includes(slot) ? { '--tag-color': slotColor(slot) } : undefined"
          >{{ slotLabel(slot) }}</span
        >
        <span
          v-for="p in r.pools || []"
          :key="p"
          class="tag"
          :title="t('detail.pools')"
          :class="{ here: r.matched?.includes(p) }"
          :style="r.matched?.includes(p) ? { '--tag-color': poolColor(p) } : undefined"
          >{{ poolLabel(p) }}</span
        >
        <div class="t">{{ r.zhText }}</div>
      </div>
      <button
        v-for="tr in ['I', 'II', 'III']"
        :key="tr"
        class="tierbtn"
        :class="{ on: r.tier === tr }"
        :disabled="!r.tierChoices.includes(tr)"
        @click="emit('tier', k, tr)"
      >
        {{ tr }}
      </button>
      <button
        class="danger"
        :aria-label="t('common.remove') + ' ' + (r.zhName || r.name)"
        @click="emit('remove', k)"
      >
        ✕
      </button>
    </div>

    <h3>{{ t('detail.enchant') }}<span v-if="gear?.enchantCount > 1"> ×{{ gear.enchantCount }}</span></h3>
    <div v-if="!enchOptions.length" class="muted">
      {{ gear?.kind === 'Artifact' ? t('detail.noEnchantArtifact') : t('detail.noEnchant') }}
    </div>
    <template v-else>
        <div v-if="enchantDraft" class="fx ench">
          <img v-if="enchantDraft.icon" class="ico" :src="iconUrl(enchantDraft.icon)" alt="" />
          <div class="n" :title="enchantDraft.name">
            {{ enchantDraft.zhName || enchantDraft.name }}
            <div class="t">{{ enchantDraft.desc }}</div>
          </div>
          <button
            v-for="tr in enchantDraft.tiers"
            :key="tr"
            class="tierbtn"
            :class="{ on: enchantDraft.tier === tr }"
            @click="emit('changeExtraTier', 0, enchantDraft.effect, enchantDraft.template, tr)"
          >
            {{ tr }}
          </button>
          <button
            class="danger"
            :aria-label="t('common.remove')"
            @click="emit('removeExtra', 0, enchantDraft.effect, enchantDraft.template)"
          >
            ✕
          </button>
        </div>
        <p v-else class="muted">
          {{
            t(
              multi && multiItems.some((g) => g.enchant)
                ? 'detail.mixedEnchant'
                : 'detail.addEnchantHint',
            )
          }}
        </p>
        <div v-for="(e, k) in extraEnchants || []" :key="e.effect + '-' + e.template + '-' + k" class="fx ench">
          <img v-if="e.icon" class="ico" :src="iconUrl(e.icon)" alt="" />
          <div class="n" :title="e.name">
            {{ e.zhName || e.name }}
            <div class="t">{{ e.desc }}</div>
          </div>
          <button
            v-for="tr in e.tiers"
            :key="tr"
            class="tierbtn"
            :class="{ on: e.tier === tr }"
            @click="emit('changeExtraTier', e.index, e.effect, e.template, tr, e.occurrence)"
          >
            {{ tr }}
          </button>
          <button
            class="danger"
            :aria-label="t('common.remove') + ' ' + (e.zhName || e.name)"
            @click="emit('removeExtra', e.index, e.effect, e.template, e.occurrence)"
          >
            ✕
          </button>
        </div>
      <section class="enchant-candidates" :aria-label="t('detail.candidateEnchants')">
        <div class="enchant-heading">
          <span>{{ t('detail.candidateEnchants') }}</span>
          <div v-if="unlocked" class="enchant-slot-filters">
            <button
              v-for="[kind, label] in ENCHANT_SLOT_FILTERS"
              :key="kind"
              class="tierbtn"
              :class="{ on: activeEnchantSlot === kind }"
              :aria-pressed="activeEnchantSlot === kind"
              type="button"
              @click="toggleEnchantSlot(kind)"
            >
              {{ t(label) }}
            </button>
          </div>
        </div>
        <p v-if="!candidateEnchants.length" class="muted">{{ t('detail.noOtherEnchant') }}</p>
        <div class="enchlist">
          <div v-for="e in candidateEnchants" :key="e.effect" class="fx">
            <img v-if="e.icon" class="ico" :src="iconUrl(e.icon)" alt="" />
            <div class="n" :title="e.slotInfo + ' ' + e.name">
              {{ e.zhName || e.name }}
              <div class="t">{{ e.zhDesc }}</div>
            </div>
            <button
              class="tierbtn add"
              :title="t('picker.add')"
              @click="emit('setEnchant', e.effect, e.tiers.at(-1).tier, unlocked)"
            >
              ＋
            </button>
          </div>
        </div>
      </section>
    </template>
    </div>
  </div>
</template>
