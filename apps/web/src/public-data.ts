import type { Geometry } from 'geojson'
import type { ResearchRecord } from './api'
import { LAYER_MIN_ZOOM, MAP_FEATURE_LIMIT, type MapData, type MapViewport } from './map-data'

export type PublicLayer = 'airports' | 'runways' | 'navaids'
export type PublicManifest = {
  schema: 1
  source: { name: string; url: string; license: string; license_url: string; revision: string; updated_at: string }
  /** Composite export revision.  Older OurAirports-only exports use source.revision. */
  dataset_revision?: string
  counts: Record<string, number>
  tiles: Record<PublicLayer, string[]>
  disclaimer: string
  coverage?: Array<{ country: string; airports: number; airports_with_communications: number; runways: number; navaids: number; enriched_airports: number }>
  sources?: Array<{ id: string; name: string; url: string; license: string; license_url: string; updated_at: string; date_kind?: 'retrieved_at' | 'updated_at'; scope: string; airport_count: number }>
}
export type AirportHit = {
  id: string; identifier: string; name: string; icao_id: string; iata_code: string
  municipality: string; country: string; coordinates: [number, number]
  aliases?: string[]; type?: string; scheduled_service?: string
}
export type AirportReference = {
  source_id: string; source_name: string; url: string; record_id: string; name?: string; name_zh?: string
  icao_id: string; country: string; coordinates?: [number, number]; retrieved_at: string
}
export type AirportDetail = { airport: ResearchRecord; communications: ResearchRecord[]; runways: ResearchRecord[]; references?: AirportReference[] }

const cache = new Map<string, unknown>()
let manifest: PublicManifest | undefined
const root = `${import.meta.env.BASE_URL}reference/`
const revisionPattern = /^[a-f0-9]{40}$/

export function publicDataRevision(value: Pick<PublicManifest, 'source' | 'dataset_revision'>): string {
  return value.dataset_revision || value.source.revision
}

async function readJson<T>(path: string, signal?: AbortSignal, cached = true): Promise<T> {
  signal?.throwIfAborted()
  if (cached && cache.has(path)) {
    const value = cache.get(path) as T
    cache.delete(path); cache.set(path, value)
    return value
  }
  const deadline = AbortSignal.timeout(30000)
  const response = await fetch(`${root}${path}`, {
    signal: signal ? AbortSignal.any([signal, deadline]) : deadline,
    cache: cached ? 'default' : 'no-store',
  })
  if (!response.ok) throw new Error(`参考数据读取失败 (${response.status})，请重试或刷新页面。`)
  const result: T = await response.json()
  signal?.throwIfAborted()
  if (cached) {
    cache.set(path, result)
    // Retain a bounded number of viewport/detail files; never preload the globe.
    while (cache.size > 32) cache.delete(cache.keys().next().value!)
  }
  return result
}

export async function loadPublicManifest(signal?: AbortSignal): Promise<PublicManifest> {
  const value = await readJson<PublicManifest>('manifest.json', signal, false)
  const coverageValid = value.coverage === undefined || (Array.isArray(value.coverage) && value.coverage.every((item) =>
    /^[A-Z]{2}$/.test(item.country) && [item.airports, item.airports_with_communications, item.runways, item.navaids, item.enriched_airports]
      .every((count) => Number.isSafeInteger(count) && count >= 0)))
  const sourcesValid = value.sources === undefined || (Array.isArray(value.sources) && value.sources.every((item) =>
    typeof item.id === 'string' && typeof item.name === 'string' && typeof item.url === 'string'
    && (item.date_kind === undefined || item.date_kind === 'retrieved_at' || item.date_kind === 'updated_at')
    && Number.isSafeInteger(item.airport_count) && item.airport_count >= 0))
  if (value.schema !== 1 || !revisionPattern.test(value.source?.revision ?? '')
    || (value.dataset_revision !== undefined && !revisionPattern.test(value.dataset_revision))
    || !Number.isFinite(Date.parse(value.source?.updated_at ?? ''))
    || !coverageValid || !sourcesValid
    || !['airports', 'runways', 'navaids'].every((layer) => Array.isArray(value.tiles?.[layer as PublicLayer])
      && value.tiles[layer as PublicLayer].every((key) => {
        const [x, y] = key.split('-').map(Number)
        return /^\d{1,2}-\d{1,2}$/.test(key) && x >= 0 && x < 72 && y >= 0 && y < 36
      }))) throw new Error('公开数据索引格式不受支持，请刷新页面。')
  if (manifest && publicDataRevision(manifest) !== publicDataRevision(value)) cache.clear()
  manifest = value
  return value
}

async function currentManifest(signal?: AbortSignal) {
  signal?.throwIfAborted()
  return manifest ?? loadPublicManifest(signal)
}

type Bounds = MapViewport['bounds']
function intervals(bounds: Bounds): [number, number][] {
  return bounds[0] <= bounds[2] ? [[bounds[0], bounds[2]]] : [[bounds[0], 180], [-180, bounds[2]]]
}

function segment(a: number[], b: number[], left: number, bottom: number, right: number, top: number) {
  let low = 0, high = 1
  const dx = b[0] - a[0], dy = b[1] - a[1]
  for (const [p, q] of [[-dx, a[0] - left], [dx, right - a[0]], [-dy, a[1] - bottom], [dy, top - a[1]]]) {
    if (p === 0) { if (q < 0) return false; continue }
    const ratio = q / p
    if (p < 0) low = Math.max(low, ratio)
    else high = Math.min(high, ratio)
    if (low > high) return false
  }
  return true
}

