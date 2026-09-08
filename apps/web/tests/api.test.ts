import { afterEach, describe, expect, it, vi } from 'vitest'
import { getJson } from '../src/api'

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals() })

describe('JSON API transport', () => {
  it.each([
    [undefined, '/api/v1/status'],
    ['', '/api/v1/status'],
    ['https://api.example.test', 'https://api.example.test/api/v1/status'],
    ['https://api.example.test/flight-map', 'https://api.example.test/flight-map/api/v1/status'],
    ['https://api.example.test/flight-map/', 'https://api.example.test/flight-map/api/v1/status'],
  ])('uses configured base %j for the actual JSON request', async (base, expectedUrl) => {
    vi.stubEnv('VITE_API_BASE_URL', base)
    const fetch = vi.fn(async () => new Response(JSON.stringify({ ready: true })))
    vi.stubGlobal('fetch', fetch)

    await expect(getJson<{ ready: boolean }>('/status')).resolves.toEqual({ ready: true })
    expect(fetch).toHaveBeenCalledWith(expectedUrl, expect.objectContaining({ cache: 'no-store' }))
  })
})
