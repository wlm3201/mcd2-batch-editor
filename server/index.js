// Production entry: serve the built UI plus the API on 127.0.0.1, starting at 8780.
// Like Vite, an occupied port is skipped (+1) instead of failing the launch.
// For development use `npm run dev` (vite serves the UI and mounts the same API).
import { spawn } from 'node:child_process'
import { SAVE_DIR, createApp } from './app.js'

const START_PORT = Number(process.env.PORT || 8780)
const MAX_TRIES = 20
const app = createApp()

function listen(port, triesLeft = MAX_TRIES) {
  const server = app.listen(port, '127.0.0.1')
  server.once('error', (err) => {
    if (err.code === 'EADDRINUSE' && triesLeft > 1 && port < 65535) {
      console.log(`mcd2-batch port ${port} is in use, trying ${port + 1}...`)
      listen(port + 1, triesLeft - 1)
      return
    }
    console.error(`mcd2-batch failed to start: ${err.message}`)
    process.exitCode = 1
  })
  server.once('listening', () => {
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
  return server
}

listen(START_PORT)
