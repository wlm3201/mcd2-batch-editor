// The glossary is also distributed on its own, so its code, texts and images travel together.
import fs from 'node:fs'
import path from 'node:path'
import { randomUUID } from 'node:crypto'
import { fileURLToPath, pathToFileURL } from 'node:url'
import {
  CATEGORY_ORDER,
  POOL_ZH,
  ROLL_SLOT_LABELS,
  TIERS,
  brandItemFor,
  orderedIds,
  prepareCatalog,
} from '../src/lib/catalog.js'
import { poolColor, slotColor } from '../src/lib/tag-colors.js'

const root = fileURLToPath(new URL('../', import.meta.url))
export const glossarySource = path.join(root, 'src', 'glossary')
const publicRoot = path.join(root, 'public')
const read = (file) => fs.readFileSync(file, 'utf8')

export function renderGlossary(
  dir = publicRoot,
  raw = JSON.parse(read(path.join(dir, 'catalog.json'))),
) {
  const catalog = prepareCatalog(raw, JSON.parse(read(path.join(dir, 'zh.json'))))
  const poolsUsed = new Set()
  const poolLabels = raw.meta?.labels?.pools || {}
  const poolLabel = (id, language) => {
    const native = poolLabels[id]
    return (
      (typeof native === 'string' ? native : native?.[language]) ||
      (language === 'zh' && POOL_ZH[id]) ||
      id.split('.').at(-1)
    )
  }

  function image(name) {
    if (!name) return ''
    const mime = { '.webp': 'image/webp', '.png': 'image/png' }[path.extname(name)]
    if (!mime || /[/\\]/.test(name)) throw Error('Invalid glossary icon: ' + name)
    return 'data:' + mime + ';base64,' + fs.readFileSync(path.join(dir, 'icons', name), 'base64')
  }

  const effects = [...catalog.effects.values()].map((effect) => {
    const tiers = TIERS.flatMap((rank) => {
      const tier = effect.tiers.get(rank)
      if (!tier) return []
      for (const pool of tier.groups) poolsUsed.add(pool)
      return [
        {
          rank,
          zh: tier.zhText,
          en: tier.text,
          pools: [...tier.groups],
          slots: tier.slots,
        },
      ]
    })
    return {
      id: effect.effect,
      zh: effect.zhName,
      en: effect.name,
      category: effect.category,
      icon: image(effect.icon),
      tiers,
    }
  })
  const poolIds = [...new Set([...Object.keys(POOL_ZH), ...poolsUsed])].filter(
    (id) => id !== 'Weapon' && poolsUsed.has(id),
  )
  const pools = poolIds.map((id) => ({
    id,
    zh: poolLabel(id, 'zh'),
    en: poolLabel(id, 'en'),
    color: poolColor(id),
    family: id.startsWith('Archetype.')
      ? 'archetypes'
      : id.startsWith('Elemental.')
        ? 'elements'
        : 'gear',
  }))
  // Keep the pool index order, then sort effects with the same first pool by name.
  const firstPool = (e) => poolIds.findIndex((p) => e.tiers.at(-1).pools.includes(p))
  effects.sort((a, b) => firstPool(a) - firstPool(b) || a.en.localeCompare(b.en, 'en'))
  const slotFamilies = {
    melee: ['melee'],
    ranged: ['ranged', 'bow', 'crossbow'],
    armor: ['armor'],
    artifact: ['artifact', 'quiver'],
  }
  const slotTags = Object.entries(ROLL_SLOT_LABELS).map(([slot, labels]) => ({
    id: 'slot:' + slot,
    ...labels,
    slot,
    filter:
      'slot:' + Object.keys(slotFamilies).find((family) => slotFamilies[family].includes(slot)),
    color: slotColor(slot),
  }))
  // Native slot eligibility already includes artifacts; do not display their pool a second time.
  const poolTags = pools.filter((p) => p.id !== 'Artifact').map((p) => ({ ...p, filter: p.id }))
  const model = {
    version: raw.meta.localVerification.version,
    brand: image(brandItemFor(catalog)?.icon),
    categories: orderedIds(
      CATEGORY_ORDER,
      effects.map((effect) => effect.category),
    ),
    categoryLabels: raw.meta?.labels?.categories || {},
    tags: [...slotTags, ...poolTags],
    filters: [
      ...slotTags
        .filter((tag) => Object.hasOwn(slotFamilies, tag.slot))
        .map((tag) => ({ ...tag, slots: slotFamilies[tag.slot] })),
      ...poolTags,
    ],
    slots: ROLL_SLOT_LABELS,
    ranks: TIERS,
    effects,
  }
  const parts = {
    STYLE: read(path.join(glossarySource, 'style.css')),
    DATA: JSON.stringify(model).replaceAll('<', '\\u003c'),
    SCRIPT: read(path.join(glossarySource, 'page.js')).replace(/<\/script/gi, '<\\/script'),
  }
  return read(path.join(glossarySource, 'index.html')).replace(
    /\/\* GLOSSARY_(STYLE|DATA|SCRIPT) \*\//g,
    (_, key) => parts[key],
  )
}

export function writeGlossary(dir = publicRoot) {
  const out = path.join(dir, 'pools.html')
  const html = renderGlossary(dir)
  if (fs.existsSync(out) && read(out) === html) return
  const temp = out + '.' + randomUUID() + '.tmp'
  try {
    fs.writeFileSync(temp, html)
    fs.renameSync(temp, out)
  } finally {
    fs.rmSync(temp, { force: true })
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const dir = process.argv[2] ? path.resolve(process.argv[2]) : publicRoot
  if (process.argv[3] === '--stdin') {
    process.stdout.write(renderGlossary(dir, JSON.parse(fs.readFileSync(0, 'utf8'))))
  } else {
    writeGlossary(dir)
    console.log(path.join(dir, 'pools.html'))
  }
}
