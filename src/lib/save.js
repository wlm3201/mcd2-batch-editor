// Hero save handling: parse the plain-JSON Character<id>.sav, list the gear, and write rolled
// effects / enchantments exactly the way the game saves them (batches under ItemData.Effects,
// an entry the item keeps stays byte-identical, every edit is marked Unseen like both editors do).
import { rolledCap, templateTier, tierFits } from './catalog.js'
import { cloneSave } from './codec.js'

export const REROLLABLE = 'SW.Item.Effect.Rerollable'
export const ENCHANTMENT = 'SW.Item.Effect.Enchantment'
export const UNSEEN = 'SW.Item.Property.Dynamic.Unseen'
export const SOULSTORM = 'SW.Item.Property.StorminatorReward'
export const GEAR_KINDS = ['Melee', 'Ranged', 'Armor', 'Artifact']

const KIND_NAMES = {
  melee: 'Melee',
  ranged: 'Ranged',
  armor: 'Armor',
  artifact: 'Artifact',
  talisman: 'Talisman',
  book: 'Enchantment Book',
  cape: 'Cape',
  pet: 'Pet',
  quest: 'Quest Item',
  food: 'Food',
  throwable: 'Throwable',
}
const RANGED_RE = /bow|sling|blowgun|launcher/i
const ARMOR_RE =
  /Helmet|Helm|Hood|Hat|Mask|Chest|Armor|Armour|Mail|Robe|Tunic|Vest|Leggings|Pants|Greaves|Boots|Shoes|Gauntlets|Gloves/
const PIECE_RE = /(Helmet|Helm|Hood|Hat|Mask|Chest|Armor|Leggings|Pants|Greaves|Boots|Shoes)$/

export function attach(doc) {
  const format = doc?.SerializeMeta?.HardFormat
  if (typeof format !== 'string' || !/^FCharacterSave(?:V\d+)?$/.test(format))
    throw new Error('Expected a Character .sav (FCharacterSave).')
  const bodyKey = format.slice(1)
  const body = doc[bodyKey]
  if (!body || !Array.isArray(body.Inventory?.Entries))
    throw new Error(`Missing ${bodyKey}.Inventory.Entries.`)
  return { doc, bodyKey, body }
}

function kindOf(tag, rec) {
  if (rec?.kind) return KIND_NAMES[rec.kind] || rec.kind
  const parts = tag.split('.')
  const leaf = parts[parts.length - 1]
  if (tag.toLowerCase().startsWith('sw.item.cosmetic.')) return 'Cosmetic'
  if (parts.length > 3) return parts[2]
  if (RANGED_RE.test(leaf)) return 'Ranged'
  if (ARMOR_RE.test(leaf)) return 'Armor'
  return 'Melee'
}

function pieceOf(tag, rec) {
  if (rec?.slot) return rec.slot // helmet | chest | leggings | boots
  const m = PIECE_RE.exec(tag.split('.').pop())
  if (!m) return null
  const word = m[1]
  if (/Leggings|Pants|Greaves/.test(word)) return 'leggings'
  if (/Boots|Shoes/.test(word)) return 'boots'
  if (/Chest|Armor/.test(word)) return 'chest'
  return 'helmet'
}

