// Candidate rolls follow the item's template pools and native slot restrictions.
// Unlock bypasses those restrictions and the roll cap.
// Effects with no pool are unique-internal abilities, not rerollable candidates.
export const TIERS = ['I', 'II', 'III']
export const CATEGORY_ORDER = ['offensive', 'defensive', 'utility']
export const BRAND_ITEM = 'SW.Item.Gauntlet_Unique1'
export const MAX_EFFECTS = 4 // the game caps an item at 4 effects in all (a Unique's own counts)
export const ROLL_SLOT_LABELS = {
  melee: { zh: '近战', en: 'Melee' },
  ranged: { zh: '远程', en: 'Ranged' },
  bow: { zh: '弓', en: 'Bow' },
  crossbow: { zh: '弩', en: 'Crossbow' },
  armor: { zh: '盔甲', en: 'Armor' },
  artifact: { zh: '法器', en: 'Artifact' },
  quiver: { zh: '箭袋', en: 'Quiver artifact' },
}

export function rollSlotTags(slots = []) {
  const result = new Set(slots)
  if (result.has('bow') && result.has('crossbow')) {
    result.delete('bow')
    result.delete('crossbow')
    result.add('ranged')
  }
  if (result.has('artifact') && result.has('quiver')) result.delete('quiver')
  return Object.keys(ROLL_SLOT_LABELS).filter((slot) => result.has(slot))
}
export function slotMatchesGear(slot, gear) {
  const kind = gear.kind?.toLowerCase()
  if (slot === 'melee') return kind === 'melee'
  if (slot === 'ranged') return kind === 'ranged'
  if (slot === 'armor') return kind === 'armor'
  if (slot === 'artifact') return kind === 'artifact'
  if (!Array.isArray(gear.blockedRollTypes)) return false
  if (slot === 'bow') return kind === 'ranged' && !gear.blockedRollTypes.includes('BowOnly')
  if (slot === 'crossbow')
    return kind === 'ranged' && !gear.blockedRollTypes.includes('CrossbowOnly')
  if (slot === 'quiver')
    return kind === 'artifact' && !gear.blockedRollTypes.includes('QuiverEffectTemplate')
  return false
}
export const CLASS_ZH = {
  Fighter: '战士',
  Ranger: '游侠',
  Mage: '法师',
  Tank: '坦克',
  Support: '辅助',
  Summoner: '召唤',
  Trickster: '诡术',
  Utility: '通用',
}
export const POOL_ZH = {
  Weapon: '武器',
  Artifact: '法器',
  ...Object.fromEntries(Object.entries(CLASS_ZH).map(([id, name]) => ['Archetype.' + id, name])),
  'Elemental.Fire': '火焰',
  'Elemental.Frost': '冰霜',
  'Elemental.Lightning': '闪电',
  'Elemental.Poison': '毒素',
  'Elemental.Soul': '灵魂',
}
export const ENCH_SLOTS = {
  melee: 'melee-weapon',
  ranged: 'ranged-weapon',
  helmet: 'armor-helmet',
  chest: 'armor-chest',
  leggings: 'armor-leggings',
  boots: 'armor-boots',
}

export function orderedIds(preferred, discovered) {
  return [...preferred, ...[...new Set(discovered)].filter((id) => !preferred.includes(id)).sort()]
}

export function brandItemFor(catalog) {
  if (!catalog) return null
  const preferred = catalog.items.get((catalog.brandItemId || BRAND_ITEM).toLowerCase())
  if (preferred?.icon) return preferred
  const items = [...catalog.items.values()]
  return (
    items.find((item) => item.kind === 'melee' && item.icon) ||
    items.find((item) => item.icon) ||
    null
  )
}

export function templateTier(catalog, template) {
  const known = catalog.templateTiers?.get(template)
  if (known) return known
  // Preserve readable tiers for old/imported templates absent from this game's catalog.
  const suffix = String(template).split('.').at(-1)
  return TIERS.includes(suffix) ? suffix : ''
}

export function enchantSlotOf(gear) {
  if (gear.kind === 'Melee') return ENCH_SLOTS.melee
  if (gear.kind === 'Ranged') return ENCH_SLOTS.ranged
  if (gear.kind === 'Armor' && gear.piece) return ENCH_SLOTS[gear.piece]
  return null // artifacts cannot be enchanted
}

export function enchantFits(gear, ench) {
  const slot = enchantSlotOf(gear)
  return Boolean(slot) && ench.slots.has(slot)
}

