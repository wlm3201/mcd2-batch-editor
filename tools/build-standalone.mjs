// A single offline file, including the glossary. Browser and desktop use the same file controls.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { build } from 'vite'

const root = fileURLToPath(new URL('../', import.meta.url))
const result = await build({ root, mode: 'browser', build: { write: false, modulePreload: false } })
const js = result.output.filter((file) => file.type === 'chunk')
const css = result.output.filter((file) => file.fileName.endsWith('.css'))
if (js.length !== 1 || !css.length) throw new Error('Expected one inline JavaScript bundle and CSS')

const local = (name) => path.join(root, 'public', name)
const data = {}
for (const name of [
  'catalog.json',
  'zh.json',
  'extras.json',
  'zh-unique.json',
  'world-quests.json',
])
  data[name] = JSON.parse(fs.readFileSync(local(name), 'utf8'))
const catalog = data['catalog.json']
const iconNames = new Set()
for (const section of ['items', 'effects', 'enchantments']) {
  for (const { icon } of Object.values(catalog[section])) {
    if (icon) iconNames.add(icon)
  }
}
const icons = {}
const mimeTypes = { '.png': 'image/png', '.webp': 'image/webp' }
for (const name of [...iconNames].sort()) {
  const type = mimeTypes[path.extname(name).toLowerCase()]
  if (!type || /[/\\]/.test(name)) throw new Error(`Unsupported catalog icon: ${name}`)
  icons[name] = `data:${type};base64,` + fs.readFileSync(local('icons/' + name), 'base64')
}
const pools = fs.readFileSync(local('pools.html'), 'utf8')
const bundle = JSON.stringify({ data, icons, pools }).replaceAll('<', '\\u003c')
const html = [
  '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
  '<meta name="viewport" content="width=device-width,initial-scale=1"><title>MCD2 Batch Editor</title>',
  '<style>',
  ...css.map((file) => file.source),
  '</style></head><body><div id="app"></div>',
  '<script>window.__MCD2__=',
  bundle,
  '</script><script type="module">',
  js[0].code.replace(/<\/script/gi, '<\\/script'),
  '</script><script type="text/plain" id="third-party-notices">',
  '</script></body></html>',
].join('')
const out = path.join(root, 'build/MCD2BatchEditor-standalone.html')
fs.mkdirSync(path.dirname(out), { recursive: true })
fs.writeFileSync(out, html)
console.log(out)
