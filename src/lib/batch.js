// Batch item operations: delete / add / rarity / power / talisman level / storm, per equipment slot.
// New items inherit a compatible entry's layout, or the game's default when the inventory is empty.
import { enchantPointsFor, templateTier } from './catalog.js'
import { ENCHANTMENT, SOULSTORM, makeNew, markUnseen, removeItem } from './save.js'
import { cloneSave as clone } from './codec.js'

export const STATIC = 'SW.Item.Effect.Static'
export const UPGRADABLE = 'SW.Item.Effect.Upgradable'
export const RARITY_PREFIX = 'SW.Rarity.'
export const NO_RARITY = 'None'
export const MAX_ITEM_POWER = 1000000
const NO_POWER = {
  PlayerLevel: 1,
  AreaThreatLevel: 1,
  RecommendedThreatLevel: 1,
  ThreatSliderOffset: 0,
  ItemPowerMin: 1,
  ItemPowerMax: 11,
  RNGRoll: 0,
  ItemPower: -1,
  ItemPowerOriginal: 0,
}

export const SLOT_ORDER = [
  'melee',
  'ranged',
  'helmet',
  'chest',
  'leggings',
  'boots',
  'artifact',
  'talisman',
  'book',
]

export function itemGroup(tag) {
  const parts = tag.split('.')
  return parts.length > 3 ? parts[2] : 'Gear'
}

function ownBatch(own) {
  return {
    TypeTag: STATIC,
    EffectsInThisBatch: [
      {
        TypeTag: own.effect,
        Intensity: own.strength,
        Quality: 0,
        EnchantmentPointsInvested: 0,
        GeneratorData: { GeneratorParentTemplate: own.template, Locked: false },
      },
    ],
  }
}

// look up a map keyed by item tag, tolerating the id-case differences between the catalog
// (SW.Item.Talisman.Llama) and real saves (sw.Item.Talisman.Llama)
function lookup(map, tag) {
  if (!map || !tag) return undefined
  const key = String(tag)
  if (map[key] !== undefined) return map[key]
  const low = key.toLowerCase()
  if (map[low] !== undefined) return map[low]
  const hit = Object.keys(map).find((k) => k.toLowerCase() === low)
  return hit !== undefined ? map[hit] : undefined
}

function setOwnEffect(data, extras) {
  const batches = data.Effects
  if (!Array.isArray(batches)) return
  const own = lookup(extras.uniqueOwn, String(data.TypeTag || ''))
  const wanted = own ? [ownBatch(own)] : []
  data.Effects = [...wanted, ...batches.filter((b) => b?.TypeTag !== STATIC)]
}

function asTalisman(data, levels) {
  data.RarityTag = RARITY_PREFIX + NO_RARITY
  // the game keeps an Upgradable batch even for a companion talisman (empty: its levels carry
  // LevelTags instead of LevelEffects) - only a talisman the list knows nothing about has none
  data.Effects = levels.length
    ? [{ TypeTag: UPGRADABLE, EffectsInThisBatch: clone(levels[0]?.LevelEffects || []) }]
    : []
  const progression = (data.ItemProgression ??= {})
  Object.assign(progression, { CurrentLevel: 0, CurrentXP: 0, ItemLevels: clone(levels) })
  const values = data.GeneratorData?.PowerGeneratorValues
  if (values && typeof values === 'object') {
    for (const [k, v] of Object.entries(NO_POWER)) if (k in values) values[k] = v
  }
}

function asBook(data) {
  data.RarityTag = RARITY_PREFIX + NO_RARITY
  data.Effects = []
  const progression = (data.ItemProgression ??= {})
  Object.assign(progression, { CurrentLevel: 0, CurrentXP: 0, ItemLevels: [] })
  const values = data.GeneratorData?.PowerGeneratorValues
  if (values && typeof values === 'object') {
    for (const [k, v] of Object.entries(NO_POWER)) if (k in values) values[k] = v
  }
  if (Array.isArray(data.DynamicPropertyTags)) data.DynamicPropertyTags = []
}

// --------------------------------------------------------------- queries

export function inSlot(all, slot) {
  return all.filter((it) => it.slotKey === slot && !it.stock)
}

export function uniqueIdFor(catalog, tag) {
  const rec = catalog.items.get(tag.toLowerCase())
  return rec?.uniqueId || null
}

export function baseIdFor(catalog, tag) {
  const rec = catalog.items.get(tag.toLowerCase())
  return rec?.base || tag
}

// --------------------------------------------------------------- ops

