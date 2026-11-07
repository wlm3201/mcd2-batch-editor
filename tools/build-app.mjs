// Builds a distributable desktop package: extract the zip, double-click start.bat.
// Bundles the Express server into a single file (no node_modules needed at runtime),
// copies the built frontend and data, and writes the launcher script.
// usage: node tools/build-app.mjs
import { build } from 'vite'
import { build as buildServer } from 'esbuild'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.join(__dirname, '..')
const OUT = path.join(ROOT, 'build', 'MCD2BatchEditor')

console.log('[1/4] building frontend...')
await build({ root: ROOT })

console.log('[2/4] bundling server...')
await buildServer({
  absWorkingDir: ROOT,
  entryPoints: ['server/index.js'],
  bundle: true,
  platform: 'node',
  format: 'cjs',
  outfile: 'build/server.cjs',
  minify: true,
})

console.log('[3/4] assembling package...')
// Refresh generated assets only. An in-place desktop run may have created backups here.
fs.rmSync(path.join(OUT, 'dist'), { recursive: true, force: true })
fs.mkdirSync(OUT, { recursive: true })
fs.cpSync(path.join(ROOT, 'dist'), path.join(OUT, 'dist'), { recursive: true })
fs.cpSync(path.join(ROOT, 'build', 'server.cjs'), path.join(OUT, 'server.cjs'))

// launcher: use system Node if available, otherwise tell the user
fs.writeFileSync(
  path.join(OUT, 'start.bat'),
  `@echo off
cd /d "%~dp0"
title MCD2 Batch Editor
echo Starting MCD2 Batch Editor...
echo.
where node >nul 2>nul
if %errorlevel% neq 0 (
  echo [ERROR] Node.js is not installed.
  echo Please install Node.js from https://nodejs.org and try again.
  pause
  exit /b 1
)
set "MCD2_OPEN_BROWSER=1"
node server.cjs
pause
`,
)

fs.writeFileSync(
  path.join(OUT, 'README.txt'),
  `MCD2 Batch Editor
=================

A save editor for Minecraft Dungeons II hero saves.

How to use:
  1. Double-click start.bat (requires Node.js: https://nodejs.org)
  2. Your browser opens the editor automatically
  3. Pick your save from the dropdown, edit, then press Save

Your save files are in:
  %LOCALAPPDATA%\\Dungeons2\\Saved\\SaveGames\\

Every write creates a dated copy in the backups folder next to start.bat.

If port 8780 is busy, set another:  set "PORT=9000" && start.bat
`,
)

console.log('[4/4] done!')
const size = (() => {
  let total = 0
  const walk = (d) => {
    for (const f of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, f.name)
      if (f.isDirectory()) walk(p)
      else total += fs.statSync(p).size
    }
  }
  walk(OUT)
  return (total / 1024 / 1024).toFixed(1)
})()
console.log(`  package: ${OUT} (${size} MB)`)
console.log(`  zip it up and distribute!`)
