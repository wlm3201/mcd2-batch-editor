const $ = (id) => document.getElementById(id)
const data = JSON.parse($('glossary-data').textContent)
const categories = data.categories
const scopes = new Map(data.filters.map((p) => [p.id, p]))
const copy = {
  title: ['词条总览', 'Effect guide'],
  search: ['搜索词条', 'Search effects'],
  placeholder: ['搜索名称或效果', 'Search names or effects'],
  all: ['全部', 'All'],
  scope: ['范围', 'Scope'],
  tier: ['阶数', 'Tier'],
  offensive: ['攻击', 'Attack'],
  defensive: ['防御', 'Defense'],
  utility: ['实用', 'Utility'],
  other: ['其他', 'Other'],
  empty: ['没有匹配的词条', 'No matching effects'],
  emptyHint: [
    '试试其他名称、效果，或将范围改为“全部”。',
    'Try another search or set the scope to All.',
  ],
}
const norm = (s) => s.normalize('NFKC').toLowerCase()
const query = $('q')
let lang = 'zh',
  pool = '',
  rank = 'III'
const label = (key) => copy[key]?.[lang === 'zh' ? 0 : 1] || key
const name = (item) =>
  typeof item === 'string' ? item : item?.[lang] || item?.[lang === 'zh' ? 'en' : 'zh']
