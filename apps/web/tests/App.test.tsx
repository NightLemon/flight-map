import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useEffect } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { MapData, MapViewport } from '../src/map-data'
import { airport, chart, geometry, legs, procedure, release, status } from './fixtures'
vi.mock('../src/PdfViewer', () => ({ PdfViewer: ({ title }: { title: string }) => <canvas title={`官方航图 ${title}`} /> }))

vi.mock('../src/AviationMap', () => ({
  EMPTY_MAP: { type: 'FeatureCollection', features: [] },
  AviationMap: ({ features, procedure, focus, onViewport }: { features: MapData; procedure: MapData; focus: [number, number] | null; onViewport: (value: MapViewport | null) => void }) => {
    useEffect(() => onViewport({ bounds: [-125, 25, -65, 50], zoom: 3.25 }), [onViewport])
    useEffect(() => { if (focus) onViewport({ bounds: [-101, 34, -99, 36], zoom: 10 }) }, [focus, onViewport])
    return <div>
    <output data-testid="map-features">{JSON.stringify(features.features)}</output>
    <output data-testid="map-procedure">{JSON.stringify(procedure.features)}</output>
    <button onClick={() => onViewport({ bounds: [-101, 34, -99, 36], zoom: 10 })}>测试放大地图</button>
  </div> },
}))
import App from '../src/App'

function renderStrict() {
  const view = render(<App />)
  fireEvent.click(screen.getByText('数据管理'))
  fireEvent.click(screen.getByRole('button', { name: '严格有效期' }))
  return view
}

type RouteOverride = (url: URL) => Promise<Response> | Response | undefined
let override: RouteOverride | undefined
let snapshot = status()
let requested: URL[]

function response(payload: unknown, code = 200) { return new Response(JSON.stringify(payload), { status: code, headers: { 'Content-Type': 'application/json' } }) }

beforeEach(() => {
  snapshot = status(); override = undefined; requested = []
  vi.stubGlobal('fetch', vi.fn(async (path: string) => {
    const url = new URL(path, 'http://test.local')
    requested.push(url)
    const custom = override?.(url)
    if (custom) return custom
    const releaseId = url.searchParams.get('release_id')
    const mode = url.searchParams.get('mode')
    const envelope = { release_id: releaseId, mode }
    if (url.pathname.endsWith('/status')) return response(snapshot)
    if (url.pathname.endsWith('/sources')) return response([])
    if (url.pathname.endsWith('/coverage')) return response([{ product_id: 'cifp', name: 'CIFP', status: 'current', categories: [] }])
    if (url.pathname.endsWith('/features')) return response({ ...envelope, type: 'FeatureCollection', features: [{ type: 'Feature', geometry: airport.geometry, properties: { ...airport.properties, id: airport.id, name: airport.name, kind: airport.kind, identifier: airport.identifier, release_id: releaseId, provenance: airport.provenance } }] })
    if (url.pathname.endsWith('/search')) return response({ ...envelope, items: releaseId === release('nasr').id ? [airport] : [] })
    if (url.pathname.endsWith('/charts')) return response({ ...envelope, items: [chart] })
    if (url.pathname.endsWith('/airports/KZZZ/procedures')) return response({ ...envelope, items: [procedure] })
    if (url.pathname.endsWith('/geometry')) return response(geometry(url.searchParams.get('branch_id') ?? ''))
    if (url.pathname.includes('/procedures/')) return response({ ...envelope, record: procedure, legs, branches: ['BRANCH A', 'BRANCH B'] })
    throw new Error(`Unexpected request ${url}`)
  }))
})
afterEach(() => { vi.unstubAllGlobals() })

async function chooseAirport() {
  await screen.findByText('API 已连接')
  fireEvent.change(screen.getByRole('textbox', { name: /搜索机场/ }), { target: { value: 'ZZZ' } })
  fireEvent.click(screen.getByRole('button', { name: '搜索', exact: true }))
  const results = await screen.findByLabelText('搜索结果')
  fireEvent.click(within(results).getByRole('button', { name: /SYNTHETIC TEST AIRPORT/ }))
  await screen.findByRole('button', { name: /SYNTHETIC SID/ })
}

