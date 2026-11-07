// Production entry: serve the built UI plus the API on 127.0.0.1:8780.
// For development use `npm run dev` (vite serves the UI and mounts the same API).
import { spawn } from 'node:child_process'
import { SAVE_DIR, createApp } from './app.js'

const PORT = Number(process.env.PORT || 8780)

const server = createApp().listen(PORT, '127.0.0.1', () => {
  const url = `http://127.0.0.1:${server.address().port}/`
  console.log(`mcd2-batch listening on ${url}`)
  if (process.platform === 'win32' && process.env.MCD2_OPEN_BROWSER === '1')
    spawn('rundll32.exe', ['url.dll,FileProtocolHandler', url], {
      windowsHide: true,
      stdio: 'ignore',
    })
      .on('error', () => console.log(url))
      .unref()
  console.log(`saves: ${SAVE_DIR}`)
})