export function gearProfiles(state, catalog) {
  const entries = state?.body?.Inventory?.Entries || []
  const out = []
  entries.forEach((entry, index) => {
    const data = entry?.ItemData
    if (!data || typeof data !== 'object') return
    const tag = String(data.TypeTag || '')
    if (!tag) return
    const rec = catalog.items.get(tag.toLowerCase())
    const kind = kindOf(tag, rec)
    const isGear = GEAR_KINDS.includes(kind)
    if (kind === 'Cosmetic' || (!isGear && kind !== 'Talisman' && kind !== 'Enchantment Book'))
      return

    let pools
    let archetypes
    if (rec?.pools?.size) {
      pools = new Set(rec.pools)
      archetypes = [...rec.classes]
    } else {
      pools = new Set(['Archetype.Utility'])
      if (kind === 'Melee' || kind === 'Ranged') pools.add('Weapon')
      if (kind === 'Artifact') pools.add('Artifact')
      archetypes = []
    }

    const rolled = []
    const ownFx = []
    let enchant = null
    let enchants = []
    let enchantCount = 0
    let totalFx = 0
    for (const batch of Array.isArray(data.Effects) ? data.Effects : []) {
      if (!batch || typeof batch !== 'object') continue
      const listed = Array.isArray(batch.EffectsInThisBatch) ? batch.EffectsInThisBatch : []
      if (batch.TypeTag !== ENCHANTMENT) totalFx += listed.length
      if (batch.TypeTag === REROLLABLE) {
        for (const eff of listed) {
          const template = eff?.GeneratorData?.GeneratorParentTemplate
          if (typeof eff?.TypeTag === 'string' && typeof template === 'string') {
            rolled.push({
              effect: eff.TypeTag,
              template,
              tier: templateTier(catalog, template),
              strength: eff.Intensity,
            })
          }
        }
      } else if (batch.TypeTag === ENCHANTMENT) {
        enchants = listed
          .filter(
            (eff) =>
              typeof eff?.TypeTag === 'string' &&
              typeof eff.GeneratorData?.GeneratorParentTemplate === 'string',
          )
          .map((eff) => {
            const template = eff.GeneratorData.GeneratorParentTemplate
            return {
              effect: eff.TypeTag,
              template,
              tier: templateTier(catalog, template),
              intensity: eff.Intensity,
              points: eff.EnchantmentPointsInvested || 0,
            }
          })
        enchantCount = enchants.length
        enchant = enchants[0] || null
      } else {
        for (const eff of listed) {
          const template = eff?.GeneratorData?.GeneratorParentTemplate
          if (typeof eff?.TypeTag === 'string' && typeof template === 'string') {
            ownFx.push({
              effect: eff.TypeTag,
              template,
              tier: templateTier(catalog, template),
              strength: eff.Intensity,
            })
          }
        }
      }
    }

    const marks = Array.isArray(data.DynamicPropertyTags) ? data.DynamicPropertyTags : []
    const rarity = String(data.RarityTag || '').replace('SW.Rarity.', '')
    const rule = catalog.rollRules.get(rarity)
    const soulstorm = marks.includes(SOULSTORM)
    // Only the item's single built-in effect occupies a slot in the game's effect cap;
    // editor-appended duplicates must not shrink the normal roll budget.
    const staticCount = Math.min(
      1,
      (Array.isArray(data.Effects) ? data.Effects : [])
        .filter((b) => b?.TypeTag === 'SW.Item.Effect.Static')
        .reduce(
          (n, b) => n + (Array.isArray(b.EffectsInThisBatch) ? b.EffectsInThisBatch.length : 0),
          0,
        ),
    )
    out.push({
      index,
      entry,
      data,
      tag,
      base: rec?.base || tag,
      name: rec?.name || tag.split('.').pop(),
      zhName: rec?.zhName || '',
      kind,
      isGear,
      slotKey: isGear
        ? kind === 'Armor'
          ? pieceOf(tag, rec)
          : kind.toLowerCase()
        : kind === 'Talisman'
          ? 'talisman'
          : 'book',
      piece: kind === 'Armor' ? pieceOf(tag, rec) : null,
      rarity,
      rollLimit: Math.max(
        0,
        Math.min(
          (rule?.rerollable || 0) + (soulstorm ? rule?.stormBonus || 0 : 0),
          catalog.maxEffects - staticCount,
        ),
      ),
      power: data.GeneratorData?.PowerGeneratorValues?.ItemPower ?? null,
      own: ownFx.length,
      ownFx,
      totalFx,
      rolled,
      enchant,
      enchants,
      enchantCount,
      pools,
      archetypes,
      blockedRollTypes: rec?.blockedRollTypes,
      stock: Boolean(data.TargetSlotOverride && data.TargetSlotOverride !== 'None'),
      equipped: Boolean(entry.EquippedSlot && entry.EquippedSlot !== 'None'),
      soulstorm,
      icon: rec?.icon || '',
    })
  })
  return out
}