describe('research workspace', () => {
  it('does not request strict airport features at overview zoom', async () => {
    renderStrict()
    await screen.findByText('放大地图查看附近机场，或搜索机场直接定位')
    await new Promise((resolve) => setTimeout(resolve, 300))
    expect(requested.filter((url) => url.pathname.endsWith('/features'))).toEqual([])
    expect(screen.getByTestId('map-features')).toHaveTextContent('[]')
  })
  it('retains the last validated cycle and official notices when acquisition fails without making it current', async () => {
    snapshot = status({ current_releases: {}, releases: [], publication_state: 'empty', verified_release_available: false })
    override = (url) => url.pathname.endsWith('/coverage') ? response([
      { product_id: 'nasr', name: 'NASR', status: 'failed', categories: ['airports'], note: 'Latest acquisition failed',
        last_successful_release: { id: 'successful-nasr-2608', airac: '2608', valid_from: '2026-08-06T09:01:00Z', valid_to: '2026-09-03T09:01:00Z', state: 'history' },
        notices_url: 'https://www.faa.gov/air_traffic/flight_info/aeronav/safety_alerts/' },
      { product_id: 'cifp', name: 'CIFP', status: 'not-imported', categories: [], last_successful_release: null, notices_url: null },
    ]) : undefined
    renderStrict()
    await screen.findByText('获取失败')
    expect(screen.getByText('最近验证通过 2608 · successful-nasr-2608')).toBeVisible()
    expect(screen.getByText('有效期 2026-08-06 09:01 UTC — 2026-09-03 09:01 UTC')).toBeVisible()
    const notices = screen.getByRole('link', { name: /官方更正公告/ })
    expect(notices).toHaveAttribute('href', 'https://www.faa.gov/air_traffic/flight_info/aeronav/safety_alerts/')
    expect(notices).toHaveAttribute('target', '_blank')
    expect(notices).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.getByText('尚无已验证的当前资料')).toBeVisible()
    expect(screen.getByRole('checkbox', { name: /机场/ })).toBeDisabled()
    expect(screen.getByTestId('map-features')).toHaveTextContent('[]')
  })

  it('uses the API empty state and never invents sample results', async () => {
    snapshot = status({ current_releases: {}, releases: [], publication_state: 'empty', verified_release_available: false })
    renderStrict()
    await screen.findByText('尚无已验证的当前资料')
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'ZZZ' } })
    fireEvent.click(screen.getByRole('button', { name: '搜索', exact: true }))
    expect(screen.getByText('所选版本没有可搜索的资料。')).toBeVisible()
    expect(screen.queryByText('SYNTHETIC TEST AIRPORT')).not.toBeInTheDocument()
    expect(screen.getByTestId('map-features')).toHaveTextContent('[]')
  })

  it('searches pinned releases and shows one branch with explicit geometry gaps', async () => {
    renderStrict()
    await chooseAirport()
    fireEvent.click(screen.getByRole('button', { name: /SYNTHETIC SID/ }))
    const selector = await screen.findByRole('combobox', { name: '程序分支' })
    expect(screen.getByTestId('map-procedure')).toHaveTextContent('[]')
    fireEvent.change(selector, { target: { value: 'BRANCH A' } })
    await screen.findByText(/几何缺口 · Unsupported RF leg/)
    expect(screen.getByText('START')).toBeVisible()
    expect(screen.queryByText('END')).not.toBeInTheDocument()
    expect(screen.getByTestId('map-procedure')).toHaveTextContent('leg1')
    fireEvent.change(selector, { target: { value: 'BRANCH B' } })
    expect(screen.getByTestId('map-procedure')).toHaveTextContent('[]')
    expect(screen.queryByText('START')).not.toBeInTheDocument()
    expect(screen.getByText('END')).toBeVisible()
    const dataRequests = requested.filter((url) => !['/api/v1/status', '/api/v1/coverage', '/api/v1/sources'].includes(url.pathname))
    expect(dataRequests.length).toBeGreaterThan(4)
    expect(dataRequests.every((url) => url.searchParams.get('release_id') && url.searchParams.get('mode') === 'current')).toBe(true)
  })

  it('clears PDF, selected records and map before a wake revalidation that fails', async () => {
    renderStrict()
    await chooseAirport()
    fireEvent.click(await screen.findByRole('button', { name: /SYNTHETIC DEPARTURE CHART/ }))
    expect(screen.getByTitle('官方航图 SYNTHETIC DEPARTURE CHART')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('map-features')).toHaveTextContent('test:airport:ZZZ'))
    override = (url) => url.pathname.endsWith('/status') ? Promise.reject(new Error('Network disconnected')) : undefined
    fireEvent(window, new Event('focus'))
    expect(screen.queryByTitle(/官方航图/)).not.toBeInTheDocument()
    expect(screen.getByTestId('map-features')).toHaveTextContent('[]')
    await screen.findByText('Network disconnected')
    expect(screen.getByText('API 未连接')).toBeVisible()
    expect(screen.queryByText('SYNTHETIC TEST AIRPORT')).not.toBeInTheDocument()
  })

  it.each([409, 410, 403])('invalidates the complete snapshot after data error %i', async (code) => {
    renderStrict()
    await chooseAirport()
    override = (url) => url.pathname.includes('/procedures/') ? response({ detail: 'Publication unavailable' }, code) : undefined
    fireEvent.click(screen.getByRole('button', { name: /SYNTHETIC SID/ }))
    await screen.findByText(`Publication unavailable (${code})`)
    expect(screen.getByText('API 已连接')).toBeVisible()
    expect(screen.queryByText('API 未连接')).not.toBeInTheDocument()
    expect(screen.queryByText('SYNTHETIC TEST AIRPORT')).not.toBeInTheDocument()
    expect(screen.getByTestId('map-features')).toHaveTextContent('[]')
  })

  it('requires explicit history selection and unloads the old current map', async () => {
    snapshot.releases.push(release('nasr', { id: 'nasr-history', state: 'history', airac: '2608' }))
    renderStrict()
    await chooseAirport()
    fireEvent.click(screen.getByRole('button', { name: '历史资料', exact: true }))
    expect(screen.getByRole('combobox', { name: 'NASR · 机场版本' })).toHaveValue('')
    expect(screen.getByTestId('map-features')).toHaveTextContent('[]')
    expect(screen.queryByText('SYNTHETIC TEST AIRPORT')).not.toBeInTheDocument()
    expect(screen.getByText('请选择资料版本')).toBeVisible()
  })

  it('rejects an old response that arrives after switching modes', async () => {
    let finish: (value: Response) => void = () => { throw new Error('request not started') }
    override = (url) => url.pathname.endsWith('/search') && url.searchParams.get('release_id') === release('nasr').id
      ? new Promise<Response>((resolve) => { finish = resolve }) : undefined
    renderStrict()
    await screen.findByText('API 已连接')
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'ZZZ' } })
    fireEvent.click(screen.getByRole('button', { name: '搜索', exact: true }))
    fireEvent.click(screen.getByRole('button', { name: '预览资料', exact: true }))
    finish(response({ release_id: release('nasr').id, mode: 'current', items: [airport] }))
    await waitFor(() => expect(screen.getByText('请选择资料版本')).toBeVisible())
    expect(screen.queryByLabelText('搜索结果')).not.toBeInTheDocument()
  })

  it('supports airport catalog research with only a d-TPP release and no invented coordinates', async () => {
    snapshot = status({ current_releases: { dtpp: release('dtpp') }, releases: [release('dtpp')] })
    const catalogAirport = { ...airport, geometry: null, properties: { catalog_only: true } }
    override = (url) => url.pathname.endsWith('/search') ? response({ release_id: release('dtpp').id, mode: 'current', items: [catalogAirport] }) : undefined
    renderStrict()
    await screen.findByText('API 已连接')
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'ZZZ' } })
    fireEvent.click(screen.getByRole('button', { name: '搜索', exact: true }))
    fireEvent.click(within(await screen.findByLabelText('搜索结果')).getByRole('button', { name: /SYNTHETIC TEST AIRPORT/ }))
    await screen.findByRole('button', { name: /SYNTHETIC DEPARTURE CHART/ })
    expect(screen.getByTestId('map-features')).toHaveTextContent('[]')
    expect(requested.some((url) => url.pathname === '/api/v1/airports/ZZZ/charts' && url.searchParams.get('release_id') === release('dtpp').id)).toBe(true)
  })

  it('removes another-cycle PDF when a procedure is selected', async () => {
    snapshot.current_releases.dtpp = release('dtpp', { airac: '2610' })
    renderStrict()
    await chooseAirport()
    fireEvent.click(await screen.findByRole('button', { name: /SYNTHETIC DEPARTURE CHART/ }))
    expect(screen.getByTitle('官方航图 SYNTHETIC DEPARTURE CHART')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /SYNTHETIC SID/ }))
    await screen.findByRole('combobox', { name: '程序分支' })
    expect(screen.queryByTitle(/官方航图/)).not.toBeInTheDocument()
    expect(screen.getByText(/没有与所选程序周期及有效期匹配的航图/)).toBeVisible()
  })

  it('clears current records at the server effective-time boundary', async () => {
    const expiring = release('nasr', { valid_to: '2026-09-07T00:00:00.600Z' })
    snapshot = status({ current_releases: { nasr: expiring }, releases: [expiring] })
    let statusReads = 0
    override = (url) => {
      if (!url.pathname.endsWith('/status')) return undefined
      statusReads += 1
      return response(statusReads === 1 ? snapshot : status({ current_releases: {}, releases: [], publication_state: 'empty' }))
    }
    renderStrict()
    fireEvent.click(screen.getByRole('button', { name: '测试放大地图' }))
    await screen.findByText('API 已连接')
    await waitFor(() => expect(screen.getByTestId('map-features')).toHaveTextContent('test:airport:ZZZ'))
    await screen.findByText('尚无已验证的当前资料')
    expect(screen.getByTestId('map-features')).toHaveTextContent('[]')
    expect(statusReads).toBeGreaterThanOrEqual(2)
  })
})

