import type { Mode, Release, ResearchMode, SnapshotStatus, Status } from './api'

export const PRODUCTS = ['nasr', 'cifp', 'dtpp'] as const
export const PRODUCT_NAMES: Record<string, string> = { nasr: 'NASR · 机场', cifp: 'CIFP · 矢量程序', dtpp: 'd-TPP · 航图目录' }
export const MODE_NAMES: Record<Mode, string> = { current: '当前资料', preview: '预览资料', history: '历史资料' }
export type Selection = Partial<Record<string, string>>
export const researchMode = (mode: Mode): ResearchMode => mode === 'current' ? 'active' : mode

export function snapshotChoices(status: Status | null, mode: ResearchMode) {
  return status?.research?.snapshots.filter((item) => {
    if (['revoked', 'blocked'].includes(item.state) || item.date_status === 'unavailable') return false
    if (mode === 'preview') return item.date_status === 'future'
    if (mode === 'history') return item.date_status !== 'future' && item.state !== 'active'
    return item.state === 'active'
  }) ?? []
}

export function selectedSnapshot(status: Status | null, mode: ResearchMode, id: string): SnapshotStatus | undefined {
  if (mode === 'active') return status?.research?.active_snapshots.nasr
  return snapshotChoices(status, mode).find((item) => item.id === id && item.product_id === 'nasr')
}

export function snapshotChartDate(snapshot: SnapshotStatus | undefined, charts: Release | undefined) {
  return Boolean(snapshot && charts && /^\d{4}-\d{2}-\d{2}$/.test(snapshot.official_effective_date)
    && Number.isFinite(Date.parse(charts.valid_from)) && snapshot.official_effective_date === charts.valid_from.slice(0, 10))
}

export function selectedReleases(status: Status | null, mode: Mode, selection: Selection): Record<string, Release> {
  if (!status) return {}
  if (mode === 'current') return status.current_releases
  return Object.fromEntries(PRODUCTS.flatMap((product) => {
    const release = status.releases.find((item) => item.id === selection[product] && item.product_id === product && item.state === mode)
    return release ? [[product, release]] : []
  }))
}

export function releaseKey(releases: Record<string, Release>, mode: Mode) {
  return `${mode}:${Object.entries(releases).map(([product, release]) => `${product}=${release.id}`).sort().join('|')}`
}

export function expired(releases: Record<string, Release>, now: number) {
  return Object.values(releases).some((release) => now < Date.parse(release.valid_from) || now >= Date.parse(release.valid_to))
}

export function sameChartCycle(procedureRelease: Release | undefined, chartRelease: Release | undefined) {
  if (!procedureRelease || !chartRelease || procedureRelease.airac !== chartRelease.airac) return false
  const procedureStart = Date.parse(procedureRelease.valid_from)
  const procedureEnd = Date.parse(procedureRelease.valid_to)
  const chartStart = Date.parse(chartRelease.valid_from)
  const chartEnd = Date.parse(chartRelease.valid_to)
  return [procedureStart, procedureEnd, chartStart, chartEnd].every(Number.isFinite)
    && Math.max(procedureStart, chartStart) < Math.min(procedureEnd, chartEnd)
}

export function officialPdfUrl(value: unknown): string | null {
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && (url.hostname === 'faa.gov' || url.hostname.endsWith('.faa.gov')) && /\.pdf$/i.test(url.pathname)
      ? url.href : null
  } catch { return null }
}

export function utc(value: string | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : `${date.toISOString().slice(0, 16).replace('T', ' ')} UTC`
}
