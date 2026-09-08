import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { AviationMap } from './AviationMap'
import { AIRPORT_MIN_ZOOM, LAYER_MIN_ZOOM, EMPTY_MAP, MAP_FEATURE_LIMIT, type MapData, type MapViewport } from './map-data'
import {
  ApiError, assertSnapshot, assertVersion, errorMessage, getJson, isAbort, snapshotQuery, versionQuery,
  type Coverage, type Envelope, type FeaturesResponse, type GeometryResponse, type Layer,
  type Mode, type Procedure, type Release, type Report, type ResearchRecord,
  type SearchResult, type SnapshotEnvelope, type SnapshotFeatures, type SnapshotRecord, type SnapshotReport, type SnapshotStatus, type Source, type Status,
} from './api'
import { ResearchPanel } from './ResearchPanel'
import { WorkspaceSplitter } from './WorkspaceSplitter'
import { expired, MODE_NAMES, PRODUCT_NAMES, PRODUCTS, releaseKey, researchMode, sameChartCycle, selectedReleases, selectedSnapshot, snapshotChartDate, snapshotChoices, utc, type Selection } from './session'
import './App.css'

const LAYERS: { id: Layer; name: string; product: string }[] = [
  { id: 'airports', name: '机场', product: 'nasr' },
  { id: 'runways', name: '跑道', product: 'cifp' },
  { id: 'navaids', name: '导航台', product: 'cifp' },
  { id: 'waypoints', name: '航点', product: 'cifp' },
  { id: 'airways', name: '航路', product: 'cifp' },
]
const COVERAGE_NAMES: Record<string, string> = { 'not-imported': '未导入', current: '当前有效', preview: '预览', history: '历史', expired: '已过期', revoked: '已撤销', quarantined: '已隔离', staged: '待发布', blocked: '已阻断', failed: '获取失败' }

function coverageSummary(note: string) {
  if (note.includes('validity-evidence-missing')) return '原件已保存；官方精确生效时间尚待核实。'
  if (note.includes('needs-user-action')) return '官方获取入口需要人工处理。'
  return note.length > 180 ? `${note.slice(0, 160)}…` : note
}

