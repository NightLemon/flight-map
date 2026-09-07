import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { AviationMap } from './AviationMap'
import { EMPTY_MAP, type Bounds, type MapData } from './map-data'
import {
  assertVersion, errorMessage, getJson, isAbort, versionQuery,
  type Coverage, type Envelope, type FeaturesResponse, type GeometryResponse, type Layer,
  type Mode, type Procedure, type Release, type Report, type ResearchRecord,
  type SearchResult, type Source, type Status,
} from './api'
import { ResearchPanel } from './ResearchPanel'
import { expired, MODE_NAMES, PRODUCT_NAMES, PRODUCTS, releaseKey, sameChartCycle, selectedReleases, utc, type Selection } from './session'
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
  const [selection, setSelection] = useState<Selection>({})
  const [layers, setLayers] = useState<Layer[]>(['airports'])
  const [bounds, setBounds] = useState<Bounds>([-180, -90, 180, 90])
  const [features, setFeatures] = useState<MapData>(EMPTY_MAP)
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
  const [report, setReport] = useState<Report | null>(null)
  const epoch = useRef(0)
  const researchEpoch = useRef(0)
  const detailEpoch = useRef(0)
  const searchEpoch = useRef(0)
  const refreshEpoch = useRef(0)
  const clock = useRef({ server: 0, received: 0 })
  const releaseJson = JSON.stringify(selectedReleases(status, mode, selection))
  const releases = useMemo(() => JSON.parse(releaseJson) as Record<string, Release>, [releaseJson])
  const key = releaseKey(releases, mode)
  const latest = useRef({ status, mode, releases, key })
  useLayoutEffect(() => { latest.current = { status, mode, releases, key } }, [status, mode, releases, key])

  const clearResearch = useCallback(() => {
    researchEpoch.current += 1
    detailEpoch.current += 1
    setProcedureChosen(false)
    setSelected(null); setProcedures([]); setDetail(null); setBranch(''); setGeometry(null)
    setCharts([]); setChartMessage(''); setResearchMessage(''); setResearchLoading(false); setChartsLoading(false)
  }, [])
  const clearData = useCallback(() => {
    epoch.current += 1; searchEpoch.current += 1
    setFeatures(EMPTY_MAP); setTruncated(false); setResults([]); setSearchState(''); setReport(null)
    clearResearch()
  }, [clearResearch])
  const fail = useCallback((reason: unknown) => {
    if (isAbort(reason)) return
    refreshEpoch.current += 1
    clearData(); setError(errorMessage(reason)); setStatus(null); setConnection('offline')
  }, [clearData])

  const refresh = useCallback(async (clearFirst = false) => {
    const token = ++refreshEpoch.current
    if (clearFirst) { clearData(); setStatus(null); setConnection('loading') }
    try {
      const [next, nextCoverage, nextSources] = await Promise.all([
        getJson<Status>('/status'), getJson<Coverage[]>('/coverage'), getJson<Source[]>('/sources'),
      ])
      if (token !== refreshEpoch.current) return
      const previous = latest.current
      if (previous.mode === 'current' && releaseKey(next.current_releases, 'current') !== previous.key) clearData()
      if (previous.mode !== 'current') {
        const ids = new Set(next.releases.filter((item) => item.state === previous.mode).map((item) => item.id))
        if (Object.values(previous.releases).some((item) => !ids.has(item.id))) clearData()
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
    const requested = LAYERS.filter((layer) => layers.includes(layer.id) && releases[layer.product]?.capabilities.includes(layer.id))
    if (requested.length === 0) return () => controller.abort()
    const timer = window.setTimeout(() => {
      Promise.all(requested.map(async (layer) => {
        const release = releases[layer.product]
        return assertVersion(await getJson<FeaturesResponse>(`/features?${versionQuery(release, mode, { layer: layer.id, bbox: bounds.join(',') })}`, controller.signal), release, mode)
      })).then((payloads) => {
        if (token !== epoch.current || controller.signal.aborted) return
        setFeatures({ type: 'FeatureCollection', features: payloads.flatMap((payload) => payload.features) })
        setTruncated(payloads.some((payload) => payload.truncated))
      }).catch((reason: unknown) => { if (token === epoch.current && !controller.signal.aborted) fail(reason) })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [releases, layers, bounds, mode, fail])

  const search = async (event: React.FormEvent) => {
    event.preventDefault()
    const text = query.trim()
    const token = ++searchEpoch.current
    setResults([])
    if (!text) { setSearchState('请输入机场标识或名称。'); return }
    const available = [releases.nasr, releases.cifp, releases.dtpp].filter((item): item is Release => Boolean(item))
    if (!available.length) { setSearchState('所选版本没有可搜索的资料。'); return }
    setSearchState('正在搜索…')
    try {
      const payloads = await Promise.all(available.map(async (release) => {
        const payload = assertVersion(await getJson<Envelope>(`/search?${versionQuery(release, mode, { q: text })}`), release, mode)
        return payload.items.map((record) => ({ ...record, release_id: release.id, product_id: release.product_id }))
      }))
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

  const selectResult = async (record: SearchResult) => {
    clearResearch()
    const token = researchEpoch.current
    setSelected(record); setResults([]); setSearchState('')
    if (record.geometry?.type === 'Point') setFocus(record.geometry.coordinates.slice(0, 2) as [number, number])
    if (record.kind === 'procedure') { await selectProcedure(record); return }
    if (record.kind !== 'airport') return
    const cifp = releases.cifp
    const dtpp = releases.dtpp
    const icao = record.product_id === 'cifp' ? record.identifier : String(record.properties.icao_id ?? '')
    const faa = ['nasr', 'dtpp'].includes(record.product_id) ? record.identifier : String(record.properties.faa_id ?? '')
    const requests: Promise<void>[] = []
    if (cifp && icao) {
      setResearchLoading(true)
      requests.push(getJson<Envelope>(`/airports/${encodeURIComponent(icao)}/procedures?${versionQuery(cifp, mode)}`).then((payload) => {
        assertVersion(payload, cifp, mode)
        if (token !== researchEpoch.current) return
        setProcedures(payload.items); setResearchLoading(false)
        if (!payload.items.length) setResearchMessage('此版本没有该机场的已支持程序记录；航图目录覆盖独立显示。')
      }))
    } else setResearchMessage(cifp ? '该机场没有已确认的 ICAO 标识，无法关联 CIFP 程序。' : '尚无所选版本的 CIFP 矢量资料。')
    if (dtpp && faa) {
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

  const hasReleases = Object.keys(releases).length > 0
  return <main className="app-shell">
    <AviationMap features={features} procedure={geometry ?? EMPTY_MAP} focus={focus} onBounds={setBounds} onFeature={(properties) => {
      const release = Object.values(releases).find((item) => item.id === properties.release_id)
      if (!release || typeof properties.id !== 'string') return
      const feature = features.features.find((item) => item.properties?.id === properties.id)
      if (!feature?.properties) return
      const p = feature.properties
      void selectResult({ id: p.id, kind: p.kind, name: p.name, identifier: p.identifier, airport_id: p.airport_id, airport_ident: p.airport_ident,
        parent_id: null, branch_id: null, sequence: null, geometry: feature.geometry, properties: p, provenance: p.provenance,
        release_id: release.id, product_id: release.product_id })
    }} />
    <header className="topbar glass-panel">
      <div className="brand-mark" aria-hidden="true"><span className="brand-wing">◢</span></div>
      <div className="brand-copy"><strong>FLIGHT MAP</strong><span>航空资料研究平台</span></div>
      <form className="search-box" onSubmit={(event) => void search(event)}><span aria-hidden="true">⌕</span>
        <input value={query} onChange={(event) => { setQuery(event.target.value); setResults([]); setSearchState(''); searchEpoch.current += 1 }} placeholder="搜索机场、航点、航路或程序" aria-label="搜索机场、航点、航路或程序" />
        <button type="submit">搜索</button>
      </form>
      <div className={`connection-state ${connection}`}><i />{connection === 'online' ? 'API 已连接' : connection === 'loading' ? '正在连接' : 'API 未连接'}</div>
    </header>
    <aside className="left-panel glass-panel" aria-label="资料版本与图层">
      <section><div className="section-heading"><span>资料版本</span><button className="text-button" onClick={() => void refresh(true)}>重新检查</button></div>
        <div className="mode-tabs">{(['current', 'preview', 'history'] as const).map((item) => <button key={item} className={mode === item ? 'active' : ''} aria-pressed={mode === item} onClick={() => { if (mode !== item) { clearData(); setMode(item); setSelection({}) } }}>{MODE_NAMES[item]}</button>)}</div>
        {mode !== 'current' && <p className="inline-notice">{MODE_NAMES[mode]} · 需显式选择每个产品的版本。</p>}
        {PRODUCTS.map((product) => <div className="release-row" key={product}>
          <label className="field-label">{PRODUCT_NAMES[product]}
            {mode === 'current' ? <span className="current-release">{releases[product] ? `${releases[product].airac} · ${releases[product].id.slice(-8)}` : '无当前发布'}</span> :
              <select aria-label={`${PRODUCT_NAMES[product]}版本`} value={selection[product] ?? ''} onChange={(event) => { clearData(); setSelection({ ...selection, [product]: event.target.value }) }}>
                <option value="">未选择</option>{status?.releases.filter((item) => item.product_id === product && item.state === mode).map((item) => <option key={item.id} value={item.id}>{item.airac} · {item.id.slice(-8)}</option>)}
              </select>}
          </label>
          {releases[product] && <><small className="version-caption">至 {utc(releases[product].valid_to)}</small><button className="text-button" onClick={() => void showReport(releases[product])}>验证报告 ↗</button></>}
        </div>)}
      </section>
      <section><div className="section-heading"><span>数据图层</span><small>{features.features.length} 个要素</small></div>
        <div className="layer-list">{LAYERS.map((layer) => {
          const available = Boolean(releases[layer.product]?.capabilities.includes(layer.id))
          return <label key={layer.id} className={`layer-row ${available ? '' : 'disabled'}`}><input type="checkbox" checked={available && layers.includes(layer.id)} disabled={!available} onChange={(event) => setLayers(event.target.checked ? [...layers, layer.id] : layers.filter((id) => id !== layer.id))} /><span>{layer.name}</span><small>{available ? '可用' : '未支持'}</small></label>
        })}</div>
        <p className="muted-copy">选中程序分支后，地图单独显示该分支的名义几何。</p>
      </section>
      <section><div className="section-heading"><span>产品覆盖</span></div>
        {coverage.map((row) => <div className="coverage-item" key={row.product_id}><b>{PRODUCT_NAMES[row.product_id] ?? row.name}</b><span>{COVERAGE_NAMES[row.status] ?? row.status}</span>
          {row.note && <><p>{coverageSummary(row.note)}</p>{coverageSummary(row.note) !== row.note && <details><summary>查看获取记录</summary><p>{row.note}</p></details>}</>}
          {row.last_successful_release && <>
            <p>最近验证通过 {row.last_successful_release.airac} · {row.last_successful_release.id}</p>
            <p className="version-caption">有效期 {utc(row.last_successful_release.valid_from)} — {utc(row.last_successful_release.valid_to)}</p>
          </>}
          {row.notices_url && <p><a href={row.notices_url} target="_blank" rel="noopener noreferrer">官方更正公告 ↗</a></p>}
        </div>)}
        {!coverage.length && <p className="muted-copy">等待 API 提供覆盖状态。</p>}
      </section>
      <section><div className="section-heading"><span>官方来源与使用依据</span></div>
        {sources.flatMap((source) => source.products.map((product) => <details className="source-detail" key={`${source.id}:${product.id}`}><summary>{product.name}</summary>
          <a href={product.landing_page} target="_blank" rel="noopener noreferrer">官方产品页 ↗</a>
          <p>{product.notes}</p><p>本地获取：{product.local_access?.acquisition ?? 'unknown'} · 处理：{product.local_access?.processing ?? 'unknown'}</p><p>{product.redistribution}</p>
          {product.local_access?.evidence.map((evidence) => <p key={evidence}>{evidence}</p>)}
        </details>))}
      </section>
    </aside>
    {(error || searchState) && <div className="floating-message glass-panel" role="status">{error || searchState}{error && <button className="text-button" onClick={() => void refresh(true)}>重试</button>}</div>}
    {results.length > 0 && <div className="search-results glass-panel" aria-label="搜索结果">{results.map((item) => <button key={`${item.release_id}:${item.id}`} onClick={() => void selectResult(item)}><strong>{item.identifier || item.name}</strong><span>{item.name}</span><small>{item.kind} · {item.product_id.toUpperCase()}</small></button>)}</div>}
    {!hasReleases && !selected && <section className="empty-state glass-panel">
      <div className="radar-icon" aria-hidden="true"><i /><i /></div><span className="eyebrow">FAA RESEARCH</span>
      <h1>{connection === 'loading' ? '正在检查资料版本' : mode === 'current' ? '尚无已验证的当前资料' : '请选择资料版本'}</h1>
      <p>{mode === 'current' ? '地图仅显示参考网格。导入官方资料、检查验证报告并显式发布后，便可开始研究。' : '在左侧为各产品选择版本。预览和历史资料始终保留版本标识。'}</p>
    </section>}
    {hasReleases && !features.features.length && !error && <div className="map-caption">当前视野内没有已启用图层要素 · 可搜索定位</div>}
    {truncated && <div className="map-caption">要素数量已达查询上限，请放大地图查看完整局部资料。</div>}
    <ResearchPanel selected={selected} release={selected ? releases[selected.product_id] : undefined} procedureRelease={releases.cifp} procedures={procedures} detail={detail} branch={branch} geometry={geometry}
      charts={procedureChosen && !sameChartCycle(releases.cifp, releases.dtpp) ? [] : charts} chartRelease={releases.dtpp} chartMessage={chartMessage} loading={researchLoading} chartsLoading={chartsLoading} message={researchMessage}
      onProcedure={(record) => void selectProcedure(record)} onBranch={(id) => void selectBranch(id)} onClose={clearResearch} />
    {report && <div className="report-backdrop"><section className="report-modal glass-panel" role="dialog" aria-modal="true" aria-label="验证报告">
      <div className="section-heading"><span>验证报告 · {report.release.product_id.toUpperCase()}</span><button onClick={() => setReport(null)}>关闭报告</button></div>
      <h2>{report.release.airac}</h2><p className="version-caption">{report.release.id}</p><p>{utc(report.release.valid_from)} — {utc(report.release.valid_to)}</p>
      <div className="report-counts">{Object.entries({ 输入: report.report.input_count, 成功: report.report.success_count, 不支持: report.report.unsupported_count, 错误: report.report.error_count }).map(([label, value]) => <div key={label}><strong>{value}</strong><span>{label}</span></div>)}</div>
      <ul>{report.report.issues.map((issue, index) => <li key={`${issue.code}:${index}`}><b>{issue.severity} · {issue.code}</b> {issue.message}</li>)}</ul>
      <details><summary>周期差异报告</summary><pre>{JSON.stringify(report.diff, null, 2)}</pre></details>
      <details><summary>产品有效期依据</summary>{report.release.validity_evidence.map((evidence) => <p key={evidence}>{evidence}</p>)}</details>
    </section></div>}
    <footer className="statusbar glass-panel"><div><span className="status-dot" /><b>{MODE_NAMES[mode]}</b></div><div>发布 <b>{status?.publication_state ?? 'UNKNOWN'}</b></div><div>AIRAC 日历 <b>{status?.airac.identifier ?? '----'}</b></div><div className="status-spacer" /><div>仅供研究 · 原件可追溯</div><div>UTC <b>{status ? new Date(status.current_time).toISOString().slice(11, 16) : '--:--'}</b></div></footer>
  </main>
}

export default App
