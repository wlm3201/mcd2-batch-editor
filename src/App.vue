<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import ItemList from './components/ItemList.vue'
import ItemTooltip from './components/ItemTooltip.vue'
import UniquePicker from './components/UniquePicker.vue'
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
  setRarityOf,
  setRarityOfSlot,
  setStormOfSlot,
  setTalismanLevelOfSlot,
  uniqueIdFor,
} from './lib/batch.js'
import {
  completeAllAchievements,
  completeAllQuests,
  completeSideQuests,
  discoverAllMap,
  unlockAllTravel,
} from './lib/world.js'
import {
  appendOwnEffect,
  applyEffects,
  applyEnchantment,
  duplicateItem,
  editRoll,
  gearProfiles,
  planItem,
  removeEnchantment,
  removeItem,
  removeOwnEffect,
  replaceOwnEffectAt,
  updateEnchantment,
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
const unlocked = ref(false)
const uniqueTarget = ref(null)
const catalog = shallowRef(null)
const brandItem = computed(() => brandItemFor(catalog.value))
const gearTip = ref(null)
const marqueeActive = ref(false)
function onMarquee(active) {
  marqueeActive.value = active
  if (active) gearTip.value?.hide()
}
function trackTip(event) {
  if (marqueeActive.value) return
  gearTip.value?.track(event)
}
let rawCat, rawZh, extras, zhUnique, worldQuests, artifactDesc, mapPoints
const talismanTexts = shallowRef(null)
const talismanOption = (template) =>
  talismanTexts.value?.options?.find((o) => o.template === template)
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
  if (talismanTexts.value?.labels)
    for (const [id, label] of Object.entries(talismanTexts.value.labels))
      if (!catalog.value.effectLabels.has(id))
        catalog.value.effectLabels.set(id, { name: label.en, zhName: label.zh, icon: '' })
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
    ;[rawCat, rawZh, extras, zhUnique, worldQuests, artifactDesc, mapPoints, talismanTexts.value] =
      await Promise.all(
        [
          'catalog.json',
          'zh.json',
          'extras.json',
          'zh-unique.json',
          'world-quests.json',
          'artifact-desc.json',
          'map-points.json',
          'talisman-texts.json',
        ].map(loadData),
      )
    prepare()
    if (!browserMode) saves.value = (await api('/api/saves')).saves
    if (browserMode || !saves.value.length) loadHero(starterText, '', 'starter')
    else await openDisk(saves.value[0].name)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

function describeFx(row, kind) {
  const cat = catalog.value
  const info =
    cat.effectLabels.get(row.effect) || cat.enchants.get(row.effect) || cat.effects.get(row.effect)
  const special = extras?.uniqueEnchantments?.[row.template]
  const tier = (cat.enchants.get(row.effect) || cat.effects.get(row.effect))?.tiers?.get(row.tier)
  const zhOn = locale.value === 'zh'
  return {
    template: row.template,
    kind,
    name:
      (zhOn && (special?.zhName || info?.zhName)) ||
      special?.name ||
      info?.name ||
      row.effect.split('.').pop(),
    description:
      (zhOn && (zhUnique?.[row.template] || tier?.zhText || rawZh?.templates?.[row.template])) ||
      tier?.text ||
      special?.text ||
      cat.templateTexts.get(row.template) ||
      '',
  }
}

function refreshItems() {
  items.value = gearProfiles(state.value, catalog.value).map((g) => {
    const ownFx = g.ownFx.map((r) => {
      const shown = describeOwnEffect(
        r,
        catalog.value,
        extras.uniqueEnchantments,
        locale.value === 'zh' ? zhUnique : null,
      )
      const tal = talismanOption(r.template)
      return tal
        ? {
            ...shown,
            name: locale.value === 'zh' ? tal.zhName : tal.name,
            description: locale.value === 'zh' ? tal.desc : tal.descEn || tal.desc,
            icon: tal.icon || shown.icon,
          }
        : shown
    })
    const rec = catalog.value.items.get(g.tag.toLowerCase())
    const desc =
      rec?.kind === 'artifact'
        ? artifactDesc?.[rec.tag]?.[locale.value === 'zh' ? 'zh' : 'en'] || ''
        : ''
    return {
      ...g,
      ownFx,
      desc,
      canBeUnique: Boolean(uniqueIdFor(catalog.value, g.tag)),
      fxLines: [
        ...ownFx.map((r) => ({ ...r, kind: 'own' })),
        ...g.rolled.map((r) => describeFx(r, 'rolled')),
        ...g.enchants.map((r) => describeFx(r, 'ench')),
      ],
    }
  })
}

function loadHero(text, name, from, version = '') {
  session.load(text)
  currentName.value = name || `Character${state.value.body.MetaData.CharacterId}.sav`
  source.value = from
  conflict.value = false
  unlocked.value = false
  revision = version
  error.value = notice.value = ''
  uniqueTarget.value = null
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
  uniqueTarget.value = null
  selectedIdx.value = new Set()
  refreshItems()
  error.value = ''
  notice.value = { key: 'status.undone' }
}
function setActive(index, multi = false) {
  uniqueTarget.value = null
  const next = multi ? new Set(selectedIdx.value) : new Set()
  if (multi && next.has(index)) next.delete(index)
  else next.add(index)
  selectedIdx.value = next
}
function setSelection(indices, additive = false) {
  uniqueTarget.value = null
  const next = additive ? new Set(selectedIdx.value) : new Set()
  for (const index of indices) next.add(index)
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
  if (targets.length === 1)
    return targets[0].rolled.map((r, idx) => ({
      effect: r.effect,
      index: idx,
      occurrence: 0,
      tier: r.tier,
    }))
  const counts = sharedCounts(targets, (g) => g.rolled, (r) => r.effect)
  const out = []
  const used = new Map()
  for (const [idx, r] of (targets[0].rolled || []).entries()) {
    const n = used.get(r.effect) || 0
    if (n >= (counts.get(r.effect) || 0)) continue
    used.set(r.effect, n + 1)
    const peers = targets.map(
      (g) => g.rolled[nthMatch(g.rolled, (v) => v.effect === r.effect, n)],
    )
    if (peers.some((v) => !v)) continue
    out.push({
      effect: r.effect,
      index: idx,
      occurrence: n,
      tier: peers.every((v) => v.tier === r.tier) ? r.tier : '',
    })
  }
  return out
})
const enchantDraft = computed(() => {
  const first = selectedItems.value[0]?.enchant
  if (
    !first ||
    !selectedItems.value.every(
      (g) => g.enchant?.effect === first.effect && g.enchant.tier === first.tier,
    )
  )
    return null
  const info = catalog.value?.enchants.get(first.effect)
  const tier = info?.tiers.get(first.tier)
  const zhOn = locale.value === 'zh'
  return {
    ...first,
    name: info?.name || first.effect,
    zhName: zhOn ? info?.zhName || '' : '',
    icon: info?.icon || '',
    desc: (zhOn && tier?.zhText) || tier?.text || info?.zhDesc || '',
    tiers: TIERS.filter((tr) => info?.tiers.has(tr)),
  }
})
// Minimum count of each key across every selected gear; a gear missing the key counts as 0.
function sharedCounts(targets, listOf, keyOf) {
  const keys = new Set(targets.flatMap((g) => (listOf(g) || []).map(keyOf)))
  const counts = new Map()
  for (const k of keys) {
    counts.set(
      k,
      Math.min(...targets.map((g) => (listOf(g) || []).filter((x) => keyOf(x) === k).length)),
    )
  }
  return counts
}
// Match from the end: additions append to the end, so removing or editing the
// n-th shared row should target the most recent matching entry first.
function nthMatch(list, predicate, occurrence = 0) {
  let left = occurrence
  const arr = list || []
  for (let i = arr.length - 1; i >= 0; i--) {
    if (!predicate(arr[i])) continue
    if (left > 0) {
      left--
      continue
    }
    return i
  }
  return -1
}
const displayOwnFx = computed(() => {
  const targets = selectedItems.value
  if (!targets.length) return []
  const mark = (r) => ({ ...r, talisman: Boolean(talismanOption(r.template)) })
  if (targets.length === 1) return (targets[0].ownFx || []).map(mark)
  const counts = sharedCounts(targets, (g) => g.ownFx, (r) => r.template)
  const out = []
  const used = new Map()
  for (const r of targets[0].ownFx || []) {
    const n = used.get(r.template) || 0
    if (n >= (counts.get(r.template) || 0)) continue
    used.set(r.template, n + 1)
    out.push({ ...mark(r), occurrence: n })
  }
  return out
})
const talismanOwnFx = computed(() => {
  const targets = selectedItems.value
  if (!targets.length) return []
  const listOf = (g) =>
    (g.ownFx || []).flatMap((r, index) =>
      talismanOption(r.template) ? [{ ...r, ownIndex: index }] : [],
    )
  if (targets.length === 1) return listOf(targets[0]).map((r) => ({ ...r, occurrence: 0 }))
  const counts = sharedCounts(targets, listOf, (r) => r.template)
  const out = []
  const used = new Map()
  for (const r of listOf(targets[0])) {
    const n = used.get(r.template) || 0
    if (n >= (counts.get(r.template) || 0)) continue
    used.set(r.template, n + 1)
    out.push({ ...r, occurrence: n })
  }
  return out
})
const sharedEnchants = computed(() => {
  const targets = selectedItems.value
  if (targets.length < 2) return []
  const key = (e) => e.effect + '|' + e.template
  const counts = sharedCounts(targets, (g) => g.enchants, key)
  const out = []
  const used = new Map()
  for (const e of targets[0].enchants || []) {
    const k = key(e)
    const n = used.get(k) || 0
    if (n >= (counts.get(k) || 0)) continue
    used.set(k, n + 1)
    out.push({ ...e, occurrence: n })
  }
  return out
})
const extraEnchants = computed(() => {
  const zhOn = locale.value === 'zh'
  const targets = selectedItems.value
  const multi = targets.length > 1
  let base = multi ? sharedEnchants.value : (active.value?.enchants || []).slice(1)
  if (multi && enchantDraft.value) {
    const at = base.findIndex(
      (e) => e.effect === enchantDraft.value.effect && e.template === enchantDraft.value.template,
    )
    if (at >= 0) base = base.filter((_, i) => i !== at)
  }
  return base.map((e, i) => {
    const info = catalog.value?.enchants.get(e.effect)
    const tier = info?.tiers.get(e.tier)
    return {
      index: multi ? -1 : i + 1,
      occurrence: e.occurrence ?? 0,
      effect: e.effect,
      template: e.template,
      tier: e.tier,
      tiers: TIERS.filter((tr) => info?.tiers.has(tr)),
      name: info?.name || e.effect.split('.').pop(),
      zhName: zhOn ? info?.zhName || '' : '',
      desc: (zhOn && tier?.zhText) || tier?.text || info?.zhDesc || '',
      icon: info?.icon || '',
    }
  })
})
function removeExtraEnchant(index, effect, template, occurrence = 0) {
  const targets = [...selectedItems.value]
  if (!targets.length) return
  mutate(() => {
    for (const g of targets) {
      const at =
        targets.length === 1
          ? index
          : nthMatch(g.enchants, (e) => e.effect === effect && e.template === template, occurrence)
      removeEnchantment(g, at)
    }
    return null
  })
}
function changeExtraTier(index, effect, template, tier, occurrence = 0) {
  const targets = [...selectedItems.value]
  const info = catalog.value?.enchants.get(effect)
  const spec = info?.tiers.get(tier)
  if (!targets.length || !spec) return
  mutate(() => {
    for (const g of targets) {
      const at =
        targets.length === 1
          ? index
          : nthMatch(g.enchants, (e) => e.effect === effect && e.template === template, occurrence)
      updateEnchantment(g, at, {
        effect,
        template: spec.template,
        intensity: spec.intensity,
        points: enchantPointsFor(catalog.value, g.rarity, tier),
      })
    }
    return null
  })
}
function removeOwnFx(index, template, occurrence = 0) {
  const targets = [...selectedItems.value]
  if (!targets.length) return
  mutate(() => {
    for (const g of targets) {
      const at =
        targets.length === 1 ? index : nthMatch(g.ownFx, (r) => r.template === template, occurrence)
      removeOwnEffect(g, at)
    }
    return null
  })
}
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
const draftRows = computed(() => {
  const rows = draft.value.map((d) => {
    const info = catalog.value.effects.get(d.effect)
    const tier = info?.tiers.get(d.tier)
    const pools = d.tier
      ? [...(tier?.groups ?? [])].filter((pool) => pool !== 'Weapon' && pool !== 'Artifact')
      : []
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
      pools,
      matched: pools.filter((pool) => selectedItems.value.some((g) => g.pools.has(pool))),
      tierChoices: info ? [...info.tiers.keys()] : [],
    }
  })
  for (const r of talismanOwnFx.value) {
    const o = talismanOption(r.template)
    if (!o) continue
    rows.push({
      effect: r.effect,
      index: r.ownIndex,
      occurrence: r.occurrence,
      tier: r.tier,
      name: o.name,
      zhName: locale.value === 'zh' ? o.zhName : '',
      zhText: locale.value === 'zh' ? o.desc : o.descEn || o.desc,
      icon: o.icon,
      slots: [],
      matchedSlots: [],
      pools: [],
      matched: [],
      tierChoices: ['I', 'II', 'III'],
      talisman: o.talisman,
      template: r.template,
    })
  }
  return rows
})

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
      taken: unlocked.value ? false : Boolean(taken),
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

