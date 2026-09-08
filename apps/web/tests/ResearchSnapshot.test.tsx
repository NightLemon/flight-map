import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useEffect } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { MapData, MapViewport } from '../src/map-data'
import { airport, chart, release, researchSnapshot, status } from './fixtures'
vi.mock('../src/PdfViewer', () => ({ PdfViewer: () => <canvas /> }))

vi.mock('../src/AviationMap', () => ({ AviationMap: ({ features, focus, onFeature, onViewport }: { features: MapData; focus: [number, number] | null; onFeature: (p: object) => void; onViewport: (value: MapViewport | null) => void }) => {
  useEffect(() => onViewport({ bounds: [-125, 25, -65, 50], zoom: 3.25 }), [onViewport])
  useEffect(() => { if (focus) onViewport({ bounds: [-101, 34, -99, 36], zoom: 10 }) }, [focus, onViewport])
  return <div>
  <output data-testid="features">{JSON.stringify(features.features)}</output><output data-testid="focus">{JSON.stringify(focus)}</output>
  <button onClick={() => onFeature(features.features[0]?.properties ?? {})}>测试机场点</button>
  <button onClick={() => onViewport({ bounds: [-101, 34, -99, 36], zoom: 10 })}>测试放大地图</button>
  <button onClick={() => onViewport({ bounds: [-125, 25, -65, 50], zoom: 3.25 })}>测试缩小地图</button>
  <button onClick={() => onViewport(null)}>测试开始移动</button>
</div> } }))
import App from '../src/App'

