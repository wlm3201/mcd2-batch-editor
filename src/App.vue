<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import ItemList from './components/ItemList.vue'
import ItemTooltip from './components/ItemTooltip.vue'
import starterText from './assets/Characterdedef7e0-da96-11f1-804d-e0a635d5cc1d.sav?raw'
import DetailPanel from './components/DetailPanel.vue'
import EffectPicker from './components/EffectPicker.vue'
import BatchTools from './components/BatchTools.vue'
import {
  CATEGORY_ORDER,
  ENCH_SLOTS,
  TIERS,
  brandItemFor,
  describeOwnEffect,
  enchantFits,
  enchantPointsFor,
  prepareCatalog,
  orderedIds,
  rolledCap,
  slotMatchesGear,
  tierFits,
} from './lib/catalog.js'
import {
  SLOT_ORDER,
  addAllOfSlot,
  clearSlot,
  maxHeroStats,
  setPowerOfSlot,
  setRarityOfSlot,
  setStormOfSlot,
  setTalismanLevelOfSlot,
} from './lib/batch.js'
import {
  completeAllAchievements,
  completeAllQuests,
  completeSideQuests,
  discoverAllMap,
  unlockAllTravel,
} from './lib/world.js'
import {
  applyEffects,
  applyEnchantment,
  duplicateItem,
  editRoll,
  gearProfiles,
  planItem,
  removeItem,
} from './lib/save.js'
import { t, locale, setLocale, setDataLabels, classLabel, categoryLabel } from './lib/i18n.js'
import { api, browserMode, download, iconUrl, loadData, poolsUrl } from './lib/files.js'
import { useSaveSession } from './lib/session.js'

const CLASS_ORDER = [
  'Fighter',
  'Ranger',
  'Mage',
  'Tank',
  'Support',
  'Summoner',
  'Trickster',
  'Utility',
]
const session = useSaveSession()
const { state, dirty, canUndo } = session
const tab = ref('edit')
const saves = shallowRef([])
const currentName = ref('')
const source = ref('')
let revision = ''
const busy = ref(true)
const saveInput = ref(null)
const error = ref('')
const conflict = ref(false)
const notice = ref('')
const dragging = ref(false)
const unlocked = ref(false)
const catalog = shallowRef(null)
const itemById = (id) => catalog.value?.items.get(id.toLowerCase())
const brandItem = computed(() => brandItemFor(catalog.value))
const gearTip = ref(null)
const welcomeItems = computed(() => {
  const available = [...(catalog.value?.items.values() || [])]
  return [
    ['SW.Item.WolfclutchHelmet', 'armor'],
    ['SW.Item.Sword_Unique1', 'melee'],
    ['SW.Item.Artifact.BlizzardStaff', 'artifact'],
  ].flatMap(([tag, kind]) => {
    const preferred = itemById(tag)
    const item = preferred?.icon
      ? preferred
      : available.find((item) => item.kind === kind && item.icon)
    return item ? [item] : []
  })
})
let rawCat, rawZh, extras, zhUnique, worldQuests
const items = shallowRef([])
const filters = reactive({ q: '', cls: 'All' })
const selectedIdx = ref(new Set())
const hoverTargets = ref(new Set())
const selectedItems = computed(() => items.value.filter((g) => selectedIdx.value.has(g.index)))
const active = computed(() => (selectedItems.value.length === 1 ? selectedItems.value[0] : null))
const isMulti = computed(() => selectedItems.value.length > 1)

function prepare() {
  if (!rawCat) return
  setDataLabels(rawCat.meta?.labels)
  catalog.value = prepareCatalog(rawCat, locale.value === 'zh' ? rawZh : {})
  refreshItems()
}
watch(
  locale,
  () => {
    document.documentElement.lang = locale.value === 'zh' ? 'zh-CN' : 'en'
    prepare()
  },
  { immediate: true },
)

