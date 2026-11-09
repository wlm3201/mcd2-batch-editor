// The standalone build supplies only inert data. File access always uses the same UI.
const embedded = window.__MCD2__
export const browserMode = import.meta.env.MODE === 'browser' || Boolean(embedded)
export const iconUrl = (name) =>
  name?.startsWith('data:image/webp;base64,')
    ? name
    : embedded
      ? embedded.icons[name]
      : `icons/${name}`

export const poolsUrl = embedded
  ? URL.createObjectURL(new Blob([embedded.pools], { type: 'text/html;charset=utf-8' }))
  : 'pools.html?v=' + Date.now()

async function readJson(res, name) {
  const type = res.headers.get('content-type') || ''
  if (!type.includes('json')) {
    const text = await res.text()
    throw new Error(`${name} · 返回不是 JSON（${type || '无 Content-Type'}）：${text.slice(0, 48).trim()}`)
  }
  return res.json()
}

export async function loadData(name) {
  if (embedded) return embedded.data[name]
  // Keep rule data in sync with the UI after deploying a new build.
  const res = await fetch(name, { cache: 'no-cache' })
  if (!res.ok) throw new Error(`${name} · HTTP ${res.status}`)
  return readJson(res, name)
}

export async function api(path, body) {
  const res = await fetch(
    path,
    body
      ? {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }
      : { cache: 'no-store' },
  )
  const result = await readJson(res, path)
  if (!res.ok)
    throw Object.assign(new Error(result.error || `HTTP ${res.status}`), { status: res.status })
  return result
}

export function download(name, text) {
  const url = URL.createObjectURL(new Blob([text], { type: 'application/octet-stream' }))
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
