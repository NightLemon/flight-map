import { spawnSync } from 'node:child_process'
import { existsSync, readdirSync } from 'node:fs'

// The data generator must run first; CI and the documented local command do so.
if (!existsSync('.cache/pages-public/reference/manifest.json')) {
  throw new Error('Run python scripts/build_pages_data.py before building Pages.')
}
if (readdirSync('.cache/pages-public').some((name) => name.startsWith('.pages-reference-'))) {
  throw new Error('A data build is unfinished. Finish or clean its staging directory before publishing.')
}
const result = spawnSync(process.execPath, [process.env.npm_execpath, 'run', 'build'], {
  stdio: 'inherit',
  env: { ...process.env, VITE_PUBLIC_REFERENCE: 'true', VITE_BASE_PATH: '/flight-map/' },
})
process.exit(result.status ?? 1)
