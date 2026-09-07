import type { Geometry } from 'geojson'
import type { MapData } from './map-data'

export type Mode = 'current' | 'preview' | 'history'
export type Product = 'nasr' | 'cifp' | 'dtpp'
export type Layer = 'airports' | 'runways' | 'navaids' | 'waypoints' | 'airways'
export type Issue = { code: string; severity: string; message: string }
export type Release = {
  id: string; source_id: string; product_id: string; airac: string
  valid_from: string; valid_to: string; parser_version: string
  quality_status: string; state: string; capabilities: string[]
  issues: Issue[]; input_sha256: string[]; validity_evidence: string[]
}
export type Status = {
  current_time: string
  airac: { identifier: string; valid_from: string; valid_to: string }
  verified_release_available: boolean; publication_state: string; disclaimer: string
  current_releases: Record<string, Release>; releases: Release[]
}
export type Coverage = {
  product_id: string; name: string; status: string; note?: string
  release_id?: string; valid_from?: string; valid_to?: string
  counts?: Record<string, number>; categories: string[]
  last_successful_release?: { id: string; airac: string; valid_from: string; valid_to: string; state: string } | null
  notices_url?: string | null
}
export type Source = {
  id: string; name: string; products: {
    id: string; name: string; landing_page: string; notes?: string; redistribution: string
    local_access?: { acquisition: string; processing: string; evidence: string[] }
  }[]
}
export type Provenance = { asset_sha256: string; member: string | null; line: number | null; locator: string }
export type ResearchRecord = {
  id: string; kind: string; name: string; identifier: string
  airport_ident: string | null; airport_id: string | null; parent_id: string | null
  branch_id: string | null; sequence: number | null; geometry: Geometry | null
  properties: Record<string, unknown>; provenance: Provenance
}
export type SearchResult = ResearchRecord & { release_id: string; product_id: string }
export type Envelope = { release_id: string; mode: Mode; items: ResearchRecord[] }
export type Procedure = {
  release_id: string; mode: Mode; record: ResearchRecord; legs: ResearchRecord[]; branches: string[]
}
export type GeometryResponse = MapData & {
  release_id: string; mode: Mode; gaps: { leg_id: string; reason: string }[]; notice?: string
}
export type FeaturesResponse = MapData & { release_id: string; mode: Mode; truncated?: boolean }
export type Report = {
  release: Release
  report: { input_count: number; success_count: number; unsupported_count: number; error_count: number; issues: Issue[]; capabilities: string[] }
  diff: unknown
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const base = import.meta.env.VITE_API_BASE_URL ?? ''
  const deadline = AbortSignal.timeout(20000)
  const response = await fetch(`${base}/api/v1${path}`, { signal: signal ? AbortSignal.any([signal, deadline]) : deadline, cache: 'no-store' })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { detail?: unknown }
    const detail = typeof payload.detail === 'string' ? payload.detail : '请求失败'
    throw new ApiError(response.status, `${detail} (${response.status})`)
  }
  return response.json() as Promise<T>
}

export function versionQuery(release: Release, mode: Mode, extra: Record<string, string> = {}) {
  return new URLSearchParams({ release_id: release.id, mode, ...extra }).toString()
}

export function assertVersion<T extends { release_id: string; mode: Mode }>(payload: T, release: Release, mode: Mode): T {
  if (payload.release_id !== release.id || payload.mode !== mode) throw new ApiError(409, '返回资料版本与本页固定版本不一致')
  return payload
}

export function isAbort(error: unknown) { return error instanceof DOMException && error.name === 'AbortError' }
export function errorMessage(error: unknown) { return error instanceof Error ? error.message : '无法读取资料' }
