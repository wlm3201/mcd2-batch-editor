const CLASS_COLORS = {
  Fighter: '#fd7573',
  Ranger: '#47b873',
  Mage: '#8098fe',
  Tank: '#cf8837',
  Support: '#49e1b8',
  Summoner: '#f5e9a6',
  Trickster: '#c578e9',
  Utility: '#869a99',
}
const POOL_COLORS = {
  ...Object.fromEntries(
    Object.entries(CLASS_COLORS).map(([id, color]) => ['Archetype.' + id, color]),
  ),
  'Elemental.Fire': '#fe9e4a',
  'Elemental.Frost': '#6fdeff',
  'Elemental.Lightning': '#e2e005',
  'Elemental.Poison': '#82d944',
  'Elemental.Soul': '#fe93f1',
}
const SLOT_COLORS = {
  melee: '#cdedfc',
  ranged: '#fec2a2',
  bow: '#b7c6a3',
  crossbow: '#cc93ac',
  armor: '#98b4dc',
  artifact: '#e5c7fa',
  quiver: '#c2b04e',
}

export function poolColor(pool) {
  if (pool === 'Weapon') return SLOT_COLORS.melee
  if (pool === 'Artifact') return SLOT_COLORS.artifact
  return POOL_COLORS[pool] || CLASS_COLORS.Utility
}
export function classColor(archetype) {
  return CLASS_COLORS[archetype] || CLASS_COLORS.Utility
}
export function slotColor(slot) {
  const key = slot?.toLowerCase()
  return (
    SLOT_COLORS[['helmet', 'chest', 'leggings', 'boots'].includes(key) ? 'armor' : key] ||
    CLASS_COLORS.Utility
  )
}