function App() {
  const [status, setStatus] = useState<Status | null>(null)
  const [coverage, setCoverage] = useState<Coverage[]>([])
  const [sources, setSources] = useState<Source[]>([])
  const [connection, setConnection] = useState<'loading' | 'online' | 'offline'>('loading')
  const [error, setError] = useState('')
  const [mode, setMode] = useState<Mode>('current')
  const [browse, setBrowse] = useState<'research' | 'strict'>('research')
  const [snapshotId, setSnapshotId] = useState('')
  const [deskWidth, setDeskWidth] = useState(500)
  const [selection, setSelection] = useState<Selection>({})
  const [layers, setLayers] = useState<Layer[]>(['airports'])
  const [viewport, setViewport] = useState<MapViewport | null>(null)
  const [features, setFeatures] = useState<MapData>(EMPTY_MAP)
  const [mapLoading, setMapLoading] = useState(false)
  const [truncated, setTruncated] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [searchState, setSearchState] = useState('')
  const [selected, setSelected] = useState<SearchResult | null>(null)
  const [focus, setFocus] = useState<[number, number] | null>(null)
  const [procedures, setProcedures] = useState<ResearchRecord[]>([])
  const [detail, setDetail] = useState<Procedure | null>(null)
  const [procedureChosen, setProcedureChosen] = useState(false)
  const [branch, setBranch] = useState('')
  const [geometry, setGeometry] = useState<GeometryResponse | null>(null)
  const [charts, setCharts] = useState<ResearchRecord[]>([])
  const [chartMessage, setChartMessage] = useState('')
  const [researchMessage, setResearchMessage] = useState('')
  const [researchLoading, setResearchLoading] = useState(false)
  const [chartsLoading, setChartsLoading] = useState(false)
  const [communications, setCommunications] = useState<ResearchRecord[]>([])
  const [communicationsLoading, setCommunicationsLoading] = useState(false)
  const [communicationsMessage, setCommunicationsMessage] = useState('')
  const airportRequest = useRef<AbortController | null>(null)
  const [report, setReport] = useState<Report | null>(null)
  const [snapshotReport, setSnapshotReport] = useState<SnapshotReport | null>(null)
  const epoch = useRef(0)
  const researchEpoch = useRef(0)
  const detailEpoch = useRef(0)
  const searchEpoch = useRef(0)
  const refreshEpoch = useRef(0)
  const clock = useRef({ server: 0, received: 0 })
  const pickedReleases = { ...selectedReleases(status, mode, selection) }
  if (browse === 'research') delete pickedReleases.nasr
  const releaseJson = JSON.stringify(pickedReleases)
  const releases = useMemo(() => JSON.parse(releaseJson) as Record<string, Release>, [releaseJson])
  const snapshotJson = JSON.stringify(browse === 'research' ? selectedSnapshot(status, researchMode(mode), snapshotId) ?? null : null)
  const snapshot = useMemo(() => JSON.parse(snapshotJson) as SnapshotStatus | null, [snapshotJson])
  const key = `${browse}:${snapshot?.id ?? ''}:${releaseKey(releases, mode)}`
  const latest = useRef({ status, mode, releases, key, browse, snapshot, snapshotId })
  useLayoutEffect(() => { latest.current = { status, mode, releases, key, browse, snapshot, snapshotId } }, [status, mode, releases, key, browse, snapshot, snapshotId])

  const clearResearch = useCallback(() => {
    airportRequest.current?.abort()
    researchEpoch.current += 1
    detailEpoch.current += 1
    setProcedureChosen(false)
    setSelected(null); setFocus(null); setProcedures([]); setDetail(null); setBranch(''); setGeometry(null)
    setCharts([]); setChartMessage(''); setResearchMessage(''); setResearchLoading(false); setChartsLoading(false)
    setCommunications([]); setCommunicationsLoading(false); setCommunicationsMessage('')
  }, [])
  useEffect(() => () => { airportRequest.current?.abort() }, [])
  const clearData = useCallback(() => {
    epoch.current += 1; searchEpoch.current += 1
    setFeatures(EMPTY_MAP); setMapLoading(false); setTruncated(false); setResults([]); setSearchState(''); setReport(null); setSnapshotReport(null); setFocus(null)
    clearResearch()
  }, [clearResearch])
  const fail = useCallback((reason: unknown) => {
    if (isAbort(reason)) return
    refreshEpoch.current += 1
    clearData(); setError(errorMessage(reason)); setStatus(null)
    setConnection(reason instanceof ApiError ? 'online' : 'offline')
  }, [clearData])

  const updateViewport = useCallback((next: MapViewport | null) => {
    setViewport((previous) => previous && next && previous.zoom === next.zoom
      && previous.bounds.every((value, index) => value === next.bounds[index]) ? previous : next)
  }, [])

  const refresh = useCallback(async (clearFirst = false) => {
    const token = ++refreshEpoch.current
    if (clearFirst) { clearData(); setStatus(null); setConnection('loading') }
    try {
      const [next, nextCoverage, nextSources] = await Promise.all([
        getJson<Status>('/status'), getJson<Coverage[]>('/coverage'), getJson<Source[]>('/sources'),
      ])
      if (token !== refreshEpoch.current) return
      const previous = latest.current
      if (previous.mode === 'current') {
        const nextReleases = { ...next.current_releases }
        if (previous.browse === 'research') delete nextReleases.nasr
        const nextSnapshot = previous.browse === 'research' ? selectedSnapshot(next, 'active', '') : undefined
        if (`${previous.browse}:${nextSnapshot?.id ?? ''}:${releaseKey(nextReleases, 'current')}` !== previous.key) clearData()
      }
      if (previous.mode !== 'current') {
        const ids = new Set(next.releases.filter((item) => item.state === previous.mode).map((item) => item.id))
        if (Object.values(previous.releases).some((item) => !ids.has(item.id))) clearData()
        if (previous.snapshot && !selectedSnapshot(next, researchMode(previous.mode), previous.snapshot.id)) clearData()
      }
      clock.current = { server: Date.parse(next.current_time), received: performance.now() }
      setStatus(next); setCoverage(nextCoverage); setSources(nextSources); setConnection('online'); setError('')
    } catch (reason) { if (token === refreshEpoch.current) fail(reason) }
  }, [clearData, fail])

  useEffect(() => {
    // The network subscription initializes the displayed publication snapshot.
    // eslint-disable-next-line react/set-state-in-effect
    void refresh()
    const interval = window.setInterval(() => {
      const current = latest.current
      const now = clock.current.server + performance.now() - clock.current.received
      if (current.mode === 'current' && expired(current.releases, now)) void refresh(true)
      else void refresh()
    }, 30000)
    const wake = () => { if (document.visibilityState === 'visible') void refresh(true) }
    document.addEventListener('visibilitychange', wake); window.addEventListener('focus', wake)
    return () => {
      refreshEpoch.current += 1
      window.clearInterval(interval); document.removeEventListener('visibilitychange', wake); window.removeEventListener('focus', wake)
    }
  }, [refresh])

  useEffect(() => {
    if (mode !== 'current' || Object.keys(releases).length === 0) return
    const deadline = Math.min(...Object.values(releases).map((item) => Date.parse(item.valid_to)))
    const now = clock.current.server + performance.now() - clock.current.received
    const timeout = window.setTimeout(() => { clearData(); setStatus(null); setError('资料已到期，正在重新检查发布状态。'); void refresh() }, Math.max(0, Math.min(2147483647, deadline - now)))
    return () => window.clearTimeout(timeout)
  }, [releases, status, mode, clearData, refresh])

  useEffect(() => {
    const controller = new AbortController()
    const token = epoch.current
    // A new view or publication must remove the previous query before loading.
    // eslint-disable-next-line react/set-state-in-effect
    setFeatures(EMPTY_MAP); setTruncated(false)
    const requested = viewport ? LAYERS.filter((layer) => layers.includes(layer.id)
      && viewport.zoom >= LAYER_MIN_ZOOM[layer.id]
      && (snapshot?.capabilities.includes(layer.id) || releases[layer.product]?.capabilities.includes(layer.id))) : []
    setMapLoading(requested.length > 0)
    if (!viewport || requested.length === 0) return () => controller.abort()
    const timer = window.setTimeout(() => {
      Promise.all(requested.map(async (layer) => {
        const query = { layer: layer.id, bbox: viewport.bounds.join(','), limit: String(MAP_FEATURE_LIMIT) }
        if (snapshot?.capabilities.includes(layer.id)) return assertSnapshot(await getJson<SnapshotFeatures>(`/research/features?${snapshotQuery(snapshot, researchMode(mode), query)}`, controller.signal), snapshot, researchMode(mode))
        const release = releases[layer.product]
        return assertVersion(await getJson<FeaturesResponse>(`/features?${versionQuery(release, mode, query)}`, controller.signal), release, mode)
      })).then((payloads) => {
        if (token !== epoch.current || controller.signal.aborted) return
        setFeatures({ type: 'FeatureCollection', features: payloads.flatMap((payload) => payload.features) })
        setMapLoading(false)
        setTruncated(payloads.some((payload) => payload.truncated))
      }).catch((reason: unknown) => { if (token === epoch.current && !controller.signal.aborted) fail(reason) })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [releases, snapshot, layers, viewport, mode, fail])

  const search = async (event: React.FormEvent) => {
    event.preventDefault()
    const text = query.trim()
    const token = ++searchEpoch.current
    setResults([])
    if (!text) { setSearchState('请输入机场标识或名称。'); return }
    const available = [releases.nasr, releases.cifp, releases.dtpp].filter((item): item is Release => Boolean(item))
    if (!available.length && !snapshot) { setSearchState('所选版本没有可搜索的资料。'); return }
    setSearchState('正在搜索…')
    try {
      const requests: Promise<SearchResult[]>[] = available.map(async (release) => {
        const payload = assertVersion(await getJson<Envelope>(`/search?${versionQuery(release, mode, { q: text })}`), release, mode)
        return payload.items.map((record) => ({ ...record, release_id: release.id, product_id: release.product_id }))
      })
      if (snapshot) requests.unshift(getJson<SnapshotEnvelope>(`/research/search?${snapshotQuery(snapshot, researchMode(mode), { q: text })}`).then((response) => {
        const payload = assertSnapshot(response, snapshot, researchMode(mode))
        return payload.items.map((record) => ({ ...record, snapshot_id: snapshot.id, product_id: 'nasr' }))
      }))
      const payloads = await Promise.all(requests)
      if (token !== searchEpoch.current) return
      const found = payloads.flat()
      setResults(found); setSearchState(found.length ? `${found.length} 条结果` : '没有找到匹配记录。')
    } catch (reason) { if (token === searchEpoch.current) fail(reason) }
  }

  const selectProcedure = async (record: ResearchRecord) => {
    const release = releases.cifp
    if (!release) return
    const token = ++detailEpoch.current
    setProcedureChosen(true)
    setDetail(null); setGeometry(null); setBranch(''); setResearchLoading(true); setResearchMessage('')
    if (!sameChartCycle(release, releases.dtpp)) { setCharts([]); setChartMessage('没有与所选程序周期及有效期匹配的航图。请显式选择对应版本。') }
    else setChartMessage('程序与航图关联未确认。请选择机场目录中的官方航图核对。')
    try {
      const payload = assertVersion(await getJson<Procedure>(`/procedures/${encodeURIComponent(record.id)}?${versionQuery(release, mode)}`), release, mode)
      if (token !== detailEpoch.current) return
      setDetail(payload); setResearchLoading(false)
      if (!payload.branches.length) setResearchMessage('该程序尚无可查看的结构化分支。')
    } catch (reason) { if (token === detailEpoch.current) fail(reason) }
  }

  const selectResult = async (record: SearchResult, fromMap = false) => {
    clearResearch()
    const token = researchEpoch.current
    const controller = new AbortController()
    airportRequest.current = controller
    setSelected(record); setResults([]); setSearchState('')
    if (!fromMap && record.geometry?.type === 'Point') setFocus(record.geometry.coordinates.slice(0, 2) as [number, number])
    if (fromMap && record.snapshot_id && snapshot) {
      void getJson<SnapshotRecord>(`/research/records/${encodeURIComponent(record.id)}?${snapshotQuery(snapshot, researchMode(mode))}`, controller.signal).then((response) => {
        if (token !== researchEpoch.current || controller.signal.aborted) return
        const payload = assertSnapshot(response, snapshot, researchMode(mode))
        setSelected({ ...payload.record, snapshot_id: snapshot.id, product_id: 'nasr' })
      }).catch((reason: unknown) => { if (token === researchEpoch.current && !controller.signal.aborted) fail(reason) })
    }
    if (record.kind === 'procedure') { await selectProcedure(record); return }
    if (record.kind !== 'airport') return
    const cifp = releases.cifp
    const dtpp = releases.dtpp
    const icao = record.product_id === 'cifp' ? record.identifier : String(record.properties.icao_id ?? '')
    const faa = ['nasr', 'dtpp'].includes(record.product_id) ? record.identifier : String(record.properties.faa_id ?? '')
    const requests: Promise<void>[] = []
    if (record.snapshot_id && snapshot?.capabilities.includes('communications')) {
      setCommunicationsLoading(true)
      requests.push(getJson<SnapshotEnvelope>(`/research/airports/${encodeURIComponent(record.id)}/communications?${snapshotQuery(snapshot, researchMode(mode))}`, controller.signal).then((response) => {
        if (token !== researchEpoch.current || controller.signal.aborted) return
        const payload = assertSnapshot(response, snapshot, researchMode(mode))
        setCommunications(payload.items); setCommunicationsLoading(false)
      }).catch((reason: unknown) => {
        if (token !== researchEpoch.current || controller.signal.aborted) return
        if (reason instanceof ApiError && [403, 409, 410].includes(reason.status)) { fail(reason); return }
        setCommunicationsLoading(false); setCommunicationsMessage(`通信频率读取失败：${errorMessage(reason)}`)
      }))
    } else setCommunicationsMessage('所选资料版本未包含机场通信频率。')
    if (cifp && icao) {
      setResearchLoading(true)
      requests.push(getJson<Envelope>(`/airports/${encodeURIComponent(icao)}/procedures?${versionQuery(cifp, mode)}`).then((payload) => {
        assertVersion(payload, cifp, mode)
        if (token !== researchEpoch.current) return
        setProcedures(payload.items); setResearchLoading(false)
        if (!payload.items.length) setResearchMessage('此版本没有该机场的已支持程序记录；航图目录覆盖独立显示。')
      }))
    } else setResearchMessage(cifp ? '该机场没有已确认的 ICAO 标识，无法关联 CIFP 程序。' : '尚无所选版本的 CIFP 矢量资料。')
    if (record.snapshot_id && !snapshotChartDate(snapshot ?? undefined, dtpp)) {
      setChartMessage('没有与机场官方日期相同的航图版本。请显式选择对应版本；不会搭配其他日期的 PDF。')
    } else if (dtpp && faa) {
      setChartsLoading(true)
      requests.push(getJson<Envelope>(`/airports/${encodeURIComponent(faa)}/charts?${versionQuery(dtpp, mode)}`).then((payload) => {
        assertVersion(payload, dtpp, mode)
        if (token !== researchEpoch.current) return
        setCharts(payload.items); setChartsLoading(false)
      }))
    } else setChartMessage(dtpp ? '缺少已确认的 FAA 机场标识，航图关联未确认。' : '尚无所选版本的 d-TPP 航图目录。')
    try { await Promise.all(requests) } catch (reason) { if (token === researchEpoch.current) fail(reason) }
  }

  const selectBranch = async (id: string) => {
    setBranch(id); setGeometry(null)
    const release = releases.cifp
    const token = ++detailEpoch.current
    if (!id || !detail || !release) return
    try {
      const payload = assertVersion(await getJson<GeometryResponse>(`/procedures/${encodeURIComponent(detail.record.id)}/geometry?${versionQuery(release, mode, { branch_id: id })}`), release, mode)
      if (token === detailEpoch.current) setGeometry(payload)
    } catch (reason) { if (token === detailEpoch.current) fail(reason) }
  }

  const showReport = async (release: Release) => {
    const token = epoch.current
    setReport(null)
    try {
      const payload = await getJson<Report>(`/releases/${encodeURIComponent(release.id)}/report`)
      if (token === epoch.current) setReport(payload)
    } catch (reason) { if (token === epoch.current) fail(reason) }
  }

  const showSnapshotReport = async () => {
    if (!snapshot) return
    const token = epoch.current
    setSnapshotReport(null)
    try {
      const payload = await getJson<SnapshotReport>(`/research/snapshots/${encodeURIComponent(snapshot.id)}/report`)
      if (token === epoch.current) setSnapshotReport(payload)
    } catch (reason) { if (token === epoch.current) fail(reason) }
  }

  const hasReleases = Object.keys(releases).length > 0 || Boolean(snapshot)
  const releaseDates = [...new Set(Object.values(releases).map((release) => release.valid_from.slice(0, 10)))]
  const dataDate = snapshot?.official_effective_date ?? (releaseDates.length === 1 ? releaseDates[0] : releaseDates.length > 1 ? '多个日期' : connection === 'loading' ? '检查中…' : '未加载')
  const airportOverview = viewport && viewport.zoom < AIRPORT_MIN_ZOOM && layers.includes('airports')
    && Boolean(snapshot || releases.nasr?.capabilities.includes('airports'))
  return <main className="app-shell" aria-label="研究工作区" tabIndex={0} style={{ '--desk-width': `${deskWidth}px` } as React.CSSProperties}>
    <AviationMap features={features} procedure={geometry ?? EMPTY_MAP} focus={focus} highlight={selected?.geometry?.type === 'Point' ? selected.geometry.coordinates as [number, number] : null} onViewport={updateViewport} onFeature={(properties) => {
      const release = Object.values(releases).find((item) => item.id === properties.release_id)
      const researchSnapshot = snapshot?.id === properties.snapshot_id ? snapshot : null
      if ((!release && !researchSnapshot) || typeof properties.id !== 'string') return
      const feature = features.features.find((item) => item.properties?.id === properties.id)
      if (!feature?.properties) return
      const p = feature.properties
      void selectResult({ id: p.id, kind: p.kind, name: p.name, identifier: p.identifier, airport_id: p.airport_id, airport_ident: p.airport_ident,
        parent_id: null, branch_id: null, sequence: null, geometry: feature.geometry, properties: p, provenance: p.provenance,
        release_id: release?.id, snapshot_id: researchSnapshot?.id, product_id: release?.product_id ?? 'nasr' }, true)
    }} />
    <header className="topbar glass-panel">
      <div className="brand-mark" aria-hidden="true"><span className="brand-wing">◢</span></div>
      <div className="brand-copy"><strong>FLIGHT MAP</strong><span>航空资料研究平台</span></div>
      <form className="search-box" onSubmit={(event) => void search(event)}><span aria-hidden="true">⌕</span>
        <input value={query} onChange={(event) => { setQuery(event.target.value); setResults([]); setSearchState(''); searchEpoch.current += 1 }} placeholder="搜索机场，例如 KJFK、SEA" aria-label="搜索机场、航点、航路或程序" />
        <button type="submit">搜索</button>
      </form>
      <div className={`connection-state ${connection}`}><i />{connection === 'online' ? 'API 已连接' : connection === 'loading' ? '正在连接' : 'API 未连接'}</div>
    </header>
    <aside className="left-panel glass-panel" aria-label="资料版本与图层">
      <details className="data-management">
        <summary><span className="data-date">资料 <b>{dataDate}</b></span><span className="data-management-label">数据管理</span></summary>
        <div className="data-management-body">
      <section><div className="section-heading"><span>资料版本</span><button className="text-button" onClick={() => void refresh(true)}>重新检查</button></div>
        <div className="mode-tabs">{(['research', 'strict'] as const).map((item) => <button key={item} aria-pressed={browse === item} className={browse === item ? 'active' : ''} onClick={() => { if (browse !== item) { clearData(); setBrowse(item); setMode('current'); setSelection({}); setSnapshotId('') } }}>{item === 'research' ? '日期级研究' : '严格有效期'}</button>)}</div>
        {browse === 'research' && <p className="muted-copy">机场按官方日期研究；精确生效时刻未知。陈旧资料保留日期和更新提醒。</p>}
        <div className="mode-tabs">{(['current', 'preview', 'history'] as const).map((item) => <button key={item} className={mode === item ? 'active' : ''} aria-pressed={mode === item} onClick={() => { if (mode !== item) { clearData(); setMode(item); setSelection({}) } }}>{MODE_NAMES[item]}</button>)}</div>
        {mode !== 'current' && <p className="inline-notice">{MODE_NAMES[mode]} · 需显式选择每个产品的版本。</p>}
        {browse === 'research' && <div className="release-row">
          <label className="field-label">NASR · 机场研究快照
            {mode === 'current' ? <span className="current-release">{snapshot?.official_effective_date ?? '无活动研究快照'}</span> : <select aria-label="机场研究快照版本" value={snapshotId} onChange={(event) => { clearData(); setSnapshotId(event.target.value) }}>
              <option value="">未选择</option>{snapshotChoices(status, researchMode(mode)).map((item) => <option key={item.id} value={item.id}>{item.official_effective_date} · {item.id.slice(-8)}</option>)}
            </select>}
          </label>
          {snapshot && <><p className="version-caption">{snapshot.id}</p><p className="muted-copy">官方日期 {snapshot.official_effective_date} · 精度：日<br />预计更新 {snapshot.expected_update_date}</p>
            {snapshot.date_status === 'update-due' && <p className="inline-notice">已到预计更新日期 · 当前仍在研究旧快照。</p>}
            {mode !== 'current' && <p className="inline-notice">{MODE_NAMES[mode]} · {snapshot.official_effective_date}</p>}
            <button className="text-button" onClick={() => void showSnapshotReport()}>研究验证报告 ↗</button></>}
        </div>}
        {PRODUCTS.filter((product) => browse !== 'research' || product !== 'nasr').map((product) => <div className="release-row" key={product}>
          <label className="field-label">{PRODUCT_NAMES[product]}
            {mode === 'current' ? <span className="current-release">{releases[product] ? `${releases[product].airac} · ${releases[product].id.slice(-8)}` : '无当前发布'}</span> :
              <select aria-label={`${PRODUCT_NAMES[product]}版本`} value={selection[product] ?? ''} onChange={(event) => { clearData(); setSelection({ ...selection, [product]: event.target.value }) }}>
                <option value="">未选择</option>{status?.releases.filter((item) => item.product_id === product && item.state === mode).map((item) => <option key={item.id} value={item.id}>{item.airac} · {item.id.slice(-8)}</option>)}
              </select>}
          </label>
          {releases[product] && <><small className="version-caption">至 {utc(releases[product].valid_to)}</small><button className="text-button" onClick={() => void showReport(releases[product])}>验证报告 ↗</button></>}
        </div>)}
      </section>
      <section><div className="section-heading"><span>产品覆盖</span></div>
        {coverage.map((row) => {
          const activeResearch = browse === 'research' && row.product_id === 'nasr' ? status?.research?.active_snapshots.nasr : undefined
          return <div className="coverage-item" key={row.product_id}><b>{PRODUCT_NAMES[row.product_id] ?? row.name}</b><span>{activeResearch ? '研究可用' : COVERAGE_NAMES[row.status] ?? row.status}</span>
          {activeResearch && <><p>活动研究快照 · 官方日期 {activeResearch.official_effective_date}</p><p className="version-caption">{activeResearch.id}</p>
            {activeResearch.date_status === 'update-due' && <p>已到预计更新日期；当前可研究旧快照。</p>}
            {row.status !== 'current' && <details><summary>严格 Current 状态</summary><p>严格 Current 未启用；日期级研究快照可用。</p><p>{row.note}</p></details>}
          </>}
          {row.note && !activeResearch && <><p>{coverageSummary(row.note)}</p>{coverageSummary(row.note) !== row.note && <details><summary>查看获取记录</summary><p>{row.note}</p></details>}</>}
          {row.last_successful_release && <>
            <p>最近验证通过 {row.last_successful_release.airac} · {row.last_successful_release.id}</p>
            <p className="version-caption">有效期 {utc(row.last_successful_release.valid_from)} — {utc(row.last_successful_release.valid_to)}</p>
          </>}
          {row.notices_url && <p><a href={row.notices_url} target="_blank" rel="noopener noreferrer">官方更正公告 ↗</a></p>}
        </div>})}
        {!coverage.length && <p className="muted-copy">等待 API 提供覆盖状态。</p>}
      </section>
      <section><div className="section-heading"><span>官方来源与使用依据</span></div>
        {sources.flatMap((source) => source.products.map((product) => <details className="source-detail" key={`${source.id}:${product.id}`}><summary>{product.name}</summary>
          <a href={product.landing_page} target="_blank" rel="noopener noreferrer">官方产品页 ↗</a>
          <p>{product.notes}</p><p>本地获取：{product.local_access?.acquisition ?? 'unknown'} · 处理：{product.local_access?.processing ?? 'unknown'}</p><p>{product.redistribution}</p>
          {product.local_access?.evidence.map((evidence) => <p key={evidence}>{evidence}</p>)}
        </details>))}
      </section>
        </div>
      </details>
      {mode !== 'current' && <p className="data-attention">正在查看{MODE_NAMES[mode]}</p>}
      {snapshot?.date_status === 'update-due' && <p className="data-attention">资料待更新 · 当前日期 {snapshot.official_effective_date}</p>}
      <section className="map-layer-controls"><div className="section-heading"><span>数据图层</span><small>{features.features.length} 个要素</small></div>
        <div className="layer-list">{LAYERS.map((layer) => {
          const available = Boolean(snapshot?.capabilities.includes(layer.id) || releases[layer.product]?.capabilities.includes(layer.id))
          return <label key={layer.id} className={`layer-row ${available ? '' : 'disabled'}`}><input type="checkbox" checked={available && layers.includes(layer.id)} disabled={!available} onChange={(event) => setLayers(event.target.checked ? [...layers, layer.id] : layers.filter((id) => id !== layer.id))} /><i aria-hidden="true" className={`legend-swatch ${layer.id}`} /><span>{layer.name}</span><small>{available ? !viewport || viewport.zoom < LAYER_MIN_ZOOM[layer.id] ? `放大显示 · Z${LAYER_MIN_ZOOM[layer.id]}` : '按视野' : '未支持'}</small></label>
        })}</div>
        <p className="muted-copy">放大后按视野加载 · 点击机场查看通信频率</p>
      </section>
    </aside>
    {(error || searchState) && <div className="floating-message glass-panel" role="status">{error || searchState}{error && <button className="text-button" onClick={() => void refresh(true)}>重试</button>}</div>}
    {results.length > 0 && <div className="search-results glass-panel" aria-label="搜索结果">{results.map((item) => <button key={`${item.snapshot_id ?? item.release_id}:${item.id}`} onClick={() => void selectResult(item)}><strong>{item.identifier || item.name}</strong><span>{item.name}</span><small>{item.kind} · {item.product_id.toUpperCase()}{item.snapshot_id ? ' · 研究' : ''}</small></button>)}</div>}
    {!hasReleases && !selected && <section className="empty-state glass-panel">
      <div className="radar-icon" aria-hidden="true"><i /><i /></div><span className="eyebrow">FAA RESEARCH</span>
      <h1>{connection === 'loading' ? '正在检查资料版本' : mode === 'current' ? browse === 'research' ? '尚无可用研究资料' : '尚无已验证的当前资料' : '请选择资料版本'}</h1>
      <p>{mode === 'current' ? '底图可独立浏览。获取官方资料、查看报告并激活研究快照后，便可开始研究。' : '在左侧为各产品选择版本。预览和历史资料始终保留版本标识。'}</p>
    </section>}
    {mapLoading && <div className="map-caption" role="status">正在读取当前视野的机场与图层…</div>}
    {hasReleases && airportOverview && !features.features.length && !mapLoading && !error && <div className="map-caption">放大地图查看附近机场，或搜索机场直接定位</div>}
    {hasReleases && viewport && !airportOverview && !mapLoading && !features.features.length && !error && <div className="map-caption">当前视野内没有已启用图层要素 · 可搜索定位</div>}
    {truncated && <div className="map-caption">当前视野资料较多，请继续放大查看完整分布。</div>}
    <WorkspaceSplitter width={deskWidth} onWidth={setDeskWidth} />
    <ResearchPanel selected={selected} snapshot={selected?.snapshot_id ? snapshot ?? undefined : undefined} release={selected ? releases[selected.product_id] : undefined} procedureRelease={releases.cifp} procedures={procedures} detail={detail} branch={branch} geometry={geometry}
      communications={communications} communicationsLoading={communicationsLoading} communicationsMessage={communicationsMessage}
      charts={procedureChosen && !sameChartCycle(releases.cifp, releases.dtpp) ? [] : charts} chartRelease={releases.dtpp} chartMessage={chartMessage} loading={researchLoading} chartsLoading={chartsLoading} message={researchMessage}
      onProcedure={(record) => void selectProcedure(record)} onBranch={(id) => void selectBranch(id)} onClose={clearResearch} mode={mode} onInvalid={fail} />
    {report && <div className="report-backdrop"><section className="report-modal glass-panel" role="dialog" aria-modal="true" aria-label="验证报告">
      <div className="section-heading"><span>验证报告 · {report.release.product_id.toUpperCase()}</span><button onClick={() => setReport(null)}>关闭报告</button></div>
      <h2>{report.release.airac}</h2><p className="version-caption">{report.release.id}</p><p>{utc(report.release.valid_from)} — {utc(report.release.valid_to)}</p>
      <div className="report-counts">{Object.entries({ 输入: report.report.input_count, 成功: report.report.success_count, 不支持: report.report.unsupported_count, 错误: report.report.error_count }).map(([label, value]) => <div key={label}><strong>{value}</strong><span>{label}</span></div>)}</div>
      <ul>{report.report.issues.map((issue, index) => <li key={`${issue.code}:${index}`}><b>{issue.severity} · {issue.code}</b> {issue.message}</li>)}</ul>
      <details><summary>周期差异报告</summary><pre>{JSON.stringify(report.diff, null, 2)}</pre></details>
      <details><summary>产品有效期依据</summary>{report.release.validity_evidence.map((evidence) => <p key={evidence}>{evidence}</p>)}</details>
    </section></div>}
    {snapshotReport && <div className="report-backdrop"><section className="report-modal glass-panel" role="dialog" aria-modal="true" aria-label="研究验证报告">
      <div className="section-heading"><span>机场研究快照验证报告</span><button onClick={() => setSnapshotReport(null)}>关闭报告</button></div>
      <h2>官方日期 {snapshotReport.snapshot.official_effective_date}</h2><p className="version-caption">{snapshotReport.snapshot.id}</p><p>{snapshotReport.disclaimer}</p>
      <div className="report-counts">{Object.entries({ 输入: snapshotReport.report.input_count, 成功: snapshotReport.report.success_count, 不支持: snapshotReport.report.unsupported_count, 错误: snapshotReport.report.error_count }).map(([label, value]) => <div key={label}><strong>{value}</strong><span>{label}</span></div>)}</div>
      <ul>{snapshotReport.report.issues.map((issue, index) => <li key={index}>{issue.code} · {issue.message}</li>)}</ul>
      <details><summary>日期依据与原件</summary><pre>{JSON.stringify({ date_evidence: snapshotReport.snapshot.date_evidence, inputs: snapshotReport.inputs }, null, 2)}</pre></details>
    </section></div>}
    <footer className="statusbar glass-panel"><div><span className="status-dot" /><b>{browse === 'research' ? '日期级研究 · ' : ''}{MODE_NAMES[mode]}</b></div><div>{snapshot ? '官方日期' : '发布'} <b>{snapshot?.official_effective_date ?? status?.publication_state ?? 'UNKNOWN'}</b></div><div>AIRAC 日历 <b>{status?.airac.identifier ?? '----'}</b></div><div className="status-spacer" /><div>仅供研究 · 原件可追溯</div><div>UTC <b>{status ? new Date(status.current_time).toISOString().slice(11, 16) : '--:--'}</b></div></footer>
  </main>
}

export default App