function renderWithManagement() {
  const view = render(<App />)
  fireEvent.click(screen.getByText('数据管理'))
  return view
}

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
    if (url.pathname.includes('/research/records/')) return response({ ...envelope, record: researchAirport })
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
  const enableAllLayers = () => {
    data.research!.active_snapshots.nasr = researchSnapshot({ schema_version: 'research-2', capabilities: ['airports', 'runways', 'navaids', 'waypoints', 'airways', 'communications'] })
  }
  const comm = { ...airport, id: 'synthetic-comm', kind: 'communication', geometry: null, airport_id: airport.id,
    properties: { service: 'GND/P', frequency: '121.900', unit: 'MHz', remarks: 'SYNTHETIC SECTOR ONLY' } }

  it('routes each enabled layer through the capable snapshot, bounded and only after zooming', async () => {
    enableAllLayers()
    renderWithManagement()
    await screen.findByText('API 已连接')
    for (const label of ['跑道', '导航台', '航点', '航路']) fireEvent.click(screen.getByRole('checkbox', { name: new RegExp(label) }))
    await new Promise((resolve) => setTimeout(resolve, 300))
    expect(requests.filter((url) => url.pathname.endsWith('/features'))).toHaveLength(0)
    fireEvent.click(screen.getByRole('button', { name: '测试放大地图' }))
    await waitFor(() => expect(requests.filter((url) => url.pathname.endsWith('/features'))).toHaveLength(5))
    const calls = requests.filter((url) => url.pathname.endsWith('/features'))
    expect(calls.map((url) => url.searchParams.get('layer')).sort()).toEqual(['airports', 'airways', 'navaids', 'runways', 'waypoints'])
    for (const url of calls) {
      expect(url.pathname).toBe('/api/v1/research/features')
      expect(url.searchParams.get('snapshot_id')).toBe(snapshot.id)
      expect(url.searchParams.get('bbox')).toBe('-101,34,-99,36')
      expect(url.searchParams.get('limit')).toBe('500')
    }
  })
  it('automatically loads frequencies and full original fields on a map airport click', async () => {
    enableAllLayers()
    override = (url) => url.pathname.endsWith('/communications') ? response({ snapshot_id: snapshot.id, mode: 'active', items: [comm] }) : undefined
    renderWithManagement()
    fireEvent.click(screen.getByRole('button', { name: '测试放大地图' }))
    await waitFor(() => expect(screen.getByTestId('features')).toHaveTextContent(airport.id))
    fireEvent.click(screen.getByRole('button', { name: '测试机场点' }))
    await screen.findByText('121.900 MHz')
    expect(screen.getByText('SYNTHETIC SECTOR ONLY')).toBeVisible()
    const call = requests.find((url) => url.pathname.endsWith('/communications'))!
    expect(decodeURIComponent(call.pathname)).toBe(`/api/v1/research/airports/${airport.id}/communications`)
    expect(call.searchParams.get('snapshot_id')).toBe(snapshot.id)
    expect(requests.some((url) => url.pathname.includes('/research/records/'))).toBe(true)
  })
  it.each(['关闭', '历史资料'])('discards late airport frequencies after %s', async (action) => {
    enableAllLayers()
    let finish: ((value: Response) => void) | undefined
    override = (url) => url.pathname.endsWith('/communications') ? new Promise<Response>((resolve) => { finish = resolve }) : undefined
    renderWithManagement(); await searchAirport()
    await waitFor(() => expect(finish).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: action, exact: true }))
    await act(async () => finish!(response({ snapshot_id: snapshot.id, mode: 'active', items: [comm] })))
    expect(screen.queryByText('121.900 MHz')).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: '机场通信频率' })).not.toBeInTheDocument()
  })
  it('does not replace a second airport frequencies with the first airport late response', async () => {
    enableAllLayers()
    let finish: ((value: Response) => void) | undefined
    const second = { ...researchAirport, id: 'second-airport', name: 'SECOND SYNTHETIC AIRPORT', identifier: 'NEXT' }
    override = (url) => {
      if (url.pathname.endsWith('/research/search') && url.searchParams.get('q') === 'NEXT') return response({ snapshot_id: snapshot.id, mode: 'active', items: [second] })
      if (url.pathname.endsWith('/communications')) return url.pathname.includes('second-airport')
        ? response({ snapshot_id: snapshot.id, mode: 'active', items: [{ ...comm, id: 'second-comm', airport_id: second.id, properties: { ...comm.properties, frequency: '122.800' } }] })
        : new Promise<Response>((resolve) => { finish = resolve })
    }
    renderWithManagement(); await searchAirport()
    await waitFor(() => expect(finish).toBeDefined())
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'NEXT' } })
    fireEvent.click(screen.getByRole('button', { name: '搜索', exact: true }))
    fireEvent.click(within(await screen.findByLabelText('搜索结果')).getByRole('button', { name: /SECOND SYNTHETIC AIRPORT/ }))
    await screen.findByText('122.800 MHz')
    await act(async () => finish!(response({ snapshot_id: snapshot.id, mode: 'active', items: [comm] })))
    expect(screen.queryByText('121.900 MHz')).not.toBeInTheDocument()
    expect(screen.getByText('122.800 MHz')).toBeVisible()
  })
  it('keeps the overview empty and only queries bounded local features after zooming', async () => {
    render(<App />)
    expect(screen.getByText('数据管理').closest('details')).not.toHaveAttribute('open')
    expect(screen.getByRole('button', { name: '严格有效期', hidden: true })).not.toBeVisible()
    expect(screen.getByRole('checkbox', { name: /机场/ })).toBeVisible()
    await screen.findByText('放大地图查看附近机场，或搜索机场直接定位')
    await new Promise((resolve) => setTimeout(resolve, 300))
    expect(requests.filter((url) => url.pathname.endsWith('/features'))).toEqual([])
    fireEvent.click(screen.getByRole('button', { name: '测试放大地图' }))
    await waitFor(() => expect(screen.getByTestId('features')).toHaveTextContent(airport.id))
    const featureRequests = () => requests.filter((url) => url.pathname.endsWith('/features'))
    expect(featureRequests()).toHaveLength(1)
    expect(featureRequests()[0].searchParams.get('bbox')).toBe('-101,34,-99,36')
    expect(featureRequests()[0].searchParams.get('limit')).toBe('500')
    fireEvent.click(screen.getByRole('button', { name: '测试放大地图' }))
    await new Promise((resolve) => setTimeout(resolve, 300))
    expect(featureRequests()).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: '测试缩小地图' }))
    expect(screen.getByTestId('features')).toHaveTextContent('[]')
    await new Promise((resolve) => setTimeout(resolve, 300))
    expect(featureRequests()).toHaveLength(1)
  })
  it.each(['测试缩小地图', '测试开始移动'])('ignores an in-flight local response after %s', async (control) => {
    let finish: ((value: Response) => void) | undefined
    override = (url) => url.pathname.endsWith('/research/features') ? new Promise<Response>((resolve) => { finish = resolve }) : undefined
    renderWithManagement()
    await screen.findByText('API 已连接')
    fireEvent.click(screen.getByRole('button', { name: '测试放大地图' }))
    await waitFor(() => expect(finish).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: control }))
    await act(async () => finish!(response({ snapshot_id: snapshot.id, mode: 'active', type: 'FeatureCollection', features: [{ type: 'Feature', geometry: airport.geometry, properties: { id: airport.id } }] })))
    expect(screen.getByTestId('features')).toHaveTextContent('[]')
  })
  it('defaults to date research and pins all airport and chart requests from a single status response', async () => {
    renderWithManagement()
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
    renderWithManagement()
    fireEvent.click(screen.getByRole('button', { name: '测试放大地图' }))
    await waitFor(() => expect(screen.getByTestId('features')).toHaveTextContent(airport.id))
    fireEvent.click(screen.getByRole('button', { name: '测试机场点' }))
    await screen.findByText('SYNTHETIC TEST AIRPORT')
    expect(screen.getByText(/官方日期 2026-09-03 · NAD83/)).toBeVisible()
  })
  it('does not request charts for a mismatched official date', async () => {
    data.current_releases.dtpp = release('dtpp', { valid_from: '2026-09-04T09:01:00Z' })
    renderWithManagement(); await searchAirport()
    expect(screen.getByText(/没有与机场官方日期相同的航图版本/)).toBeVisible()
    expect(requests.some((u) => u.pathname.endsWith('/charts'))).toBe(false)
  })
  it('retains an update-due snapshot with a clear reminder', async () => {
    data.research!.active_snapshots.nasr = researchSnapshot({ date_status: 'update-due' })
    renderWithManagement(); await searchAirport()
    expect(screen.getByText(/当前仍在研究旧快照/)).toBeVisible()
  })
  it('shows research availability as the primary coverage state when strict validity remains blocked', async () => {
    override = (url) => url.pathname.endsWith('/coverage') ? response([{ product_id: 'nasr', name: 'NASR', status: 'blocked', categories: ['airports'], note: 'validity-evidence-missing' }]) : undefined
    renderWithManagement()
    await screen.findByText('研究可用')
    expect(screen.getByText('活动研究快照 · 官方日期 2026-09-03')).toBeVisible()
    expect(screen.queryByText('已阻断')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('严格 Current 状态'))
    expect(screen.getByText('严格 Current 未启用；日期级研究快照可用。')).toBeVisible()
  })
  it('requires an explicit history snapshot and immediately clears old map and selection', async () => {
    const old = researchSnapshot({ id: 'old-snapshot', state: 'history' })
    data.research!.snapshots.push(old)
    renderWithManagement(); await searchAirport()
    fireEvent.click(screen.getByRole('button', { name: '历史资料', exact: true }))
    expect(screen.getByTestId('features')).toHaveTextContent('[]')
    expect(screen.queryByText('SYNTHETIC TEST AIRPORT')).not.toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '机场研究快照版本' })).toHaveValue('')
    fireEvent.change(screen.getByRole('combobox', { name: '机场研究快照版本' }), { target: { value: old.id } })
    await waitFor(() => expect(requests.some((u) => u.pathname.endsWith('/research/features') && u.searchParams.get('snapshot_id') === old.id && u.searchParams.get('mode') === 'history')).toBe(true))
  })
  it.each([403, 409, 410])('clears the entire page after research gate error %i', async (code) => {
    renderWithManagement(); await searchAirport()
    override = (url) => url.pathname.endsWith('/research/search') ? response({ detail: 'Snapshot unavailable' }, code) : undefined
    fireEvent.click(screen.getByRole('button', { name: '搜索', exact: true }))
    await screen.findByText(`Snapshot unavailable (${code})`)
    expect(screen.getByText('API 已连接')).toBeVisible()
    expect(screen.queryByText('API 未连接')).not.toBeInTheDocument()
    expect(screen.getByTestId('features')).toHaveTextContent('[]')
    expect(screen.getByTestId('focus')).toHaveTextContent('null')
    expect(screen.queryByText('SYNTHETIC TEST AIRPORT')).not.toBeInTheDocument()
  })
  it('reloads the complete selection after a version conflict without restoring the old airport', async () => {
    renderWithManagement(); await searchAirport()
    const replacement = researchSnapshot({ id: 'replacement-snapshot' })
    data.research!.active_snapshots.nasr = replacement
    data.research!.snapshots = [replacement]
    override = (url) => url.pathname.endsWith('/research/search') ? response({ detail: 'Snapshot switched' }, 409) : undefined
    fireEvent.click(screen.getByRole('button', { name: '搜索', exact: true }))
    await screen.findByText('Snapshot switched (409)')
    expect(screen.getByText('API 已连接')).toBeVisible()
    expect(screen.getByTestId('features')).toHaveTextContent('[]')
    fireEvent.click(screen.getByRole('button', { name: '重试', exact: true }))
    await waitFor(() => expect(requests.some((url) => url.pathname.endsWith('/research/features') && url.searchParams.get('snapshot_id') === replacement.id)).toBe(true))
    expect(screen.queryByText('Snapshot switched (409)')).not.toBeInTheDocument()
    expect(screen.queryByText('SYNTHETIC TEST AIRPORT')).not.toBeInTheDocument()
    expect(screen.getByTestId('focus')).toHaveTextContent('null')
  })
  it('rejects a delayed search after mode switching', async () => {
    let finish: (value: Response) => void = () => { throw new Error('not requested') }
    override = (url) => url.pathname.endsWith('/research/search') ? new Promise<Response>((resolve) => { finish = resolve }) : undefined
    renderWithManagement(); await screen.findByText('API 已连接')
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'ZZZ' } })
    fireEvent.click(screen.getByRole('button', { name: '搜索', exact: true }))
    fireEvent.click(screen.getByRole('button', { name: '预览资料', exact: true }))
    finish(response({ snapshot_id: snapshot.id, mode: 'active', items: [researchAirport] }))
    await waitFor(() => expect(screen.getByText('请选择资料版本')).toBeVisible())
    expect(screen.queryByLabelText('搜索结果')).not.toBeInTheDocument()
  })
})
