// 对比四类词条与「可洗词条 / 独特词条」的重合关系：
//   1. 独特装备自带词条中，哪些相对可洗词条独有
//   2. 护符词条中，哪些与可洗词条重复（并列出护符独有的作对照）
//   3. 附魔中，哪些与独特装备自带词条重复
//   4. 可洗词条中，哪些相对独特词条独有
//   另外给出四类按词条标识去重的总表（--all），用于「每个词条不重不漏加一遍」。
// 口径：一律按 effect ID 比较；可洗词条 = catalog.effects 中至少有一个
// kind=gear 且带 groups 的档位（与 prepareCatalog 收录到候选列表的条件一致）。
// 用法：node tools/compare-effects.mjs [--json] [--all]
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../', import.meta.url))
const read = (name) => JSON.parse(fs.readFileSync(path.join(root, 'public', name), 'utf8'))
const catalog = read('catalog.json')
const extras = read('extras.json')
const zh = read('zh.json')
const zhUnique = read('zh-unique.json')
const talTexts = read('talisman-texts.json')

const rollable = new Map()
for (const [id, effect] of Object.entries(catalog.effects || {})) {
  const tiers = (effect.tiers || []).filter((t) => t.kind === 'gear' && t.groups?.length)
  if (tiers.length) rollable.set(id, { ...effect, rollTiers: tiers })
}
const rollIds = new Set(rollable.keys())

const uniqueByEffect = new Map()
for (const [itemId, own] of Object.entries(extras.uniqueOwn || {})) {
  if (!own?.effect) continue
  let rec = uniqueByEffect.get(own.effect)
  if (!rec) {
    rec = { effect: own.effect, templates: new Set(), items: [] }
    uniqueByEffect.set(own.effect, rec)
  }
  if (own.template) rec.templates.add(own.template)
  rec.items.push(zh.itemsById?.[itemId] || catalog.items?.[itemId]?.name || itemId)
}
const uniqueIds = new Set(uniqueByEffect.keys())

const talByEffect = new Map()
for (const o of talTexts.options || []) {
  let rec = talByEffect.get(o.effect)
  if (!rec) {
    rec = { effect: o.effect, templates: [], talismans: new Set() }
    talByEffect.set(o.effect, rec)
  }
  rec.templates.push(o.template)
  rec.talismans.add(o.talismanName)
}

const enchants = new Map(Object.entries(catalog.enchantments || {}))
const uniqueEnch = extras.uniqueEnchantments || {}
const uniqueEnchName = (template) =>
  uniqueEnch[template]?.zhName || uniqueEnch[template]?.name || ''
const tplDesc = (template) =>
  zh.templates?.[template] || zhUnique?.[template] || uniqueEnch[template]?.text || ''
const effZh = (id, templates = []) => {
  for (const tpl of templates) {
    const name = uniqueEnchName(tpl)
    if (name) return name
  }
  return (
    talTexts.labels?.[id]?.zh ||
    zh.effectsById?.[id] ||
    zh.enchants?.[id]?.name ||
    zh.effects?.[catalog.effects?.[id]?.name] ||
    id.split('.').at(-1)
  )
}
const enchZh = (id) => zh.enchants?.[id]?.name || effZh(id)
const descOfUnique = (id) => {
  for (const tpl of uniqueByEffect.get(id)?.templates || []) {
    const desc = tplDesc(tpl)
    if (desc) return desc
  }
  return ''
}
const descOfTalisman = (id) =>
  talTexts.options.find((o) => o.effect === id && o.tier === 'III')?.desc || ''
const descOfRoll = (id) => {
  const tier = rollable.get(id)?.rollTiers.at(-1)
  return (tier && tplDesc(tier.template)) || tier?.text || ''
}
const descOfEnch = (id) => {
  const info = enchants.get(id)
  const tier = info?.tiers?.at(-1)
  return (tier && tplDesc(tier.template)) || zh.enchants?.[id]?.desc || tier?.text || ''
}
const plain = (rec, desc) => ({
  zhName: effZh(rec.effect, [...rec.templates]),
  desc,
  items: rec.items || [...rec.talismans],
})
const byName = (a, b) => a.zhName.localeCompare(b.zhName, 'zh')

const uniqueOnlyRaw = [...uniqueByEffect.values()].filter((r) => !rollIds.has(r.effect))
const uniqueOnly = uniqueOnlyRaw
  .map((r) => plain(r, descOfUnique(r.effect)))
  .sort(byName)
const talismanDuplicated = [...talByEffect.values()]
  .filter((r) => rollIds.has(r.effect))
  .map((r) => ({ ...plain(r, descOfTalisman(r.effect)), rollDesc: descOfRoll(r.effect) }))
  .sort(byName)
const talismanOnly = [...talByEffect.values()]
  .filter((r) => !rollIds.has(r.effect))
  .map((r) => plain(r, descOfTalisman(r.effect)))
  .sort(byName)
