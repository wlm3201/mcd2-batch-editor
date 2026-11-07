<script setup>
import { computed } from 'vue'
import { iconUrl } from '../lib/files.js'
import {
  t,
  pieceLabel,
  classLabel,
  rarityLabel,
  kindLabel,
  classColor,
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
})
const emit = defineEmits([
  'tier',
  'remove',
  'applyFx',
  'setEnchant',
  'clearEnchant',
  'applyEnchant',
  'hoverTargets',
  'copy',
  'delete',
])
const candidateEnchants = computed(() =>
  props.enchOptions.filter((e) => e.effect !== props.enchantDraft?.effect),
)

function enchInfo() {
  return props.enchOptions.find((e) => e.effect === props.enchantDraft?.effect) || {}
}
function enchTierText() {
  const info = enchInfo()
  return info.tiers?.find((t) => t.tier === props.enchantDraft?.tier)?.zhText || info.zhDesc || ''
}
</script>

<template>
  <div class="card item-detail">
    <!-- multi-select mode -->
    <template v-if="multi">
      <div class="name-row" style="margin-bottom: 8px">
        <h2 style="flex: 1">{{ multiItems.length }} {{ t('detail.selected') }}</h2>
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
            }}<template v-if="gear.soulstorm"> · {{ t('detail.storm') }}</template>
            <template v-if="gear.enchant"> · {{ t('detail.ench') }}</template> · {{ gear.totalFx }}
            {{ t('detail.fxCount') }} · {{ t('detail.level') }} {{ gear.power ?? '?' }}
            <template v-if="gear.equipped"> · {{ t('detail.equipped') }}</template>
            <template v-if="gear.stock"> · {{ t('detail.stock') }}</template>
          </div>
        </div>
        <div class="detail-actions">
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
            @click="emit('applyEnchant', enchantDraft ? 'set' : 'clear')"
            @mouseenter="emit('hoverTargets', true)"
            @mouseleave="emit('hoverTargets', false)"
          >
            {{ t('detail.applyEnchant') }} ×{{ identicalCount }}
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
      </div>
    </template>

    <!-- shared: own effects + rolled effects + enchantment -->
    <template v-if="ownFx && ownFx.length">
      <h3>{{ t('detail.ownFx') }}</h3>
      <div v-for="r in ownFx" :key="r.template" class="fx own">
        <img v-if="r.icon" class="ico" :src="iconUrl(r.icon)" alt="" />
        <div class="n" :title="r.name">
          {{ r.name }}
          <div v-if="r.description" class="t">{{ r.description }}</div>
        </div>
      </div>
    </template>

    <h3>
      {{ t(multi ? 'detail.shared' : 'detail.effects') }}
      <span
        >{{ rows.length
        }}<template v-if="gear"> / {{ unlocked ? '∞' : gear.rollLimit }}</template></span
      >
    </h3>
    <div v-if="!rows.length" class="muted">{{ t('detail.noRolled') }}</div>
    <div v-for="(r, k) in rows" :key="r.effect" class="fx">
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

    <h3>{{ t('detail.enchant') }}</h3>
    <div v-if="!enchOptions.length" class="muted">
      {{ gear?.kind === 'Artifact' ? t('detail.noEnchantArtifact') : t('detail.noEnchant') }}
    </div>
    <template v-else>
        <div v-if="enchantDraft" class="fx ench">
          <img v-if="enchInfo().icon" class="ico" :src="iconUrl(enchInfo().icon)" alt="" />
          <div class="n" :title="(enchInfo().slotInfo || '') + ' ' + (enchInfo().name || '')">
            {{ enchInfo().zhName || enchInfo().name || '' }}
            <div class="t">{{ enchTierText() }}</div>
          </div>
          <button
            v-for="tr in ['I', 'II', 'III']"
            :key="tr"
            class="tierbtn"
            :class="{ on: enchantDraft.tier === tr }"
            :disabled="!enchInfo().tiers?.some((t) => t.tier === tr)"
            @click="emit('setEnchant', enchantDraft.effect, tr)"
          >
            {{ tr }}
          </button>
          <button class="danger" :aria-label="t('common.remove')" @click="emit('clearEnchant')">
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
      <section class="enchant-candidates" :aria-label="t('detail.candidateEnchants')">
        <h4 class="enchant-heading">{{ t('detail.candidateEnchants') }}</h4>
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
              @click="emit('setEnchant', e.effect, e.tiers.at(-1).tier)"
            >
              ＋
            </button>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