export function clearSlot(state, all, slot) {
  const entries = state.body?.Inventory?.Entries || []
  let deleted = 0
  const skipped = []
  for (const it of inSlot(all, slot)) {
    const at = entries.indexOf(it.entry)
    if (at >= 0) {
      removeItem(state, at)
      deleted += 1
    } else {
      skipped.push(`${it.zhName || it.name}: not found`)
    }
  }
  return { deleted, skipped }
}

export function addAllOfSlot(state, all, catalog, extras, slot) {
  const entries = state.body?.Inventory?.Entries || []
  const have = new Set(all.filter((it) => !it.stock).map((it) => it.tag.toLowerCase()))
  const wanted = []
  for (const rec of catalog.items.values()) {
    const full = rec.tag
    const kind = rec.kind
    let ok = false
    if (slot === 'melee') ok = kind === 'melee'
    else if (slot === 'ranged') ok = kind === 'ranged'
    else if (['helmet', 'chest', 'leggings', 'boots'].includes(slot))
      ok = kind === 'armor' && rec.slot === slot
    else if (slot === 'artifact') ok = kind === 'artifact'
    else if (slot === 'talisman') ok = kind === 'talisman'
    else if (slot === 'book') ok = kind === 'book'
    if (!ok) continue
    if (['melee', 'ranged', 'helmet', 'chest', 'leggings', 'boots'].includes(slot) && !rec.unique)
      continue // gear slots: Uniques only
    wanted.push(full)
  }
  wanted.sort()
  const added = []
  const skipped = []
  for (const tag of wanted) {
    if (have.has(tag.toLowerCase())) {
      skipped.push(`${tag}: already owned`)
      continue
    }
    try {
      addOne(state, catalog, extras, tag, entries)
      added.push(tag)
      have.add(tag.toLowerCase())
    } catch (e) {
      skipped.push(`${tag}: ${e.message || e}`)
    }
  }
  return { added, skipped }
}

function templateFor(entries, tag, slot) {
  const group = itemGroup(tag)
  const usable = entries.filter((e) => {
    const t = String(e?.ItemData?.TypeTag || '')
    return t && !t.toLowerCase().startsWith('sw.item.cosmetic.')
  })
  const levels = (e) =>
    Array.isArray(e?.ItemData?.ItemProgression?.ItemLevels) &&
    e.ItemData.ItemProgression.ItemLevels.length
  return (
    usable.find(
      (e) => String(e.ItemData.TypeTag) === tag && (!slot || slot !== 'talisman' || levels(e)),
    ) ||
    usable.find((e) => String(e.ItemData.TypeTag) === tag) ||
    usable.find(
      (e) =>
        itemGroup(String(e.ItemData.TypeTag)) === group &&
        (!slot || slot !== 'talisman' || levels(e)),
    ) ||
    usable.find((e) => itemGroup(String(e.ItemData.TypeTag)) === group) ||
    usable.find(
      (e) => !itemGroup(String(e.ItemData.TypeTag)).match(/Cosmetic|QuestItem|Currency/),
    ) ||
    usable[0]
  )
}