// Rows already on the item always target one entry by index, unlocked or not;
// picker actions without an index keep replace-by-effect / unlocked-append rules.
export function editRoll(gear, effect, tier, catalog, unlocked, index = null) {
  const current = gear.rolled
  const byIndex = index != null
  if (byIndex && !current[index]) return false
  const at = byIndex ? index : current.findIndex((r) => r.effect === effect)
  if (tier === null) {
    if (byIndex) return applyEffects(gear, current.filter((_, i) => i !== index))
    return at >= 0 && applyEffects(gear, current.filter((r) => r.effect !== effect))
  }
  const spec = catalog.effects.get(effect)?.tiers.get(tier)
  if (!spec || (!byIndex && !tierFits(spec, gear, unlocked))) return false
  if (at < 0 && current.length >= rolledCap(gear, unlocked)) return false
  const next = current.slice()
  const roll = { effect, tier, template: spec.template, strength: spec.intensity }
  if (unlocked && !byIndex) next.push(roll)
  else next[at < 0 ? current.length : at] = roll
  return applyEffects(gear, next)
}

// Explicit "apply to similar" replaces the rolled batch. If no requested roll
// is legal, leave the recipient intact. An empty source deliberately clears it.
export function planItem(gear, staged, effects, unlocked) {
  const final = []
  const notes = []
  if (gear.stock) return { final: gear.rolled, changes: [], notes: [gear.name] }
  for (const [effect, tier] of staged) {
    const spec = effects.get(effect)?.tiers.get(tier)
    if (!spec || !tierFits(spec, gear, unlocked) || final.length >= rolledCap(gear, unlocked)) {
      notes.push(gear.zhName || gear.name)
      continue
    }
    if (!final.some((r) => r.effect === effect))
      final.push({ effect, tier, template: spec.template, strength: spec.intensity })
  }
  if (staged.length && !final.length) return { final: gear.rolled, changes: [], notes }
  const same =
    final.length === gear.rolled.length &&
    final.every(
      (r, i) => r.effect === gear.rolled[i].effect && r.template === gear.rolled[i].template,
    )
  return { final, changes: same ? [] : [gear.name], notes }
}

function editableBatch(gear, type) {
  if (gear.stock) throw new Error(gear.name + ': merchant stock')
  const batches = gear.data.Effects
  if (!Array.isArray(batches)) throw new Error(gear.name + ': invalid Effects')
  const matches = batches.filter((b) => b?.TypeTag === type)
  const entries = matches[0]?.EffectsInThisBatch
  if (
    matches.length > 1 ||
    (matches.length &&
      (!Array.isArray(entries) ||
        !entries.every(
          (e) =>
            typeof e?.TypeTag === 'string' &&
            typeof e.GeneratorData?.GeneratorParentTemplate === 'string',
        )))
  )
    throw new Error(gear.name + ': unsupported effect batch')
  return matches[0]
}

// Write the rolled batch the way the game saves it; entries the item keeps stay as they are.
export function applyEffects(gear, final) {
  const data = gear.data
  const batch = editableBatch(gear, REROLLABLE)
  const batches = data.Effects
  const entries = batch?.EffectsInThisBatch || []
  if (
    entries.length === final.length &&
    final.every(
      (r, i) =>
        entries[i].TypeTag === r.effect &&
        entries[i].GeneratorData.GeneratorParentTemplate === r.template,
    )
  )
    return false
  const source = new Map()
  for (const e of entries) {
    const key = e.TypeTag + '|' + e.GeneratorData.GeneratorParentTemplate
    if (!source.has(key)) source.set(key, [])
    source.get(key).push(e)
  }
  const made = final.map((r) => {
    const pool = source.get(`${r.effect}|${r.template}`)
    if (pool?.length) return pool.shift()
    return {
      TypeTag: r.effect,
      Intensity: r.strength,
      Quality: 0,
      EnchantmentPointsInvested: 0,
      GeneratorData: { GeneratorParentTemplate: r.template, Locked: false },
    }
  })
  if (!made.length) {
    if (batch) batches.splice(batches.indexOf(batch), 1)
  } else if (batch) {
    batch.EffectsInThisBatch = made
  } else {
    let at = batches.findIndex((b) => b?.TypeTag === ENCHANTMENT) // before the enchantment: the game rolls first
    if (at < 0) at = batches.length
    batches.splice(at, 0, { TypeTag: REROLLABLE, EffectsInThisBatch: made })
  }
  markUnseen(data)
  return true
}

