import { beforeEach, describe, expect, it, vi } from 'vitest'

const revision = 'a'.repeat(40)
const manifest = {
  schema: 1, source: { name: 'Synthetic reference', revision, updated_at: '2026-09-08T01:00:00Z' },
  tiles: { airports: ['21-26', '22-26'], runways: ['21-26', '22-26'], navaids: [] },
  counts: {}, disclaimer: 'Synthetic test data', review: null,
}
const feature = (id: string, coordinates = [-74, 40.5]) => ({
  type: 'Feature', id, geometry: { type: 'Point', coordinates }, properties: { id, kind: 'airport' },
})
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } })

beforeEach(() => { vi.resetModules(); vi.unstubAllGlobals() })

describe('public reference data', () => {
  it('fetches only the manifest at overview zoom and lazy-loads matching viewport cells', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(json(manifest)).mockImplementation(() => json({ type: 'FeatureCollection', features: [feature('1'), feature('2', [10, 20])] }))
    vi.stubGlobal('fetch', fetcher)
    const api = await import('../src/public-data')
    const source = await api.loadPublicManifest()
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect((await api.loadPublicFeatures(source, ['airports'], { zoom: 3, bounds: [-180, -80, 180, 80] })).features).toHaveLength(0)
    expect(fetcher).toHaveBeenCalledTimes(1)
    const result = await api.loadPublicFeatures(source, ['airports'], { zoom: 8, bounds: [-74.5, 40.1, -73.5, 40.8] })
    expect(result.features.map((item) => item.id)).toEqual(['1'])
    expect(fetcher.mock.calls[1][0]).toBe(`/reference/${revision}/tiles/airports/21-26.json`)
    await api.loadPublicFeatures(source, ['airports'], { zoom: 8, bounds: [-74.5, 40.1, -73.5, 40.8] })
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('loads search on demand, ranks exact codes first and uses the fixed revision for details', async () => {
    const id = 'ourairports:airport:3797'
    const fetcher = vi.fn().mockResolvedValueOnce(json(manifest))
      .mockResolvedValueOnce(json([{ id: 'other', identifier: 'AAAA', name: 'Test JFK park' }, { id, identifier: 'KJFK', iata_code: 'JFK', name: 'Synthetic test airport' }]))
      .mockResolvedValueOnce(json({ [id]: { airport: { id }, communications: [], runways: [] } }))
    vi.stubGlobal('fetch', fetcher)
    const api = await import('../src/public-data')
    expect((await api.searchPublicAirports('jfk'))[0].id).toBe(id)
    expect(fetcher).toHaveBeenCalledTimes(2)
    expect((await api.loadPublicAirport(id)).airport.id).toBe(id)
    expect(fetcher.mock.calls[2][0]).toBe(`/reference/${revision}/airports/213.json`)
    await expect(api.loadPublicAirport('../secrets')).rejects.toThrow('无效')
    expect(fetcher).toHaveBeenCalledTimes(3)
  })

  it('uses country shards, aliases and the composite data revision when present', async () => {
    const datasetRevision = 'b'.repeat(40)
    const countryManifest = {
      ...manifest,
      dataset_revision: datasetRevision,
      review: { reviewed_at: '2026-09-08', source_revision: revision, sha256: 'c'.repeat(64), correction_count: 1, note_count: 2 },
      coverage: [{ country: 'CN', airports: 2, airports_with_communications: 1, airports_with_frequencies: 2, runways: 3, navaids: 1, enriched_airports: 1 }],
      sources: [{ id: 'ourairports', name: 'OurAirports', url: 'https://ourairports.com', license: 'Public Domain', license_url: 'https://ourairports.com', updated_at: '2026-09-08T01:00:00Z', scope: 'global', airport_count: 2 }],
    }
    const hits = [
      { id: 'ourairports:airport:3', identifier: 'AAAA', name: 'Small field without codes', icao_id: '', iata_code: '', type: 'small_airport', country: 'CN' },
      { id: 'ourairports:airport:1', identifier: 'ZBAD', name: 'Beijing Daxing International Airport', icao_id: 'ZBAD', iata_code: 'PKX', aliases: ['北京大兴国际机场'], type: 'large_airport', scheduled_service: 'yes', country: 'CN' },
      { id: 'ourairports:airport:2', identifier: 'ZBXX', name: 'Small field', aliases: ['北京测试机场'], type: 'small_airport', country: 'CN' },
    ]
    const fetcher = vi.fn().mockResolvedValueOnce(json(countryManifest)).mockResolvedValueOnce(json(hits))
      .mockResolvedValueOnce(json({ 'ourairports:airport:1': { airport: { id: 'ourairports:airport:1' }, communications: [], runways: [], references: [] } }))
    vi.stubGlobal('fetch', fetcher)
    const api = await import('../src/public-data')
    const source = await api.loadPublicManifest()
    expect(api.publicDataRevision(source)).toBe(datasetRevision)
    expect((await api.searchPublicAirports('', undefined, 'CN')).map((item) => item.identifier)).toEqual(['ZBAD', 'AAAA', 'ZBXX'])
    expect(fetcher.mock.calls[1][0]).toBe(`/reference/${datasetRevision}/search/CN.json`)
    expect((await api.searchPublicAirports('大兴', undefined, 'CN'))[0].identifier).toBe('ZBAD')
    await expect(api.searchPublicAirports('', undefined, 'ZZ')).rejects.toThrow('无效')
    expect((await api.loadPublicAirport('ourairports:airport:1')).airport.id).toBe('ourairports:airport:1')
    expect(fetcher.mock.calls[2][0]).toBe(`/reference/${datasetRevision}/airports/1.json`)
  })

  it('handles crossing lines and date-line bounds without drawing their long arc', async () => {
    const { publicGeometryIntersects: intersects } = await import('../src/public-data')
    expect(intersects({ type: 'LineString', coordinates: [[-80, 40], [-70, 40]] }, [-75, 39, -74, 41])).toBe(true)
    const line = { type: 'LineString' as const, coordinates: [[179, 10], [-179, 11]] }
    expect(intersects(line, [178, 9, -178, 12])).toBe(true)
    expect(intersects(line, [-1, 9, 1, 12])).toBe(false)
    expect(intersects({ type: 'MultiLineString', coordinates: [[[179, 10], [180, 10.5]], [[-180, 10.5], [-179, 11]]] }, [-180, 10, -178, 12])).toBe(true)
    expect(intersects({ type: 'Point', coordinates: [-179, 10] }, [178, 9, -178, 12])).toBe(true)
  })

  it('cancels requests and never caches an HTTP failure', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(new Response('', { status: 503 })).mockResolvedValueOnce(json(manifest))
    vi.stubGlobal('fetch', fetcher)
    const api = await import('../src/public-data')
    await expect(api.loadPublicManifest()).rejects.toThrow('503')
    expect((await api.loadPublicManifest()).source.revision).toBe(revision)
    const controller = new AbortController(); controller.abort()
    await expect(api.searchPublicAirports('test', controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('deduplicates boundary features and caps each viewport layer at 500', async () => {
    const items = Array.from({ length: 501 }, (_, i) => feature(String(i)))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(json(manifest)).mockImplementation(() => json({ type: 'FeatureCollection', features: items })))
    const api = await import('../src/public-data')
    const source = await api.loadPublicManifest()
    const result = await api.loadPublicFeatures(source, ['airports'], { zoom: 8, bounds: [-75, 40.1, -65, 40.8] })
    expect(result.features).toHaveLength(500)
    expect(new Set(result.features.map((item) => item.id)).size).toBe(500)
    expect(result.truncated).toBe(true)
  })
})
