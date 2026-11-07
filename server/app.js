import express from 'express'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { createHash, randomUUID } from 'node:crypto'
import { attach } from '../src/lib/save.js'
import { parseSave } from '../src/lib/codec.js'

export const SAVE_DIR =
  process.env.MCD2_SAVE_DIR ||
  path.join(
    process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local'),
    'Dungeons2',
    'Saved',
    'SaveGames',
  )
const NAME_RE = /^Character[\w-]*\.sav$/i
const revision = (bytes) => createHash('sha256').update(bytes).digest('hex')

export function createApp({ saveDir = SAVE_DIR, root = process.cwd() } = {}) {
  const app = express()
  // A browser can resolve an unrelated hostname to loopback. Disk access is
  // reserved for the local editor origin, even after such a DNS change.
  app.use('/api', (req, res, next) => {
    res.set('Cache-Control', 'no-store')
    const host = req.get('host') || ''
    const origin = req.get('origin')
    if (
      !/^(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$/i.test(host) ||
      (origin && origin !== req.protocol + '://' + host)
    )
      return res.status(403).json({ error: 'Open the editor on localhost to access disk saves.' })
    next()
  })
  app.use(express.json({ limit: '20mb' }))

  app.get('/api/health', (_req, res) => res.json({ ok: true, saveDir }))
  app.get('/api/saves', (_req, res, next) => {
    try {
      const saves = fs
        .readdirSync(saveDir, { withFileTypes: true })
        .filter((entry) => entry.isFile() && NAME_RE.test(entry.name))
        .map(({ name }) => {
          const s = fs.statSync(path.join(saveDir, name))
          return { name, size: s.size, mtime: s.mtimeMs }
        })
        .sort((a, b) => b.mtime - a.mtime)
      res.json({ dir: saveDir, saves })
    } catch (err) {
      if (err.code === 'ENOENT') return res.json({ dir: saveDir, saves: [] })
      next(err)
    }
  })

  app.get('/api/open/:name', (req, res, next) => {
    const { name } = req.params
    if (!NAME_RE.test(name)) return res.status(400).json({ error: 'Invalid save name' })
    try {
      const bytes = fs.readFileSync(path.join(saveDir, name))
      res.json({ name, text: bytes.toString('utf8'), revision: revision(bytes) })
    } catch (err) {
      next(err)
    }
  })

  app.post('/api/save', (req, res, next) => {
    const { name, text, revision: expected } = req.body || {}
    if (typeof name !== 'string' || !NAME_RE.test(name) || typeof text !== 'string')
      return res.status(400).json({ error: 'Invalid save name or contents' })
    if (typeof expected !== 'string' || !/^[a-f0-9]{64}$/.test(expected))
      return res.status(428).json({ error: 'Reopen the save before writing it.' })
    let nextHero
    try {
      nextHero = attach(parseSave(text))
    } catch (err) {
      return res.status(400).json({ error: err.message })
    }

    const file = path.join(saveDir, name)
    let pending
    try {
      const original = fs.readFileSync(file)
      const changedOnDisk = () =>
        res
          .status(409)
          .json({ error: 'The save changed on disk. Reopen it or export your edits as a copy.' })
      if (revision(original) !== expected) return changedOnDisk()
      if (text === original.toString('utf8'))
        return res.json({ written: name, backup: null, revision: expected })

      const hero = attach(parseSave(original.toString('utf8')))
      if (
        hero.bodyKey !== nextHero.bodyKey ||
        hero.body.MetaData?.CharacterId !== nextHero.body.MetaData?.CharacterId
      )
        return res
          .status(400)
          .json({ error: 'The character ID or save format differs from the open file.' })

      const backupRoot = path.join(root, 'backups')
      fs.mkdirSync(backupRoot, { recursive: true })
      const stamp = new Date().toISOString().replace(/[:.]/g, '-')
      const backup = path.join(fs.mkdtempSync(path.join(backupRoot, stamp + '-')), name)
      fs.writeFileSync(backup, original, { flag: 'wx', flush: true })

      pending = path.join(saveDir, name + '.' + randomUUID() + '.tmp')
      fs.writeFileSync(pending, text, { flag: 'wx', flush: true })
      if (revision(fs.readFileSync(file)) !== expected) return changedOnDisk()
      fs.renameSync(pending, file)
      pending = undefined
      res.json({ written: name, backup: path.relative(root, backup), revision: revision(text) })
    } catch (err) {
      next(err)
    } finally {
      if (pending) fs.rmSync(pending, { force: true })
    }
  })

  app.use('/api', (err, _req, res, _next) => {
    res.status(err.status || (err.code === 'ENOENT' ? 404 : 500)).json({ error: err.message })
  })
  app.use(express.static(path.join(root, 'dist')))
  app.use((req, res, next) => {
    if (req.method === 'GET' && !req.path.startsWith('/api/'))
      return res.sendFile(path.join(root, 'dist', 'index.html'))
    next()
  })
  return app
}