// Write the enchantment batch. append=true adds another entry instead of replacing the batch.
export function applyEnchantment(gear, spec, append = false) {
  const data = gear.data
  const batch = editableBatch(gear, ENCHANTMENT)
  const batches = data.Effects
  const entries = batch?.EffectsInThisBatch || []
  if (
    !append &&
    spec &&
    entries.length === 1 &&
    entries[0].TypeTag === spec.effect &&
    entries[0].GeneratorData.GeneratorParentTemplate === spec.template
  )
    return false
  if (!spec) {
    if (batch) batches.splice(batches.indexOf(batch), 1)
    else return false
    markUnseen(data)
    return true
  }
  const entry = {
    TypeTag: spec.effect,
    Intensity: spec.intensity,
    Quality: 0,
    EnchantmentPointsInvested: spec.points || 0,
    GeneratorData: { GeneratorParentTemplate: spec.template, Locked: false },
  }
  if (append && batch) batch.EffectsInThisBatch.push(entry)
  else if (batch) batch.EffectsInThisBatch = [entry]
  else batches.push({ TypeTag: ENCHANTMENT, EffectsInThisBatch: [entry] })
  markUnseen(data)
  return true
}

// Remove one entry from a multi-enchantment batch without touching the others.
export function removeEnchantment(gear, index) {
  const data = gear.data
  const batch = editableBatch(gear, ENCHANTMENT)
  const entries = batch?.EffectsInThisBatch
  if (!entries || !entries[index]) return false
  entries.splice(index, 1)
  if (!entries.length) data.Effects.splice(data.Effects.indexOf(batch), 1)
  markUnseen(data)
  return true
}

// Change one entry's tier without touching the other enchantments.
export function updateEnchantment(gear, index, spec) {
  const batch = editableBatch(gear, ENCHANTMENT)
  const entry = batch?.EffectsInThisBatch?.[index]
  if (!entry) return false
  if (
    entry.TypeTag === spec.effect &&
    entry.GeneratorData.GeneratorParentTemplate === spec.template
  )
    return false
  entry.TypeTag = spec.effect
  entry.GeneratorData.GeneratorParentTemplate = spec.template
  entry.Intensity = spec.intensity
  entry.EnchantmentPointsInvested = spec.points || 0
  markUnseen(gear.data)
  return true
}

const STATIC_BATCH = 'SW.Item.Effect.Static'

// Experimental: add another unique built-in effect without replacing the existing ones.
export function appendOwnEffect(gear, spec) {
  if (gear.stock) throw new Error(gear.name + ': merchant stock')
  const data = gear.data
  const batches = data.Effects
  if (!Array.isArray(batches)) throw new Error(gear.name + ': invalid Effects')
  let batch = batches.find((b) => b?.TypeTag === STATIC_BATCH)
  if (!batch) {
    batch = { TypeTag: STATIC_BATCH, EffectsInThisBatch: [] }
    batches.unshift(batch)
  }
  if (!Array.isArray(batch.EffectsInThisBatch)) batch.EffectsInThisBatch = []
  batch.EffectsInThisBatch.push({
    TypeTag: spec.effect,
    Intensity: spec.strength,
    Quality: 0,
    EnchantmentPointsInvested: 0,
    GeneratorData: { GeneratorParentTemplate: spec.template, Locked: false },
  })
  markUnseen(data)
  return true
}

