import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { MapData } from '../src/map-data'
import { airport, chart, release, researchSnapshot, status } from './fixtures'

vi.mock('../src/AviationMap', () => ({ AviationMap: ({ features, focus, onFeature }: { features: MapData; focus: unknown; onFeature: (p: object) => void }) => <div>
  <output data-testid="features">{JSON.stringify(features.features)}</output><output data-testid="focus">{JSON.stringify(focus)}</output>
  <button onClick={() => onFeature(features.features[0]?.properties ?? {})}>测试机场点</button>
</div> }))
import App from '../src/App'

const snapshot = researchSnapshot()
const researchAirport = { ...airport, properties: { ...airport.properties, datum: 'NAD83' } }
const initial = () => status({ current_releases: { dtpp: release('dtpp') }, research: { current_time: '2026-09-08T00:00:00Z', active_snapshots: { nasr: snapshot }, snapshots: [snapshot], attempts: [], storage_errors: [], disclaimer: 'synthetic only' } })
let data = initial()
let requests: URL[] = []
let override: ((url: URL) => Response | Promise<Response> | undefined) | undefined
const response = (payload: unknown, code = 200) => new Response(JSON.stringify(payload), { status: code, headers: { 'Content-Type': 'application/json' } })

beforeEach(() => {
  data = initial(); requests = []; override = undefined
  vi.stubGlobal('fetch', vi.fn(async (path: string) => {
    const url = new URL(path, 'http://test.local'); requests.push(url)
    const custom = override?.(url)
    if (custom) return custom
    const envelope = { snapshot_id: url.searchParams.get('snapshot_id'), release_id: url.searchParams.get('release_id'), mode: url.searchParams.get('mode') }
    if (url.pathname.endsWith('/status')) return response(data)
    if (url.pathname.endsWith('/coverage') || url.pathname.endsWith('/sources')) return response([])
    if (url.pathname.endsWith('/features')) return response({ ...envelope, type: 'FeatureCollection', features: [{ type: 'Feature', geometry: airport.geometry,
      properties: { ...researchAirport.properties, ...envelope, ...researchAirport, properties: undefined } }] })
    if (url.pathname.endsWith('/search')) return response({ ...envelope, items: envelope.snapshot_id ? [researchAirport] : [] })
    if (url.pathname.endsWith('/charts')) return response({ ...envelope, items: [chart] })
    throw new Error(`Unexpected ${url}`)
  }))
})
afterEach(() => vi.unstubAllGlobals())

async function searchAirport() {
  await screen.findByText('API 已连接')
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'KZZZ' } })
  fireEvent.click(screen.getByRole('button', { name: '搜索', exact: true }))
  fireEvent.click(within(await screen.findByLabelText('搜索结果')).getByRole('button', { name: /SYNTHETIC TEST AIRPORT/ }))
}

describe('airport research snapshot UI', () => {
  it('defaults to date research and pins all airport and chart requests from a single status response', async () => {
    render(<App />)
    await searchAirport()
    await screen.findByRole('button', { name: /SYNTHETIC DEPARTURE CHART/ })
    expect(screen.getByRole('button', { name: '日期级研究' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('focus')).toHaveTextContent('[-100,35]')
    expect(screen.getByText(/官方日期 2026-09-03 · NAD83/)).toBeVisible()
    fireEvent.click(screen.getByText('来源、原始字段与有效期'))
    expect(screen.getByText('synthetic-row:1 · 行 1')).toBeVisible()
    expect(requests.find((u) => u.pathname.endsWith('/research/search'))?.searchParams.get('snapshot_id')).toBe(snapshot.id)
    expect(requests.find((u) => u.pathname.endsWith('/charts'))?.searchParams.get('release_id')).toBe(release('dtpp').id)
    expect(requests.some((u) => u.pathname === '/api/v1/research/snapshots')).toBe(false)
  })
  it('opens a real API airport point with its date and source', async () => {
    render(<App />)
    await waitFor(() => expect(screen.getByTestId('features')).toHaveTextContent(airport.id))
    fireEvent.click(screen.getByRole('button', { name: '测试机场点' }))
    await screen.findByText('SYNTHETIC TEST AIRPORT')
    expect(screen.getByText(/官方日期 2026-09-03 · NAD83/)).toBeVisible()
  })
  it('does not request charts for a mismatched official date', async () => {
    data.current_releases.dtpp = release('dtpp', { valid_from: '2026-09-04T09:01:00Z' })
    render(<App />); await searchAirport()
    expect(screen.getByText(/没有与机场官方日期相同的航图版本/)).toBeVisible()
    expect(requests.some((u) => u.pathname.endsWith('/charts'))).toBe(false)
  })
  it('retains an update-due snapshot with a clear reminder', async () => {
    data.research!.active_snapshots.nasr = researchSnapshot({ date_status: 'update-due' })
    render(<App />); await searchAirport()
    expect(screen.getByText(/当前仍在研究旧快照/)).toBeVisible()
  })
  it('requires an explicit history snapshot and immediately clears old map and selection', async () => {
    const old = researchSnapshot({ id: 'old-snapshot', state: 'history' })
    data.research!.snapshots.push(old)
    render(<App />); await searchAirport()
    fireEvent.click(screen.getByRole('button', { name: '历史资料', exact: true }))
    expect(screen.getByTestId('features')).toHaveTextContent('[]')
    expect(screen.queryByText('SYNTHETIC TEST AIRPORT')).not.toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '机场研究快照版本' })).toHaveValue('')
    fireEvent.change(screen.getByRole('combobox', { name: '机场研究快照版本' }), { target: { value: old.id } })
    await waitFor(() => expect(requests.some((u) => u.pathname.endsWith('/research/features') && u.searchParams.get('snapshot_id') === old.id && u.searchParams.get('mode') === 'history')).toBe(true))
  })
  it.each([403, 409, 410])('clears the entire page after research gate error %i', async (code) => {
    render(<App />); await searchAirport()
    override = (url) => url.pathname.endsWith('/research/search') ? response({ detail: 'Snapshot unavailable' }, code) : undefined
    fireEvent.click(screen.getByRole('button', { name: '搜索', exact: true }))
    await screen.findByText(`Snapshot unavailable (${code})`)
    expect(screen.getByTestId('features')).toHaveTextContent('[]')
    expect(screen.getByTestId('focus')).toHaveTextContent('null')
    expect(screen.queryByText('SYNTHETIC TEST AIRPORT')).not.toBeInTheDocument()
  })
  it('rejects a delayed search after mode switching', async () => {
    let finish: (value: Response) => void = () => { throw new Error('not requested') }
    override = (url) => url.pathname.endsWith('/research/search') ? new Promise<Response>((resolve) => { finish = resolve }) : undefined
    render(<App />); await screen.findByText('API 已连接')
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'ZZZ' } })
    fireEvent.click(screen.getByRole('button', { name: '搜索', exact: true }))
    fireEvent.click(screen.getByRole('button', { name: '预览资料', exact: true }))
    finish(response({ snapshot_id: snapshot.id, mode: 'active', items: [researchAirport] }))
    await waitFor(() => expect(screen.getByText('请选择资料版本')).toBeVisible())
    expect(screen.queryByLabelText('搜索结果')).not.toBeInTheDocument()
  })
})