export function publicGeometryIntersects(geometry: Geometry | null, bounds: Bounds): boolean {
  if (!geometry) return false
  if (geometry.type === 'MultiLineString') return geometry.coordinates.some((coordinates) =>
    publicGeometryIntersects({ type: 'LineString', coordinates }, bounds))
  const [, south, , north] = bounds
  if (geometry.type === 'Point') {
    const [x, y] = geometry.coordinates
    return y >= south && y <= north && intervals(bounds).some(([left, right]) =>
      [-360, 0, 360].some((shift) => x + shift >= left && x + shift <= right))
  }
  if (geometry.type !== 'LineString') return false
  for (let i = 1; i < geometry.coordinates.length; i++) {
    const a = geometry.coordinates[i - 1], b = [...geometry.coordinates[i]]
    if (b[0] - a[0] > 180) b[0] -= 360
    if (b[0] - a[0] < -180) b[0] += 360
    if (intervals(bounds).some(([left, right]) => [-360, 0, 360].some((shift) =>
      segment(a, b, left + shift, south, right + shift, north)))) return true
  }
  return false
}

function tileIntersects(key: string, bounds: Bounds) {
  const [x, y] = key.split('-').map(Number)
  const west = x * 5 - 180, south = y * 5 - 90
  return south <= bounds[3] && south + 5 >= bounds[1]
    && intervals(bounds).some(([left, right]) => [-360, 0, 360].some((shift) =>
      west + shift <= right && west + shift + 5 >= left))
}

export async function loadPublicFeatures(source: PublicManifest, layers: PublicLayer[], viewport: MapViewport, signal?: AbortSignal): Promise<MapData & { truncated: boolean }> {
  const parts = await Promise.all(layers.filter((layer) => viewport.zoom >= LAYER_MIN_ZOOM[layer]).map(async (layer) => {
    const keys = source.tiles[layer].filter((key) => tileIntersects(key, viewport.bounds))
    const found = new Map<string, MapData['features'][number]>()
    for (let i = 0; i < keys.length; i += 4) {
      signal?.throwIfAborted()
      const tiles = await Promise.all(keys.slice(i, i + 4).map((key) =>
        readJson<MapData>(`${publicDataRevision(source)}/tiles/${layer}/${key}.json`, signal)))
      for (const tile of tiles) for (const feature of tile.features) {
        if (publicGeometryIntersects(feature.geometry, viewport.bounds)) found.set(String(feature.id), feature)
      }
      if (found.size > MAP_FEATURE_LIMIT) break
    }
    return { features: [...found.values()].slice(0, MAP_FEATURE_LIMIT), truncated: found.size > MAP_FEATURE_LIMIT }
  }))
  signal?.throwIfAborted()
  return { type: 'FeatureCollection', features: parts.flatMap((part) => part.features), truncated: parts.some((part) => part.truncated) }
}

function searchable(value: string | undefined) {
  return (value ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLocaleLowerCase()
}

function airportPriority(item: AirportHit) {
  if (item.scheduled_service && item.scheduled_service !== 'no') return 0
  if (item.type === 'large_airport') return 1
  if (item.type === 'medium_airport') return 2
  return 3
}

export async function searchPublicAirports(query: string, signal?: AbortSignal, country?: string): Promise<AirportHit[]> {
  const q = searchable(query.trim().slice(0, 100))
  const source = await currentManifest(signal)
  const selectedCountry = country?.trim().toUpperCase()
  if (selectedCountry && (!/^[A-Z]{2}$/.test(selectedCountry) || !source.coverage?.some((item) => item.country === selectedCountry))) {
    throw new Error('无效的国家或地区代码。')
  }
  if (!q && !selectedCountry) return []
  const revision = publicDataRevision(source)
  const index = await readJson<AirportHit[]>(selectedCountry ? `${revision}/search/${selectedCountry}.json` : `${revision}/search.json`, signal)
  const rank = (item: AirportHit) => q && [item.identifier, item.icao_id, item.iata_code].some((key) => searchable(key) === q) ? 0 : 1
  const results = index.filter((item) => !q || [item.identifier, item.name, item.icao_id, item.iata_code, item.municipality, ...(item.aliases ?? [])]
    .some((key) => searchable(key).includes(q)))
  results.sort((a, b) => rank(a) - rank(b) || airportPriority(a) - airportPriority(b) || a.identifier.localeCompare(b.identifier))
  signal?.throwIfAborted()
  return results.slice(0, 50)
}

export async function loadPublicAirport(id: string, signal?: AbortSignal): Promise<AirportDetail> {
  if (!/^ourairports:airport:\d+$/.test(id)) throw new Error('无效的机场标识。')
  const numeric = Number(id.split(':')[2])
  if (!Number.isSafeInteger(numeric)) throw new Error('无效的机场标识。')
  const source = await currentManifest(signal)
  const bucket = await readJson<Record<string, AirportDetail>>(`${publicDataRevision(source)}/airports/${numeric % 256}.json`, signal)
  const detail = bucket[id]
  if (!detail || detail.airport.id !== id) throw new Error('此数据快照中未找到机场详情。')
  return detail
}
