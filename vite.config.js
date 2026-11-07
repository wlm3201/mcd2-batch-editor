import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { createApp } from './server/app.js'
import path from 'node:path'
import { glossarySource, writeGlossary } from './tools/build-glossary.mjs'

function glossaryPlugin() {
  return {
    name: 'mcd2-glossary',
    configResolved() {
      writeGlossary()
    },
    configureServer(server) {
      const data = ['catalog.json', 'zh.json'].map((name) =>
        path.resolve(server.config.publicDir, name),
      )
      const shared = ['src/lib/catalog.js', 'src/lib/tag-colors.js'].map((file) =>
        path.resolve(server.config.root, file),
      )
      const inputs = new Set([...data, ...shared])
      server.watcher.add([glossarySource, ...inputs])
      const refresh = (file) => {
        const changed = path.resolve(file)
        if (changed.startsWith(glossarySource + path.sep) || inputs.has(changed)) writeGlossary()
      }
      server.watcher.on('change', refresh).on('add', refresh)
    },
  }
}

// dev: mount the save API on the vite server itself, so `npm run dev` works alone
// (no separate backend process, no proxy). Production: `npm start` serves everything.
function apiPlugin() {
  return {
    name: 'mcd2-api',
    configureServer(server) {
      const app = createApp()
      server.middlewares.use((req, res, next) => {
        if (req.url.startsWith('/api/')) app(req, res)
        else next()
      })
    },
  }
}

export default defineConfig({
  plugins: [vue(), glossaryPlugin(), apiPlugin()],
  base: './',
  build: { outDir: 'dist' },
})