// Locate the n-th built-in effect the same way gearProfiles builds ownFx.
function ownEntries(batches) {
  const out = []
  for (const batch of batches) {
    if (!batch || batch.TypeTag === REROLLABLE || batch.TypeTag === ENCHANTMENT) continue
    const entries = batch.EffectsInThisBatch
    if (!Array.isArray(entries)) continue
    for (let i = 0; i < entries.length; i++) {
      const entry = entries[i]
      if (
        typeof entry?.TypeTag === 'string' &&
        typeof entry.GeneratorData?.GeneratorParentTemplate === 'string'
      )
        out.push({ batch, entries, at: i, entry })
    }
  }
  return out
}

// Change one built-in effect by index (duplicates stay independent).
export function replaceOwnEffectAt(gear, index, next) {
  if (gear.stock) throw new Error(gear.name + ': merchant stock')
  if (!Array.isArray(gear.data.Effects)) throw new Error(gear.name + ': invalid Effects')
  const found = ownEntries(gear.data.Effects)[index]
  if (!found) return false
  const entry = found.entry
  if (
    entry.TypeTag === next.effect &&
    entry.GeneratorData.GeneratorParentTemplate === next.template &&
    entry.Intensity === next.strength
  )
    return false
  entry.TypeTag = next.effect
  entry.GeneratorData.GeneratorParentTemplate = next.template
  entry.Intensity = next.strength
  markUnseen(gear.data)
  return true
}

// Remove one built-in effect by index; drop the batch when it becomes empty.
export function removeOwnEffect(gear, index) {
  if (gear.stock) throw new Error(gear.name + ': merchant stock')
  const batches = gear.data.Effects
  if (!Array.isArray(batches)) throw new Error(gear.name + ': invalid Effects')
  const found = ownEntries(batches)[index]
  if (!found) return false
  found.entries.splice(found.at, 1)
  if (!found.entries.length) batches.splice(batches.indexOf(found.batch), 1)
  markUnseen(gear.data)
  return true
}

// Duplicate an item: clone the entry, reset it like a fresh drop, add to the end.
export function duplicateItem(state, index) {
  const entries = state.body?.Inventory?.Entries
  if (!Array.isArray(entries) || !entries[index]) throw new Error('item not found')
  const clone = cloneSave(entries[index])
  const data = clone?.ItemData
  if (data && typeof data === 'object') {
    makeNew(clone)
  }
  entries.push(clone)
  return entries.length - 1
}

export function removeItem(state, index) {
  const entries = state.body?.Inventory?.Entries
  if (!Array.isArray(entries) || !entries[index]) throw new Error('item not found')
  const entry = entries[index]
  if (entry.EquippedSlot && entry.EquippedSlot !== 'None') entry.EquippedSlot = 'None'
  entries.splice(index, 1)
}

export function makeNew(entry) {
  const data = entry.ItemData
  if ('EquippedSlot' in entry) entry.EquippedSlot = 'None'
  if ('MerchantItemSold' in entry) entry.MerchantItemSold = false
  if ('MerchantDiscount' in entry) entry.MerchantDiscount = 0
  if ('TargetSlotOverride' in data) data.TargetSlotOverride = 'None'
  const gen = data.GeneratorData
  if (gen && 'GenesisRandomSeed' in gen)
    gen.GenesisRandomSeed = 1 + Math.floor(Math.random() * 4294967295)
  if ('PickupTimestamp' in data) data.PickupTimestamp = Math.floor(Date.now() / 1000)
  markUnseen(data)
}

export function markUnseen(data) {
  if (!Array.isArray(data.DynamicPropertyTags)) data.DynamicPropertyTags = []
  if (!data.DynamicPropertyTags.includes(UNSEEN)) data.DynamicPropertyTags.push(UNSEEN)
}