const pickerSource = ref('rolls')
const activePickerSource = computed(() => (unlocked.value ? pickerSource.value : 'rolls'))
const talismanCandidates = computed(() =>
  (talismanTexts.value?.options || []).filter((o) => o.tier === 'III').map((o) => ({
    id: o.id,
    effect: o.effect,
    template: o.template,
    talisman: o.talisman,
    strength: o.strength,
    name: o.name,
    zhName: locale.value === 'zh' ? o.zhName : '',
    icon: o.icon,
    desc: locale.value === 'zh' ? o.desc : o.descEn || o.desc,
    category: o.category,
    tier: o.tier,
    slots: [],
    pools: [],
    taken: false,
    disabled: false,
  })),
)
const shownCandidates = computed(() =>
  activePickerSource.value === 'talisman' ? talismanCandidates.value : candidates.value,
)
const pickerGroups = computed(() =>
  orderedIds(
    CATEGORY_ORDER,
    shownCandidates.value.map((candidate) => candidate.category),
  )
    .map((key) => ({
      key,
      zh: categoryLabel(key),
      effects: shownCandidates.value.filter((c) => c.category === key),
    }))
    .filter((g) => g.effects.length),
)

const enchOptions = computed(() => {
  const targets = selectedItems.value
  if (!targets.length) return []
  const out = []
  for (const info of catalog.value.enchants.values()) {
    if (!unlocked.value && !targets.every((g) => enchantFits(g, info))) continue
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
      slots: [...info.slots],
      icon: info.icon,
      tiers: TIERS.filter((tr) => info.tiers.has(tr)).map((tier) => ({
        tier,
        zhText: info.tiers.get(tier)?.zhText || info.tiers.get(tier)?.text || '',
      })),
    })
  }
  return out
})