export function prepareCatalog(raw, zh = {}) {
  const effects = new Map()
  const effectLabels = new Map()
  const templateTexts = new Map()
  const templateTiers = new Map()
  const indexTier = (template, tier) => {
    if (!template || !TIERS.includes(tier)) return
    const previous = templateTiers.get(template)
    if (previous && previous !== tier) throw new Error('Conflicting template tier: ' + template)
    templateTiers.set(template, tier)
  }
  for (const [eid, e] of Object.entries(raw.effects || {})) {
    const label = {
      name: e.name || eid,
      zhName: zh.effectsById?.[eid] || zh.effects?.[e.name] || '',
      icon: e.icon || '',
    }
    effectLabels.set(eid, label)
    const tiers = new Map()
    for (const t of e.tiers || []) {
      indexTier(t.template, t.tier)
      const text = t.text || ''
      if (t.template && text) templateTexts.set(t.template, text)
      if (t.kind !== 'gear' || !TIERS.includes(t.tier) || t.inGame === false) continue
      if (!t.template || typeof t.intensity !== 'number') continue
      const want = {
        template: t.template,
        intensity: t.intensity,
        text,
        zhText: zh.templates?.[t.template] || '',
        groups: new Set(t.groups || []),
        rollTypes: t.rollTypes || [],
        slots: rollSlotTags(t.slots),
      }
      if (!want.groups.size) continue // this tier is not rerollable; other ranks may still be
      const old = tiers.get(t.tier)
      if (!old || (!old.groups.size && want.groups.size)) tiers.set(t.tier, want) // the catalog repeats a few tiers
    }
    if (tiers.size) {
      effects.set(eid, {
        effect: eid,
        ...label,
        category: e.category || 'other',
        tiers,
      })
    }
  }

  const items = new Map()
  for (const [iid, r] of Object.entries(raw.items || {})) {
    items.set(iid.toLowerCase(), {
      tag: r.saveId || iid,
      name: r.name,
      zhName: zh.itemsById?.[iid] || zh.items?.[r.name] || '',
      kind: r.kind,
      classes: r.classes || [],
      pools: new Set(r.pools || []),
      blockedRollTypes: r.blockedRollTypes || [],
      icon: r.icon || '',
      unique: !!r.unique,
      base: r.base || iid,
      uniqueId: r.uniqueId || null,
      slot: r.slot || null,
    })
  }

  // Display actual slot eligibility after both pool and native slot restrictions.
  // For example, a Weapon-only pool cannot offer a roll on a quiver artifact.
  for (const effect of effects.values()) {
    for (const tier of effect.tiers.values()) {
      const eligible = [...items.values()].filter((item) => tierFits(tier, item, false))
      tier.slots = tier.slots.filter((slot) => eligible.some((item) => slotMatchesGear(slot, item)))
    }
  }

  const enchants = new Map()
  for (const [nid, e] of Object.entries(raw.enchantments || {})) {
    const tiers = new Map()
    for (const t of e.tiers || []) {
      indexTier(t.template, t.tier)
      if (!TIERS.includes(t.tier) || t.inGame === false) continue
      if (!t.template || typeof t.intensity !== 'number') continue
      tiers.set(t.tier, {
        template: t.template,
        intensity: t.intensity,
        text: t.text || '',
        zhText: zh.templates?.[t.template] || '',
      })
    }
    if (!tiers.size) continue
    const zhInfo = (zh.enchants || {})[nid] || {}
    enchants.set(nid, {
      effect: nid,
      name: e.name || nid,
      zhName: zhInfo.name || (zh.effects || {})[e.name] || '',
      zhDesc: zhInfo.desc || '',
      icon: e.icon || '',
      category: e.category || '',
      slots: new Set(e.slots || []),
      tiers,
    })
  }

  return {
    effects,
    effectLabels,
    templateTexts,
    templateTiers,
    items,
    enchants,
    rollRules: new Map(raw.rarities.map((r) => [r.id, r])),
    enchantPoints: raw.meta?.enchantPoints || null, // rarity -> points for tiers I/II/III
    talismanXp: raw.meta?.talismanXp || [], // XP a talisman needs for level 2, then level 3
    maxEffects: raw.meta?.maxEffects || MAX_EFFECTS,
    brandItemId: raw.meta?.brandItem || BRAND_ITEM,
    labels: raw.meta?.labels || {},
  }
}

// Own effects are fixed templates: a rolled tier with the same name can have a different value.
export function describeOwnEffect(row, catalog, uniqueEnchantments = {}, zhTexts = null) {
  const special = uniqueEnchantments[row.template]
  const base = catalog.effectLabels.get(row.effect) || catalog.enchants.get(row.effect)
  const english = special?.name || base?.name || row.effect.split('.').at(-1)
  return {
    ...row,
    name: (zhTexts && (special?.zhName || base?.zhName)) || english,
    description:
      zhTexts?.[row.template] || special?.text || catalog.templateTexts.get(row.template) || '',
    icon: special?.icon || base?.icon || '',
  }
}

// The local rarity table supplies both the natural rolls and the Storm bonus.
export function rolledCap(gear, unlocked) {
  return unlocked ? Infinity : gear.rollLimit
}

export function tierFits(tier, gear, unlocked = false) {
  if (unlocked) return true
  if (tier.rollTypes.some((type) => !gear.blockedRollTypes || gear.blockedRollTypes.includes(type)))
    return false
  if (!tier.groups.size) return false // unique-internal, never rolled
  return [...tier.groups].some((g) => gear.pools.has(g))
}

export function enchantPointsFor(catalog, rarity, tier) {
  const costs = catalog.enchantPoints?.[rarity]
  const i = TIERS.indexOf(tier)
  return Array.isArray(costs) && i >= 0 && i < costs.length ? costs[i] : 0
}