function addOne(state, catalog, extras, tag, entries) {
  const rec = catalog.items.get(tag.toLowerCase())
  const isTalisman = rec?.kind === 'talisman'
  const isBook = rec?.kind === 'book'
  const rarity = isTalisman || isBook ? null : rec?.unique ? 'Unique' : 'Special' // artifacts cap at Special
  const power = isTalisman || isBook ? null : 150
  const slot = isTalisman ? 'talisman' : isBook ? 'book' : null

  const template = templateFor(entries, tag, slot)
  // A freshly created hero has no template. Use the default inventory entry layout
  // from a game-created starter sword; makeNew supplies the seed and pickup time.
  const entry = template
    ? clone(template)
    : {
        EquippedSlot: 'None',
        StackCount: 1,
        MerchantItemSold: false,
        MerchantDiscount: 0,
        ItemData: {
          Effects: [],
          EffectRerolls: 0,
          DynamicPropertyTags: [],
          TargetSlotOverride: 'None',
          PickupTimestamp: 0,
          ItemProgression: { CurrentLevel: 0, CurrentXP: 0, ItemLevels: [] },
          GeneratorData: { GenesisRandomSeed: 0, PowerGeneratorValues: { ...NO_POWER } },
        },
      }
  const data = (entry.ItemData ??= {})
  data.TypeTag = tag
  if (rarity != null) data.RarityTag = RARITY_PREFIX + rarity
  if ('Effects' in data) {
    data.Effects = []
    setOwnEffect(data, extras) // a Unique comes with an effect of its own
  }
  if ('EffectRerolls' in data) data.EffectRerolls = 0
  if (Array.isArray(data.DynamicPropertyTags)) data.DynamicPropertyTags = []
  const progression = data.ItemProgression
  if (progression && typeof progression === 'object') {
    if ('CurrentLevel' in progression) progression.CurrentLevel = 0
    if ('CurrentXP' in progression) progression.CurrentXP = 0
    if ('ItemLevels' in progression) progression.ItemLevels = []
  }
  const values = data.GeneratorData?.PowerGeneratorValues
  if (values && typeof values === 'object') {
    const heroLevel = state.body?.MetaData?.Level
    if ('PlayerLevel' in values && typeof heroLevel === 'number') values.PlayerLevel = heroLevel
    if (power != null) {
      for (const key of ['ItemPower', 'ItemPowerOriginal', 'ItemPowerMin', 'ItemPowerMax']) {
        if (key in values) values[key] = power
      }
    }
  }
  if (isTalisman) asTalisman(data, lookup(extras.talismanLevels, tag) || [])
  if (isBook) asBook(data)
  entry.StackCount = 1
  makeNew(entry)
  // defaults: talismans start at level 3, gear carries the storm mark
  if (isTalisman) {
    const levels = data.ItemProgression?.ItemLevels || []
    const steps = catalog.talismanXp || []
    const lvl = Math.min(2, Math.max(0, levels.length - 1))
    if (levels.length) {
      data.ItemProgression.CurrentLevel = lvl
      data.ItemProgression.CurrentXP = steps.slice(0, lvl).reduce((a, b) => a + b, 0)
      const batch = (data.Effects || []).find((b) => b?.TypeTag === UPGRADABLE)
      if (batch && levels[lvl]?.LevelEffects?.length) {
        batch.EffectsInThisBatch = clone(levels[lvl].LevelEffects)
      }
    }
  } else if (!isBook && Array.isArray(data.DynamicPropertyTags)) {
    if (!data.DynamicPropertyTags.includes(SOULSTORM)) data.DynamicPropertyTags.unshift(SOULSTORM)
  }
  entries.push(entry)
  const loot = state.body?.LootProgression?.DiscoveredLoot
  if (
    Array.isArray(loot) &&
    !loot.some((id) => typeof id === 'string' && id.toLowerCase() === tag.toLowerCase())
  )
    loot.push(tag)
  return entries.length - 1
}

export function setRarityOfSlot(state, all, catalog, extras, slot, rarity) {
  const changed = []
  const notes = []
  for (const it of inSlot(all, slot)) {
    if (it.kind === 'Talisman' || it.kind === 'Enchantment Book') {
      notes.push(`${it.zhName || it.name}: no rarity`)
      continue
    }
    let wanted = it.tag
    if (rarity === 'Unique') wanted = uniqueIdFor(catalog, it.tag) || it.tag
    else wanted = baseIdFor(catalog, it.tag)
    const data = it.data
    if (wanted === it.tag && rarity === it.rarity) continue
    if (wanted !== it.tag) {
      data.TypeTag = wanted
      markUnseen(data)
      setOwnEffect(data, extras) // a Unique's own effect goes with what the item is
    }
    const old = it.rarity
    if (rarity !== old) {
      recountEnchantPoints(data, old, rarity, catalog)
      data.RarityTag = RARITY_PREFIX + rarity
    }
    changed.push(`${it.zhName || it.name} -> ${rarity}`)
  }
  return { changed, notes }
}

function recountEnchantPoints(data, oldRarity, newRarity, catalog) {
  for (const batch of data.Effects || []) {
    if (batch?.TypeTag !== ENCHANTMENT) continue
    for (const eff of batch.EffectsInThisBatch || []) {
      const tpl = eff?.GeneratorData?.GeneratorParentTemplate
      const tier = templateTier(catalog, tpl)
      const points = enchantPointsFor(catalog, newRarity, tier)
      if (
        tier &&
        points &&
        eff.EnchantmentPointsInvested === enchantPointsFor(catalog, oldRarity, tier)
      ) {
        eff.EnchantmentPointsInvested = points
      }
    }
  }
}

