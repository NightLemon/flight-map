import { createHash, webcrypto } from 'node:crypto'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchChartPdf } from '../src/pdf-client'
import { release } from './fixtures'

const bytes = new TextEncoder().encode('%PDF-1.4\nSYNTHETIC TRANSPORT TEST ONLY')
const digest = createHash('sha256').update(bytes).digest('hex')
const headers = { 'Content-Type': 'application/pdf', 'X-FlightMap-Release-Id': release('dtpp').id,
  'X-FlightMap-Chart-Id': 'chart-one', 'X-FlightMap-Pdf-Sha256': digest }

beforeEach(() => vi.stubGlobal('crypto', webcrypto))
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals() })
describe('pinned PDF transport', () => {
  it.each([
    [undefined, '/api/v1/charts/chart-one/pdf'],
    ['', '/api/v1/charts/chart-one/pdf'],
    ['https://api.example.test', 'https://api.example.test/api/v1/charts/chart-one/pdf'],
    ['https://api.example.test/flight-map', 'https://api.example.test/flight-map/api/v1/charts/chart-one/pdf'],
    ['https://api.example.test/flight-map/', 'https://api.example.test/flight-map/api/v1/charts/chart-one/pdf'],
  ])('uses configured base %j for the API record endpoint without browser credentials and checks its bytes', async (base, expectedUrl) => {
    vi.stubEnv('VITE_API_BASE_URL', base)
    const fetch = vi.fn(async () => new Response(bytes, { headers })); vi.stubGlobal('fetch', fetch)
    const result = await fetchChartPdf('chart-one', release('dtpp'), 'history', new AbortController().signal)
    expect(Array.from(result)).toEqual(Array.from(bytes))
    expect(fetch).toHaveBeenCalledWith(`${expectedUrl}?release_id=${release('dtpp').id}&mode=history`, expect.objectContaining({ cache: 'no-store', credentials: 'omit', redirect: 'error' }))
  })
  it.each(['X-FlightMap-Release-Id', 'X-FlightMap-Chart-Id'])('rejects a mismatched %s', async (header) => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(bytes, { headers: { ...headers, [header]: 'different' } })))
    await expect(fetchChartPdf('chart-one', release('dtpp'), 'current', new AbortController().signal)).rejects.toMatchObject({ status: 409 })
  })
  it.each(['', '0'.repeat(64)])('rejects a missing or mismatched hash', async (hash) => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(bytes, { headers: { ...headers, 'X-FlightMap-Pdf-Sha256': hash } })))
    await expect(fetchChartPdf('chart-one', release('dtpp'), 'current', new AbortController().signal)).rejects.toThrow(/哈希/)
  })
  it('retains the upstream status for panel-local error handling', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'Official service timed out' }), { status: 504 })))
    await expect(fetchChartPdf('chart-one', release('dtpp'), 'current', new AbortController().signal)).rejects.toMatchObject({ status: 504 })
  })
})