async function boot() {
  try {
    ;[rawCat, rawZh, extras, zhUnique, worldQuests] = await Promise.all(
      ['catalog.json', 'zh.json', 'extras.json', 'zh-unique.json', 'world-quests.json'].map(
        loadData,
      ),
    )
    prepare()
    if (browserMode) {
      loadHero(starterText, '', 'starter')
    } else {
      saves.value = (await api('/api/saves')).saves
      if (saves.value.length) await openDisk(saves.value[0].name)
    }
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

function refreshItems() {
  items.value = gearProfiles(state.value, catalog.value).map((g) => ({
    ...g,
    ownFx: g.ownFx.map((r) =>
      describeOwnEffect(
        r,
        catalog.value,
        extras.uniqueEnchantments,
        locale.value === 'zh' ? zhUnique : null,
      ),
    ),
  }))
}

function loadHero(text, name, from, version = '') {
  session.load(text)
  currentName.value = name || `Character${state.value.body.MetaData.CharacterId}.sav`
  source.value = from
  conflict.value = false
  unlocked.value = false
  revision = version
  error.value = notice.value = ''
  Object.assign(filters, { q: '', cls: 'All' })
  hoverTargets.value = new Set()
  refreshItems()
  const first = items.value.find((g) => g.isGear && !g.stock)
  selectedIdx.value = new Set(first ? [first.index] : [])
}

const canLeave = () => !dirty.value || window.confirm(t('file.discard'))
async function openDisk(name) {
  if (!name || !canLeave()) return
  busy.value = true
  try {
    const r = await api('/api/open/' + encodeURIComponent(name))
    loadHero(r.text, r.name, 'disk', r.revision)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
function switchDisk(event) {
  const name = event.target.value
  event.target.value = source.value === 'disk' ? currentName.value : ''
  openDisk(name)
}
async function importFile(file) {
  if (!file || busy.value || !catalog.value || !canLeave()) return
  busy.value = true
  try {
    const text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(
      await file.arrayBuffer(),
    )
    loadHero(text, file.name, 'file')
  } catch (e) {
    error.value = t('file.invalid') + ' · ' + e.message
  } finally {
    busy.value = false
  }
}
function pickFile(event) {
  const file = event.target.files[0]
  event.target.value = ''
  importFile(file)
}
function dropFile(event) {
  dragging.value = false
  importFile(event.dataTransfer.files[0])
}
function beforeUnload(event) {
  if (dirty.value) {
    event.preventDefault()
    event.returnValue = ''
  }
}

function mutate(action, { resetSelection = false } = {}) {
  if (!state.value || busy.value) return
  error.value = notice.value = ''
  try {
    const { changed, result } = session.edit(action)
    const details = [...(result?.notes || []), ...(result?.skipped || [])]
    if (details.length)
      notice.value = { key: 'status.skipped', detail: details.length + ' (' + details[0] + ')' }
    else if (!changed) notice.value = { key: 'status.noChange' }
    if (changed && resetSelection) selectedIdx.value = new Set()
  } catch (e) {
    error.value = e.message
  }
  refreshItems()
}
function undo() {
  session.undo()
  selectedIdx.value = new Set()
  refreshItems()
  error.value = ''
  notice.value = { key: 'status.undone' }
}
function setActive(index, multi = false) {
  const next = multi ? new Set(selectedIdx.value) : new Set()
  if (multi && next.has(index)) next.delete(index)
  else next.add(index)
  selectedIdx.value = next
}

const filtered = computed(() =>
  items.value.filter((it) => {
    if (it.stock || !it.isGear) return false
    if (filters.cls !== 'All' && !it.archetypes.includes(filters.cls)) return false
    const q = filters.q.trim().toLowerCase()
    if (
      q &&
      !(
        it.name.toLowerCase().includes(q) ||
        (it.zhName || '').includes(filters.q.trim()) ||
        it.tag.toLowerCase().includes(q)
      )
    )
      return false
    return true
  }),
)

const groups = computed(() => {
  const list = filtered.value
  const groups = SLOT_ORDER.map((key) => ({
    key,
    title: t('batch.slot' + key[0].toUpperCase() + key.slice(1)),
    items: list.filter((it) => it.slotKey === key),
  }))
  const other = list.filter((it) => !SLOT_ORDER.includes(it.slotKey))
  if (other.length) groups.push({ key: 'other', title: t('list.other'), items: other })
  return groups.filter((g) => g.items.length)
})

const gearCount = computed(() => items.value.filter((i) => !i.stock && i.isGear).length)

const classList = computed(() => {
  const src = items.value.filter((i) => !i.stock && i.isGear)
  const counts = new Map()
  for (const it of src) for (const a of it.archetypes) counts.set(a, (counts.get(a) || 0) + 1)
  return [
    { value: 'All', label: t('common.all'), count: src.length },
    ...orderedIds(CLASS_ORDER, counts.keys())
      .filter((c) => counts.has(c))
      .map((c) => ({
        value: c,
        label: classLabel(c),
        count: counts.get(c),
      })),
  ]
})

const slotCounts = computed(() => {
  const c = {}
  for (const it of items.value) if (!it.stock) c[it.slotKey] = (c[it.slotKey] || 0) + 1
  return c
})

const draft = computed(() => {
  const targets = selectedItems.value
  if (!targets.length) return []
  return targets[0].rolled.flatMap((r) => {
    const common = targets.map((g) => g.rolled.find((v) => v.effect === r.effect))
    if (!common.every(Boolean)) return []
    return [{ effect: r.effect, tier: common.every((v) => v.tier === r.tier) ? r.tier : '' }]
  })
})
const enchantDraft = computed(() => {
  const first = selectedItems.value[0]?.enchant
  return first &&
    selectedItems.value.every(
      (g) => g.enchant?.effect === first.effect && g.enchant.tier === first.tier,
    )
    ? first
    : null
})
const samePools = computed(() => {
  const g = active.value
  if (!g?.slotKey) return []
  return items.value.filter(
    (i) =>
      i.isGear &&
      !i.stock &&
      i.slotKey === g.slotKey &&
      (unlocked.value || i.blockedRollTypes?.join() === g.blockedRollTypes?.join()) &&
      i.pools.size === g.pools.size &&
      [...i.pools].every((p) => g.pools.has(p)),
  )
})
function fitsAll(tier) {
  return selectedItems.value.every((g) => tierFits(tier, g, unlocked.value))
}
const draftRows = computed(() =>
  draft.value.map((d) => {
    const info = catalog.value.effects.get(d.effect)
    const tier = info?.tiers.get(d.tier)
    return {
      ...d,
      name: info?.name || d.effect,
      zhName: info?.zhName || '',
      zhText: d.tier ? tier?.zhText || tier?.text || '' : t('detail.mixed'),
      icon: info?.icon || '',
      slots: tier?.slots || [],
      matchedSlots: (tier?.slots || []).filter((slot) =>
        selectedItems.value.some((g) => slotMatchesGear(slot, g)),
      ),
      tierChoices: info
        ? [...info.tiers].filter(([, spec]) => fitsAll(spec)).map(([name]) => name)
        : [],
    }
  }),
)

const candidates = computed(() => {
  const targets = selectedItems.value
  if (!targets.length) return []
  const out = []
  for (const info of catalog.value.effects.values()) {
    const fit = TIERS.filter((tier) => info.tiers.has(tier) && fitsAll(info.tiers.get(tier)))
    if (!fit.length) continue
    const taken = draft.value.find((d) => d.effect === info.effect)
    const best = fit.at(-1)
    const shown = info.tiers.get(taken?.tier) || info.tiers.get(best)
    const pools = [...shown.groups].filter((pool) => pool !== 'Weapon' && pool !== 'Artifact')
    out.push({
      effect: info.effect,
      name: info.name,
      zhName: info.zhName,
      icon: info.icon,
      category: info.category,
      desc: shown.zhText || shown.text,
      taken: Boolean(taken),
      tier: best,
      disabled: targets.some(
        (g) =>
          !g.rolled.some((r) => r.effect === info.effect) &&
          g.rolled.length >= rolledCap(g, unlocked.value),
      ),
      pools,
      slots: shown.slots,
      matchedSlots: shown.slots.filter((slot) => targets.some((g) => slotMatchesGear(slot, g))),
      matched: pools.filter((p) => targets.some((g) => g.pools.has(p))),
    })
  }
  return out
})

const pickerGroups = computed(() =>
  orderedIds(
    CATEGORY_ORDER,
    candidates.value.map((candidate) => candidate.category),
  )
    .map((key) => ({
      key,
      zh: categoryLabel(key),
      effects: candidates.value.filter((c) => c.category === key),
    }))
    .filter((g) => g.effects.length),
)

const enchOptions = computed(() => {
  const targets = selectedItems.value
  if (!targets.length) return []
  const out = []
  for (const info of catalog.value.enchants.values()) {
    if (!targets.every((g) => enchantFits(g, info))) continue
    const takenTier = enchantDraft.value?.effect === info.effect ? enchantDraft.value.tier : null
    const slotInfo = Object.entries(ENCH_SLOTS)
      .filter(([, slot]) => info.slots.has(slot))
      .map(([slot]) => t('batch.slot' + slot[0].toUpperCase() + slot.slice(1)))
      .join(' · ')
    const shown = info.tiers.get(takenTier) || [...info.tiers.values()].at(-1)
    out.push({
      effect: info.effect,
      name: info.name,
      zhName: info.zhName,
      zhDesc: shown?.zhText || shown?.text || info.zhDesc,
      slotInfo,
      icon: info.icon,
      tiers: TIERS.filter((tr) => info.tiers.has(tr)).map((tier) => ({
        tier,
        zhText: info.tiers.get(tier)?.zhText || info.tiers.get(tier)?.text || '',
        taken: takenTier === tier,
      })),
    })
  }
  return out
})

function changeRoll(effect, tier) {
  mutate(() => {
    for (const g of selectedItems.value) editRoll(g, effect, tier, catalog.value, unlocked.value)
  })
}
function applyFx() {
  if (!active.value) return
  const staged = draft.value.map((d) => [d.effect, d.tier])
  mutate(() => {
    const notes = []
    for (const g of samePools.value) {
      if (g === active.value) continue
      const plan = planItem(g, staged, catalog.value.effects, unlocked.value)
      notes.push(...plan.notes)
      if (plan.changes.length) applyEffects(g, plan.final)
    }
    return { notes }
  })
}
function setEnchantment(targets, effect, tier) {
  mutate(() => {
    const info = catalog.value.enchants.get(effect)
    const spec = info?.tiers.get(tier)
    for (const g of targets) {
      if (!effect) applyEnchantment(g, null)
      else if (spec && enchantFits(g, info))
        applyEnchantment(g, {
          effect,
          ...spec,
          points: enchantPointsFor(catalog.value, g.rarity, tier),
        })
    }
  })
}
function copyItem() {
  mutate(() => {
    for (const g of selectedItems.value) duplicateItem(state.value, g.index)
  })
}
function deleteItem() {
  mutate(
    () => {
      for (const g of [...selectedItems.value].sort((a, b) => b.index - a.index))
        removeItem(state.value, g.index)
    },
    { resetSelection: true },
  )
}
function onApplyHover(on) {
  hoverTargets.value = on ? new Set(samePools.value.map((i) => i.index)) : new Set()
}

function runOp({ op, slot, value }) {
  const hero = state.value,
    all = items.value,
    cat = catalog.value
  const operations = {
    maxStats: () => maxHeroStats(hero, rawCat.meta.heroMaxStats),
    completeQuests: () => completeAllQuests(hero, worldQuests),
    completeSideQuests: () => completeSideQuests(hero, worldQuests),
    completeAchievements: () => completeAllAchievements(hero, worldQuests),
    unlockTravel: () => unlockAllTravel(hero, worldQuests),
    discoverMap: () => discoverAllMap(hero),
    clear: () => clearSlot(hero, all, slot),
    add: () => addAllOfSlot(hero, all, cat, extras, slot),
    rarity: () => setRarityOfSlot(hero, all, cat, extras, slot, value),
    storm: () => setStormOfSlot(hero, all, slot, value),
    power: () => setPowerOfSlot(hero, all, slot, value),
    level: () => setTalismanLevelOfSlot(hero, all, cat, slot, value),
  }
  mutate(operations[op], { resetSelection: op === 'clear' })
}

async function save(copy = false) {
  if (!state.value || busy.value) return
  const text = session.fileText()
  const snapshot = session.current.value
  busy.value = true
  error.value = notice.value = ''
  try {
    if (source.value !== 'disk' || copy) {
      download(currentName.value, text)
      notice.value = { key: 'status.download' }
    } else {
      const r = await api('/api/save', { name: currentName.value, text, revision })
      revision = r.revision
      notice.value = r.backup ? { key: 'status.backup', detail: r.backup } : { key: 'status.saved' }
    }
    if (!copy) session.remember(text, snapshot)
  } catch (e) {
    conflict.value = e.status === 409
    error.value = conflict.value ? t('file.conflict') : e.message
  } finally {
    busy.value = false
  }
}

const fileStatus = computed(() => {
  const message =
    notice.value && [t(notice.value.key), notice.value.detail].filter(Boolean).join(' ')
  if (dirty.value) return [t('nav.dirty'), message].filter(Boolean).join(' · ')
  return message || t('status.clean')
})
watch(brandItem, (item) => {
  if (!item?.icon) return
  const link =
    document.querySelector('link[rel="icon"]') ||
    document.head.appendChild(document.createElement('link'))
  link.rel = 'icon'
  link.href = iconUrl(item.icon)
})
onMounted(() => {
  window.addEventListener('beforeunload', beforeUnload)
  boot()
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
</script>

<template>
  <div
    class="workspace"
    @dragover.prevent
    @drop.prevent="dropFile"
    @pointermove="gearTip?.track($event)"
    @pointerleave="gearTip?.hide()"
    @pointerdown="gearTip?.hide()"
    @scroll.capture="gearTip?.hide()"
  >
    <header class="top">
      <div class="brand">
        <img v-if="brandItem?.icon" :src="iconUrl(brandItem.icon)" alt="" />
        <span
          >MCD2 <span class="brand-sub">{{ t('app.name') }}</span></span
        >
      </div>
      <nav class="tabs" :aria-label="t('nav.editor')">
        <button
          :class="{ on: tab === 'edit' }"
          :aria-pressed="tab === 'edit'"
          @click="tab = 'edit'"
        >
          {{ t('nav.editor') }}
        </button>
        <button
          :disabled="!state"
          :class="{ on: tab === 'batch' }"
          :aria-pressed="tab === 'batch'"
          @click="tab = 'batch'"
        >
          {{ t('nav.batch') }}
        </button>
      </nav>
      <div v-if="state" class="file-info">
        <select
          v-if="saves.length"
          class="file-switch"
          :value="source === 'disk' ? currentName : ''"
          :title="currentName"
          :disabled="busy"
          :aria-label="t('file.onDisk')"
          @change="switchDisk"
        >
          <option v-if="source !== 'disk'" value="" disabled>{{ currentName }}</option>
          <option v-for="s in saves" :key="s.name" :value="s.name">{{ s.name }}</option>
        </select>
        <span v-else class="file-name" :title="currentName">{{
          source === 'starter' ? t('file.starter') : currentName
        }}</span>
        <span class="file-status" :class="{ dirty }" :title="fileStatus" role="status"
          ><span>{{ fileStatus }}</span></span
        >
      </div>
      <div v-if="state || browserMode" class="file-actions">
        <button :disabled="busy || !catalog" @click="saveInput.click()">
          {{ t('nav.import') }}
        </button>
        <template v-if="state">
          <button :disabled="!canUndo || busy" @click="undo">{{ t('nav.undo') }}</button>
          <button v-if="source === 'disk'" :disabled="busy" @click="save(true)">
            {{ t('file.copy') }}
          </button>
          <button class="primary" :disabled="busy || (source === 'disk' && !dirty)" @click="save()">
            {{ t(source === 'disk' ? 'nav.save' : 'file.export') }}
          </button>
        </template>
      </div>
      <div class="toolbar">
        <a class="pool-link" :href="poolsUrl + '#lang=' + locale" target="_blank" rel="noopener"
          >{{ t('nav.pools') }} ↗</a
        >
        <button class="langbtn" @click="setLocale(locale === 'zh' ? 'en' : 'zh')">
          {{ locale === 'zh' ? 'EN' : '中文' }}
        </button>
      </div>
    </header>
    <input
      ref="saveInput"
      class="visually-hidden"
      type="file"
      accept=".sav,application/json"
      tabindex="-1"
      :aria-label="t('nav.import')"
      @change="pickFile"
    />
    <div v-if="error || conflict" class="banner error" role="alert">
      <span class="error-message">{{ conflict ? t('file.conflict') : error }}</span>
      <button v-if="conflict" :disabled="busy" @click="openDisk(currentName)">
        {{ t('file.reload') }}
      </button>
      <button
        v-if="!conflict"
        class="iconbtn banner-close"
        :aria-label="t('common.close')"
        :title="t('common.close')"
        @click="error = ''"
      >
        ✕
      </button>
    </div>
    <div
      v-if="!state && !browserMode"
      class="welcome"
      @dragenter.prevent="dragging = true"
      @dragleave.self="dragging = false"
    >
      <section class="drop-card" :class="{ dragging }">
        <div class="welcome-art" aria-hidden="true">
          <img v-for="item in welcomeItems" :key="item.tag" :src="iconUrl(item.icon)" alt="" />
        </div>
        <h1>{{ t('file.openHero') }}</h1>
        <p>{{ t('file.drop') }}</p>
        <button class="primary" :disabled="busy || !catalog" @click="saveInput.click()">
          {{ t(busy ? 'file.loading' : 'nav.import') }}
        </button>
        <select
          v-if="saves.length"
          value=""
          :disabled="busy"
          :aria-label="t('file.onDisk')"
          @change="switchDisk"
        >
          <option value="" disabled>{{ t('file.onDisk') }}</option>
          <option v-for="s in saves" :key="s.name" :value="s.name">{{ s.name }}</option>
        </select>
      </section>
    </div>
    <template v-if="state">
      <main v-if="tab === 'edit'" class="editor-grid" :inert="busy">
        <ItemList
          :groups="groups"
          :active="active?.index"
          :selected="selectedIdx"
          :filters="filters"
          :total="gearCount"
          :classes="classList"
          :highlight="hoverTargets"
          @open="setActive"
          @filter="Object.assign(filters, $event)"
        />
        <DetailPanel
          v-if="active || isMulti"
          :gear="active"
          :multi="isMulti"
          :multi-items="selectedItems"
          :rows="draftRows"
          :own-fx="active?.ownFx"
          :identical-count="samePools.length"
          :unlocked="unlocked"
          :ench-options="enchOptions"
          :enchant-draft="enchantDraft"
          @tier="(k, tr) => changeRoll(draft[k].effect, tr)"
          @remove="(k) => changeRoll(draft[k].effect, null)"
          @apply-fx="applyFx"
          @set-enchant="(e, tr) => setEnchantment(selectedItems, e, tr)"
          @clear-enchant="setEnchantment(selectedItems, null)"
          @apply-enchant="setEnchantment(samePools, enchantDraft?.effect, enchantDraft?.tier)"
          @hover-targets="onApplyHover"
          @copy="copyItem"
          @delete="deleteItem"
        />
        <div v-else class="card empty detail-placeholder">
          <div v-if="!gearCount" class="inventory-empty">
            <h2>{{ t('editor.empty') }}</h2>
            <button @click="tab = 'batch'">{{ t('editor.addGear') }}</button>
          </div>
          <span v-else>{{ t('editor.selectItem') }}</span>
        </div>
        <section v-if="active || isMulti" class="card picker">
          <div class="panel-heading">
            <h2>
              {{ t('picker.title') }} <small>{{ candidates.length }}</small>
            </h2>
            <div class="picker-options">
              <label class="toggle" :title="t('nav.unlockTip')">
                <input v-model="unlocked" type="checkbox" />
                <span class="track"><span class="knob"></span></span>{{ t('nav.unlock') }}
              </label>
            </div>
          </div>
          <EffectPicker
            :groups="pickerGroups"
            @add="changeRoll"
            @remove="(e) => changeRoll(e, null)"
          />
        </section>
      </main>
      <main v-else class="batchwrap" :inert="busy">
        <BatchTools :counts="slotCounts" @op="runOp" />
      </main>
    </template>
    <ItemTooltip ref="gearTip" :items="items" />
  </div>
</template>