function changeRoll(effect, tier, index = null, occurrence = 0) {
  mutate(() => {
    const multi = selectedItems.value.length > 1
    for (const g of selectedItems.value) {
      const at =
        multi && index !== null
          ? nthMatch(g.rolled, (r) => r.effect === effect, occurrence)
          : index
      editRoll(g, effect, tier, catalog.value, unlocked.value, at)
    }
  })
}
function onPickAdd(effect, tier, candidate) {
  if (candidate?.talisman) addTalismanEffect(candidate)
  else changeRoll(effect, tier)
}
function addTalismanEffect(option) {
  mutate(() => {
    let changed = false
    for (const g of selectedItems.value) {
      changed =
        appendOwnEffect(g, {
          effect: option.effect,
          template: option.template,
          strength: option.strength,
        }) || changed
    }
    return changed ? { notes: [] } : null
  })
}
function onRowTier(k, tr) {
  const row = draftRows.value[k]
  if (row?.talisman) return changeTalismanTier(row, tr)
  const d = draft.value[k]
  changeRoll(d.effect, tr, d.index, d.occurrence)
}
function onRowRemove(k) {
  const row = draftRows.value[k]
  if (row?.talisman) return removeOwnFx(row.index, row.template, row.occurrence)
  const d = draft.value[k]
  changeRoll(d.effect, null, d.index, d.occurrence)
}
function changeTalismanTier(row, tr) {
  const option = talismanTexts.value?.options?.find(
    (o) => o.talisman === row.talisman && o.tier === tr,
  )
  if (!option) return
  const targets = [...selectedItems.value]
  mutate(() => {
    let changed = false
    for (const g of targets) {
      const at =
        targets.length === 1
          ? row.index
          : nthMatch(g.ownFx, (r) => r.template === row.template, row.occurrence)
      changed =
        replaceOwnEffectAt(g, at, {
          effect: option.effect,
          template: option.template,
          strength: option.strength,
        }) || changed
    }
    return changed ? { notes: [] } : null
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
function setGearRarity(rarity) {
  const targets = [...selectedItems.value]
  if (!targets.length) return
  mutate(() => {
    const skipped = []
    for (const g of targets) {
      if (g.rarity !== rarity && !setRarityOf(g, catalog.value, extras, rarity))
        skipped.push(g.zhName || g.name)
    }
    return skipped.length ? { skipped } : null
  })
}
function applyEnchantToSame() {
  setEnchantment(
    samePools.value,
    enchantDraft.value?.effect,
    enchantDraft.value?.tier,
    unlocked.value,
  )
}
function setEnchantment(targets, effect, tier, append = false) {
  mutate(() => {
    const info = catalog.value.enchants.get(effect)
    const spec = info?.tiers.get(tier)
    for (const g of targets) {
      if (!effect) applyEnchantment(g, null)
      else if (spec && (unlocked.value || enchantFits(g, info)))
        applyEnchantment(
          g,
          {
            effect,
            ...spec,
            points: enchantPointsFor(catalog.value, g.rarity, tier),
          },
          append,
        )
    }
  })
}
// Three unique enchantments have no category in the game catalog; classify by their effect text.
const UNIQUE_CATEGORY_OVERRIDES = {
  'SW.Enchantment.MaulerDive': 'offensive',
  'SW.Enchantment.PhantomLance': 'offensive',
  'SW.Enchantment.ClawingShadow.Unique': 'utility',
}
const uniqueOptions = computed(() => {
  if (!catalog.value || !extras?.uniqueOwn || !zhUnique) return []
  const zhOn = locale.value === 'zh'
  const byTemplate = new Map()
  for (const [id, own] of Object.entries(extras.uniqueOwn)) {
    if (!byTemplate.has(own.template)) byTemplate.set(own.template, [])
    byTemplate.get(own.template).push(id)
  }
  return [...byTemplate.entries()]
    .map(([template, ids]) => {
      const own = extras.uniqueOwn[ids[0]]
      const items = ids.map((id) => {
        const rec = catalog.value.items.get(id.toLowerCase())
        const slot = rec?.slot || (rec?.kind === 'melee' || rec?.kind === 'ranged' ? rec.kind : '')
        return { id, name: (zhOn && rec?.zhName) || rec?.name || id, icon: rec?.icon || '', slot }
      })
      const info =
        catalog.value.effectLabels.get(own.effect) || catalog.value.enchants.get(own.effect)
      return {
        template,
        effect: own.effect,
        strength: own.strength,
        icon: extras?.uniqueEnchantments?.[template]?.icon || info?.icon || '',
        name:
          (zhOn &&
            (rawZh?.effectsById?.[own.effect] ||
              extras?.uniqueEnchantments?.[template]?.zhName ||
              info?.zhName)) ||
          extras?.uniqueEnchantments?.[template]?.name ||
          info?.name ||
          own.effect.split('.').pop(),
        description:
          (zhOn && zhUnique[template]) ||
          catalog.value.templateTexts.get(template) ||
          extras?.uniqueEnchantments?.[template]?.text ||
          '',
        from: items.length > 1 ? `${items[0].name} +${items.length - 1}` : items[0].name,
        itemNames: items.map((it) => it.name),
        slots: [...new Set(items.map((it) => it.slot).filter(Boolean))],
        category:
          rawCat?.effects?.[own.effect]?.category ||
          rawCat?.enchantments?.[own.effect]?.category ||
          UNIQUE_CATEGORY_OVERRIDES[own.effect] ||
          'other',
        items,
      }
    })
    .sort((a, b) => a.name.localeCompare(b.name, zhOn ? 'zh' : 'en'))
})

function openUniquePicker(k, append = false) {
  if (!selectedItems.value.length) return
  uniqueTarget.value = {
    gearIndexes: selectedItems.value.map((g) => g.index),
    ownIndex: k,
    append,
  }
}
function openAddOwn() {
  if (!selectedItems.value.length) return
  uniqueTarget.value = {
    gearIndexes: selectedItems.value.map((g) => g.index),
    ownIndex: -1,
    append: true,
  }
}
function applyUnique(option) {
  const target = uniqueTarget.value
  if (!target) return
  if (!target.append) uniqueTarget.value = null
  const gears = items.value.filter((g) => target.gearIndexes.includes(g.index))
  if (gears.length !== target.gearIndexes.length) {
    uniqueTarget.value = null // inventory changed while the picker stayed open
    return
  }
  const old = displayOwnFx.value[target.ownIndex]
  if (!gears.length || (!target.append && !old)) return
  mutate(() => {
    let changed = false
    for (const g of gears) {
      if (target.append) {
        changed = appendOwnEffect(g, option) || changed
        continue
      }
      const at =
        gears.length === 1
          ? target.ownIndex
          : nthMatch(g.ownFx, (r) => r.template === old.template, old.occurrence ?? 0)
      changed = replaceOwnEffectAt(g, at, option) || changed
    }
    return changed ? { notes: [] } : null
  })
}
function copyItem() {
  uniqueTarget.value = null
  mutate(() => {
    for (const g of selectedItems.value) duplicateItem(state.value, g.index)
  })
}
function deleteItem() {
  uniqueTarget.value = null
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
    completeQuests: () => completeAllQuests(hero, worldQuests, mapPoints?.cutscenes),
    completeSideQuests: () => completeSideQuests(hero, worldQuests),
    completeAchievements: () => completeAllAchievements(hero, worldQuests),
    unlockTravel: () => unlockAllTravel(hero, worldQuests),
    discoverMap: () => discoverAllMap(hero, worldQuests, mapPoints),
    clear: () => clearSlot(hero, all, slot),
    add: () => addAllOfSlot(hero, all, cat, extras, slot),
    rarity: () => setRarityOfSlot(hero, all, cat, extras, slot, value),
    storm: () => setStormOfSlot(hero, all, slot, value),
    power: () => setPowerOfSlot(hero, all, slot, value),
    level: () => setTalismanLevelOfSlot(hero, all, cat, slot, value),
  }
  mutate(operations[op], { resetSelection: op === 'clear' })
}

async function save(copy = false, force = false) {
  if (!state.value || busy.value) return
  const text = session.fileText()
  const snapshot = session.current.value
  busy.value = true
  error.value = notice.value = ''
  conflict.value = false
  try {
    if (browserMode || copy) {
      download(currentName.value, text)
      notice.value = { key: 'status.download' }
    } else {
      const diskName = /^Character[\w-]*\.sav$/i.test(currentName.value)
        ? currentName.value
        : `Character${state.value.body.MetaData.CharacterId}.sav`
      const r = await api('/api/save', { name: diskName, text, revision, force })
      revision = r.revision
      currentName.value = diskName
      source.value = 'disk'
      saves.value = (await api('/api/saves')).saves
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
    @pointermove="trackTip"
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
        <span
          v-else
          class="file-name"
          :class="{ 'starter-hint': browserMode && source === 'starter' }"
          :title="currentName"
          >{{ source === 'starter' ? t(browserMode ? 'file.starterHint' : 'file.starter') : currentName }}</span
        >
        <span class="file-status" :class="{ dirty }" :title="fileStatus" role="status"
          ><span>{{ fileStatus }}</span></span
        >
      </div>
      <div v-if="state || browserMode" class="file-actions">
        <label class="toggle" :title="t('nav.unlockTip')">
          <input v-model="unlocked" type="checkbox" />
          <span class="track"><span class="knob"></span></span>{{ t('nav.unlock') }}
        </label>
        <button :disabled="busy || !catalog" @click="saveInput.click()">
          {{ t('nav.import') }}
        </button>
        <template v-if="state">
          <button :disabled="!canUndo || busy" @click="undo">{{ t('nav.undo') }}</button>
          <button v-if="!browserMode" :disabled="busy" @click="save(true)">
            {{ t('file.copy') }}
          </button>
          <button class="primary" :disabled="busy || (source === 'disk' && !dirty)" @click="save()">
            {{ t(browserMode ? 'file.export' : 'nav.save') }}
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
      <button v-if="conflict" class="primary" :disabled="busy" @click="save(false, true)">
        {{ t('file.forceSave') }}
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
    <template v-if="state">
      <main v-if="tab === 'edit'" class="editor-grid" :inert="busy || uniqueTarget !== null">
        <ItemList
          :groups="groups"
          :active="active?.index"
          :selected="selectedIdx"
          :filters="filters"
          :total="gearCount"
          :classes="classList"
          :highlight="hoverTargets"
          @open="setActive"
          @select="setSelection"
          @marquee="onMarquee"
          @filter="Object.assign(filters, $event)"
        />
        <DetailPanel
          v-if="active || isMulti"
          :gear="active"
          :multi="isMulti"
          :multi-items="selectedItems"
          :rows="draftRows"
          :own-fx="displayOwnFx"
          :identical-count="samePools.length"
          :unlocked="unlocked"
          :ench-options="enchOptions"
          :enchant-draft="enchantDraft"
          :extra-enchants="extraEnchants"
          @tier="onRowTier"
          @remove="onRowRemove"
          @apply-fx="applyFx"
          @set-enchant="(e, tr, append) => setEnchantment(selectedItems, e, tr, append)"
          @apply-enchant="applyEnchantToSame"
          @pick-own="openUniquePicker"
          @add-own="openAddOwn"
          @remove-own="(k, tpl, occ) => removeOwnFx(k, tpl, occ)"
          @remove-extra="(i, e, tpl, occ) => removeExtraEnchant(i, e, tpl, occ)"
          @change-extra-tier="(i, e, tpl, tr, occ) => changeExtraTier(i, e, tpl, tr, occ)"
          @set-rarity="setGearRarity"
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
              {{ t('picker.title') }} <small>{{ shownCandidates.length }}</small>
            </h2>
            <div v-if="unlocked" class="picker-tabs">
              <button
                class="tierbtn"
                :class="{ on: activePickerSource === 'rolls' }"
                :aria-pressed="activePickerSource === 'rolls'"
                type="button"
                @click="pickerSource = 'rolls'"
              >
                {{ t('picker.rollsTab') }}
              </button>
              <button
                class="tierbtn"
                :class="{ on: activePickerSource === 'talisman' }"
                :aria-pressed="activePickerSource === 'talisman'"
                type="button"
                @click="pickerSource = 'talisman'"
              >
                {{ t('picker.talismanTab') }}
              </button>
            </div>
          </div>
          <EffectPicker
            :groups="pickerGroups"
            @add="onPickAdd"
            @remove="(e) => changeRoll(e, null)"
          />
        </section>
      </main>
      <main v-else class="batchwrap" :inert="busy">
        <BatchTools :counts="slotCounts" @op="runOp" />
      </main>
    </template>
    <ItemTooltip ref="gearTip" :items="items" />
    <UniquePicker
      v-if="uniqueTarget"
      :options="uniqueOptions"
      @select="applyUnique"
      @close="uniqueTarget = null"
    />
  </div>
</template>
