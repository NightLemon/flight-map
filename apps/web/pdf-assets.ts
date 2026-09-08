import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { createRequire } from 'node:module'
import type { Plugin } from 'vite'

// Both dev and production serve the exact installed PDF.js resources locally.
export function pdfAssets(): Plugin {
  const root = dirname(createRequire(import.meta.url).resolve('pdfjs-dist/package.json'))
  const files = new Map<string, string>()
  for (const folder of ['cmaps', 'standard_fonts', 'wasm', 'iccs']) {
    for (const name of readdirSync(join(root, folder))) files.set(`pdfjs/${folder}/${name}`, join(root, folder, name))
  }
  return {
    name: 'flightmap-local-pdf-resources',
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const path = request.url?.split('?')[0].replace(/^\//, '') ?? ''
        const file = files.get(path)
        if (!file) { next(); return }
        response.setHeader('Content-Type', path.endsWith('.wasm') ? 'application/wasm' : path.endsWith('.js') ? 'text/javascript' : 'application/octet-stream')
        response.end(readFileSync(file))
      })
    },
    generateBundle() {
      for (const [fileName, path] of files) this.emitFile({ type: 'asset', fileName, source: readFileSync(path) })
    },
  }
}