const enchDupIds = new Set([...enchants.keys()].filter((id) => uniqueIds.has(id)))
const enchantmentDuplicated = [...enchDupIds]
  .map((id) => ({
    zhName: enchZh(id),
    desc: descOfEnch(id),
    uniqueDesc: descOfUnique(id),
    items: uniqueByEffect.get(id).items,
  }))
  .sort(byName)
const uniqueEnchantOnly = uniqueOnlyRaw
  .filter((r) => r.effect.startsWith('SW.Enchantment.') && !enchDupIds.has(r.effect))
  .map((r) => plain(r, descOfUnique(r.effect)))
  .sort(byName)
const rollableOnly = [...rollable.keys()]
  .filter((id) => !uniqueIds.has(id))
  .map((id) => ({ zhName: effZh(id), desc: descOfRoll(id) }))
  .sort(byName)

const sourcesOf = new Map()
const addSource = (id, label) => {
  if (!sourcesOf.has(id)) sourcesOf.set(id, new Set())
  sourcesOf.get(id).add(label)
}
for (const id of rollable.keys()) addSource(id, '可洗')
for (const id of uniqueIds) addSource(id, '独特')
for (const id of talByEffect.keys()) addSource(id, '护符')
for (const id of enchants.keys()) addSource(id, '附魔')
const union = [...sourcesOf.entries()]
  .map(([id, sources]) => {
    const desc = sources.has('可洗')
      ? descOfRoll(id)
      : sources.has('独特')
        ? descOfUnique(id)
        : sources.has('护符')
          ? descOfTalisman(id)
          : descOfEnch(id)
    return {
      zhName: effZh(id, [...(uniqueByEffect.get(id)?.templates || [])]),
      desc,
      sources: [...sources],
    }
  })
  .sort(byName)

const result = {
  meta: {
    catalogEffects: Object.keys(catalog.effects || {}).length,
    rollableEffects: rollable.size,
    uniqueItems: Object.keys(extras.uniqueOwn || {}).length,
    uniqueEffects: uniqueByEffect.size,
    talismanEffects: talByEffect.size,
    talismanTiers: (talTexts.options || []).length,
    enchantments: enchants.size,
    unionEffects: union.length,
  },
  uniqueOnly,
  talismanDuplicated,
  talismanOnly,
  enchantmentDuplicated,
  uniqueEnchantOnly,
  rollableOnly,
  union,
}

if (process.argv.includes('--json')) {
  console.log(JSON.stringify(result, null, 2))
} else {
  const m = result.meta
  const out = [
    '口径：按词条标识精确匹配；可洗词条 = catalog.effects 中至少一个可重洗档位（kind=gear 且有 groups）。',
    '',
    `可洗词条 ${m.rollableEffects} 种（catalog.effects 共 ${m.catalogEffects} 种）`,
    `独特装备自带词条 ${m.uniqueItems} 件 / ${m.uniqueEffects} 种 effect`,
    `护符词条 ${m.talismanEffects} 种 effect / ${m.talismanTiers} 条档位`,
    `附魔 ${m.enchantments} 种`,
    `四类去重后不重不漏共 ${m.unionEffects} 种（--all 查看完整清单）`,
    '',
    `== 1. 独特词条中相对可洗词条独有：${uniqueOnly.length} 种 ==`,
  ]
  for (const r of uniqueOnly)
    out.push(
      `  ${r.zhName}：${r.desc || '（无描述）'}`,
      `      来源 ${r.items.join('、')}`,
    )
  out.push('', `== 2. 护符词条中相对可洗词条重复：${talismanDuplicated.length} 种 ==`)
  for (const r of talismanDuplicated)
    out.push(
      `  ${r.zhName}：${r.desc || '（无描述）'}（护符 ${r.items.join('、')}）`,
      `      可洗：${r.rollDesc || '（无描述）'}`,
    )
  out.push(
    '',
    `  （对照）护符独有 ${talismanOnly.length} 种：${talismanOnly.map((r) => r.zhName).join('、')}`,
    '',
    `== 3. 附魔中相对独特词条重复：${enchantmentDuplicated.length} 种 ==`,
  )
  for (const r of enchantmentDuplicated)
    out.push(
      `  ${r.zhName}：${r.desc || '（无描述）'}`,
      `      独特版：${r.uniqueDesc || '（无描述）'}`,
      `      带该词条的装备 ${r.items.join('、')}`,
    )
  out.push(
    '',
    `  （对照）仅独特版、附魔表中无同名 effect：${uniqueEnchantOnly.length} 种`,
    ...uniqueEnchantOnly.map(
      (r) => `    ${r.zhName}：${r.desc || '（无描述）'}  ← ${r.items.join('、')}`,
    ),
    '',
    `== 4. 可洗词条中相对独特词条独有：${rollableOnly.length} 种 ==`,
  )
  for (const r of rollableOnly) out.push(`  ${r.zhName}：${r.desc || '（无描述）'}`)
  if (process.argv.includes('--all'))
    out.push(
      '',
      `== 去重总表：${union.length} 种（每种只列一次） ==`,
      ...union.map(
        (r) => `  ${r.zhName}：${r.desc || '（无描述）'} [${r.sources.join('·')}]`,
      ),
    )
  console.log(out.join('\n'))
}