const categoryLabel = (category) => name(data.categoryLabels[category]) || label(category)
function el(tag, cls, text) {
  const node = document.createElement(tag)
  if (cls) node.className = cls
  if (text !== undefined) node.textContent = text
  return node
}
function readRoute() {
  const hash = location.hash.slice(1),
    args = new URLSearchParams(hash)
  const legacy = hash.startsWith('sec-') ? hash.slice(4) : args.get('pool')
  const preset = legacy === 'Artifact' ? 'slot:artifact' : legacy
  lang = args.get('lang') === 'en' ? 'en' : 'zh'
  pool = scopes.has(preset) ? preset : ''
  rank = data.ranks.includes(args.get('tier')) ? args.get('tier') : 'III'
  query.value = args.get('q') || ''
  return args.get('effect')
}
function writeRoute() {
  const params = new URLSearchParams()
  if (lang === 'en') params.set('lang', lang)
  if (pool) params.set('pool', pool)
  if (rank !== 'III') params.set('tier', rank)
  if (query.value.trim()) params.set('q', query.value.trim())
  const hash = '#' + params
  if (hash !== (location.hash || '#')) history.replaceState(null, '', hash)
}
// Search both languages and IDs without exposing the alternate language or ID on cards.
const index = new Map(
  data.effects.map((e) => [
    e.id,
    new Map(
      e.tiers.map((tier) => [
        tier.rank,
        norm(
          [
            e.id,
            e.en,
            e.zh,
            tier.en,
            tier.zh,
            ...tier.slots.flatMap((slot) => [data.slots[slot].zh, data.slots[slot].en]),
          ].join(' '),
        ),
      ]),
    ),
  ]),
)
function choice(group, value, text) {
  const node = el('label', 'choice'),
    input = el('input')
  input.type = 'radio'
  input.name = group
  input.value = value
  node.append(input, el('span', '', text))
  return node
}
function controls() {
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en'
  document.title = label('title') + ' · MCD2'
  for (const node of document.querySelectorAll('[data-i18n]'))
    node.textContent = label(node.dataset.i18n)
  for (const b of document.querySelectorAll('[data-lang]'))
    b.setAttribute('aria-pressed', b.dataset.lang === lang)
  query.placeholder = label('placeholder')
  $('ranks').replaceChildren(...data.ranks.map((tier) => choice('tier', tier, tier)))
  $('pools').replaceChildren(
    choice('pool', '', label('all')),
    ...data.filters.map((p) => choice('pool', p.id, name(p))),
  )
}
function matchesScope(tier, scope) {
  return scope.slots
    ? tier.slots.some((slot) => scope.slots.includes(slot))
    : tier.pools.includes(scope.id)
}
function tagFor(tag) {
  const active = !pool || tag.filter === pool
  const node = el('span', 'tag' + (active ? ' here' : ''), name(tag))
  node.dataset.tag = tag.id
  if (active) node.style.setProperty('--tag-color', tag.color)
  return node
}
function cardFor(e) {
  const card = el('article', 'effect-card')
  card.dataset.effect = card.id = e.id
  const head = el('div', 'card-head')
  if (e.icon) {
    const image = el('img')
    image.src = e.icon
    image.alt = ''
    image.width = image.height = 34
    head.append(image)
  }
  const title = el('h3', '', name(e))
  title.id = 'name-' + e.id
  card.setAttribute('aria-labelledby', title.id)
  head.append(title, el('span', 'tier', e.tier.rank))
  const desc = el('p', 'value')
  for (const part of name(e.tier).split(/(-?\d+(?:[.,]\d+)?[%％]?)/))
    desc.append(/^-?\d/.test(part) ? el('b', '', part) : document.createTextNode(part))
  const tags = el('div', 'tags')
  tags.append(
    ...data.tags
      .filter((tag) => (tag.slot ? e.tier.slots.includes(tag.slot) : e.tier.pools.includes(tag.id)))
      .map(tagFor),
  )
  card.append(head, desc, tags)
  return card
}
function groupFor(type, entries) {
  const section = el('section', 'group')
  section.dataset.category = type
  const title = el('h2', 'group-title', categoryLabel(type))
  title.id = 'group-' + type
  title.append(el('small', '', String(entries.length)))
  section.setAttribute('aria-labelledby', title.id)
  const cards = el('div', 'cards')
  cards.append(...entries.map(cardFor))
  section.append(title, cards)
  return section
}
function render() {
  const words = norm(query.value.trim()).split(/\s+/).filter(Boolean)
  const available = data.effects.flatMap((effect) => {
    const tier = effect.tiers.find((t) => t.rank === rank)
    return tier ? [{ ...effect, tier }] : []
  })
  const matches = available.filter(
    (e) =>
      (!pool || matchesScope(e.tier, scopes.get(pool))) &&
      words.every((w) => index.get(e.id).get(rank).includes(w)),
  )
  for (const input of $('pools').querySelectorAll('input')) input.checked = input.value === pool
  for (const input of $('ranks').querySelectorAll('input')) input.checked = input.value === rank
  $('count').textContent =
    lang === 'zh'
      ? matches.length + ' / ' + available.length + ' 项'
      : matches.length + ' of ' + available.length + ' effects'
  $('empty').hidden = matches.length > 0
  $('effect-list').replaceChildren(
    ...categories.flatMap((type) => {
      const entries = matches.filter((e) => e.category === type)
      return entries.length ? [groupFor(type, entries)] : []
    }),
  )
}
function update() {
  render()
  writeRoute()
}
$('search').addEventListener('submit', (e) => e.preventDefault())
query.addEventListener('input', update)
$('pools').addEventListener('change', (e) => {
  pool = e.target.value
  update()
})
$('ranks').addEventListener('change', (e) => {
  rank = e.target.value
  update()
})
document.querySelector('.languages').addEventListener('click', (e) => {
  const b = e.target.closest('[data-lang]')
  if (b) {
    lang = b.dataset.lang
    controls()
    update()
  }
})
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    query.focus()
    query.select()
  } else if (e.key === 'Escape' && document.activeElement === query && query.value) {
    e.preventDefault()
    query.value = ''
    update()
  }
})
function route() {
  const effect = readRoute()
  controls()
  render()
  const card = effect && document.getElementById(effect)
  if (card?.matches('.effect-card')) {
    card.classList.add('bookmark')
    requestAnimationFrame(() => card.scrollIntoView({ block: 'center' }))
  }
}
window.addEventListener('hashchange', route)
if (data.brand) {
  $('brand-icon').src = data.brand
  $('favicon').href = data.brand
} else $('brand-icon').hidden = true
$('version').textContent = 'v' + data.version
if (/Mac|iPad|iPhone/.test(navigator.platform)) $('shortcut').textContent = '⌘ K'
route()