export function setStormOfSlot(state, all, slot, on) {
  const changed = []
  for (const it of inSlot(all, slot)) {
    if (!['Melee', 'Ranged', 'Armor', 'Artifact'].includes(it.kind)) continue
    const data = it.data
    if (!Array.isArray(data.DynamicPropertyTags)) data.DynamicPropertyTags = []
    const marks = data.DynamicPropertyTags
    const has = marks.includes(SOULSTORM)
    if (has === on) continue
    if (on) marks.unshift(SOULSTORM)
    else marks.splice(marks.indexOf(SOULSTORM), 1)
    markUnseen(data)
    changed.push(it.zhName || it.name)
  }
  return { changed }
}

export function setPowerOfSlot(state, all, slot, power) {
  const changed = []
  const notes = []
  if (!Number.isInteger(power) || power < 0 || power > MAX_ITEM_POWER) {
    return { changed, notes: [`power must be a whole number 0-${MAX_ITEM_POWER}`] }
  }
  for (const it of inSlot(all, slot)) {
    if (it.kind === 'Talisman') {
      notes.push(`${it.zhName || it.name}: talismans level up instead`)
      continue
    }
    if (it.kind === 'Enchantment Book') {
      notes.push(`${it.zhName || it.name}: books have no power`)
      continue
    }
    const values = it.data.GeneratorData?.PowerGeneratorValues
    if (!values || !('ItemPower' in values)) {
      notes.push(`${it.zhName || it.name}: no power value`)
      continue
    }
    for (const key of ['ItemPower', 'ItemPowerOriginal', 'ItemPowerMin', 'ItemPowerMax']) {
      if (key in values) values[key] = power
    }
    changed.push(`${it.zhName || it.name} -> ${power}`)
  }
  return { changed, notes }
}

export function maxHeroStats(state, limits) {
  const changed = []
  const body = state.body
  if (!body) return { changed }
  const attrs = body.Ability?.Attributes
  if (!Array.isArray(attrs)) return { changed: [], notes: ['no Ability.Attributes'] }
  if (!Number.isInteger(limits?.Level)) throw new Error('Missing hero limits in game data')
  for (const [name, value] of Object.entries(limits)) {
    const entry = attrs.find((attr) => attr?.AttributeName === name)
    if (entry?.CurrentValue === value) continue
    if (entry) entry.CurrentValue = value
    // A new character has an empty array until the game initializes these attributes.
    else attrs.push({ AttributeName: name, CurrentValue: value })
    changed.push(`${name} = ${value}`)
  }
  // Hero level is mirrored in metadata. Equipped gear determines PowerLevel.
  if (body.MetaData && 'Level' in body.MetaData && body.MetaData.Level !== limits.Level) {
    body.MetaData.Level = limits.Level
    changed.push(`MetaData.Level = ${limits.Level}`)
  }
  return { changed, notes: [] }
}

export function setTalismanLevelOfSlot(state, all, catalog, slot, level) {
  const changed = []
  const notes = []
  const steps = catalog.talismanXp || []
  if (steps.length < 2) return { changed, notes: ['no talisman XP table'] }
  for (const it of inSlot(all, slot)) {
    if (it.kind !== 'Talisman') continue
    const data = it.data
    const levels = data.ItemProgression?.ItemLevels
    const batch = (data.Effects || []).find((b) => b?.TypeTag === UPGRADABLE)
    if (!Array.isArray(levels) || !levels.length || !batch) {
      notes.push(`${it.zhName || it.name}: its levels are not saved with it`)
      continue
    }
    if (!Number.isInteger(level) || level < 1 || level > levels.length) {
      notes.push(`${it.zhName || it.name}: levels 1-${levels.length}`)
      continue
    }
    const effects = levels.map((l) => l?.LevelEffects)
    const tagged = levels.some((l) => Array.isArray(l?.LevelTags) && l.LevelTags.length)
    if (!effects[level - 1]?.length && !tagged) {
      notes.push(`${it.zhName || it.name}: no effect data for level ${level}`)
      continue
    }
    const least = steps.slice(0, level - 1).reduce((a, b) => a + b, 0)
    const most =
      level === effects.length
        ? null
        : Math.max(
            Math.min(
              steps[level - 1],
              steps.slice(0, level).reduce((a, b) => a + b, 0),
            ),
            least + 1,
          ) - 1
    let xp = Number(data.ItemProgression.CurrentXP) || 0
    xp = most == null ? Math.max(xp, least) : Math.min(Math.max(xp, least), most)
    batch.EffectsInThisBatch = clone(effects[level - 1] || [])
    data.ItemProgression.CurrentLevel = level - 1
    data.ItemProgression.CurrentXP = xp
    changed.push(`${it.zhName || it.name} -> level ${level}`)
  }
  return { changed, notes }
}
