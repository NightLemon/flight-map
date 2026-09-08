import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent } from 'react'
import type { GeoJsonProperties } from 'geojson'
import { AirportCommunications } from './AirportCommunications'
import { AviationMap } from './AviationMap'
import { EMPTY_MAP, type MapData, type MapViewport } from './map-data'
import {
  loadPublicAirport, loadPublicFeatures, loadPublicManifest, searchPublicAirports,
  type AirportDetail, type AirportHit, type PublicLayer, type PublicManifest,
} from './public-data'
import type { ResearchRecord } from './api'
import { WorkspaceSplitter } from './WorkspaceSplitter'
import './PublicApp.css'

const LAYERS: Array<{ id: PublicLayer; name: string; minZoom: number }> = [
  { id: 'airports', name: '机场', minZoom: 8 },
  { id: 'runways', name: '跑道', minZoom: 10 },
  { id: 'navaids', name: '导航台', minZoom: 6 },
]

function message(error: unknown) { return error instanceof Error ? error.message : '无法读取公开资料。' }
function isAbort(error: unknown) { return error instanceof DOMException && error.name === 'AbortError' }
function stringValue(value: unknown) { return typeof value === 'string' || typeof value === 'number' ? String(value) : '' }
function displayDate(value: string) { return value ? value.slice(0, 10) : '未提供' }
function isOlderThan30Days(value: string) {
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) && Date.now() - timestamp > 30 * 24 * 60 * 60 * 1000
}

function airportFromProperties(properties: NonNullable<GeoJsonProperties>, coordinates: [number, number]): AirportHit | null {
  if (typeof properties.id !== 'string' || typeof properties.identifier !== 'string') return null
  return {
    id: properties.id,
    identifier: properties.identifier,
    name: stringValue(properties.name),
    icao_id: stringValue(properties.icao_id),
    iata_code: stringValue(properties.iata_code),
    municipality: stringValue(properties.municipality),
    country: stringValue(properties.country),
    coordinates,
  }
}

function text(record: ResearchRecord, ...keys: string[]) {
  for (const key of keys) {
    const value = stringValue(record.properties[key])
    if (value) return value
  }
  return ''
}

function Runways({ items }: { items: ResearchRecord[] }) {
  if (!items.length) return <p className="muted-copy">该机场没有可显示的跑道记录。</p>
  return <section className="public-runways" aria-label="跑道">
    <div className="section-heading"><span>跑道</span><small>{items.length} 条</small></div>
    <div className="public-runway-list">{items.map((runway) => {
      const length = text(runway, 'length_ft', 'length', 'length_feet')
      const surface = text(runway, 'surface')
      return <article key={runway.id}>
        <b>{runway.identifier || runway.name || '未命名跑道'}</b>
        {(length || surface) && <small>{[length && `${length} ft`, surface].filter(Boolean).join(' · ')}</small>}
      </article>
    })}</div>
  </section>
}

function Properties({ properties }: { properties: NonNullable<GeoJsonProperties> }) {
  const rows = Object.entries(properties).filter(([, value]) => typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean')
  return <section className="public-properties" aria-label="地图要素属性">
    <div className="section-heading"><span>地图要素</span></div>
    <dl>{rows.length ? rows.slice(0, 12).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>) : <p className="muted-copy">该要素没有可显示的属性。</p>}</dl>
  </section>
}

function PublicApp() {
  const [manifest, setManifest] = useState<PublicManifest | null>(null)
  const [manifestError, setManifestError] = useState('')
  const [manifestLoading, setManifestLoading] = useState(true)
  const [layers, setLayers] = useState<PublicLayer[]>(['airports'])
  const [viewport, setViewport] = useState<MapViewport | null>(null)
  const [features, setFeatures] = useState<MapData>(EMPTY_MAP)
  const [mapLoading, setMapLoading] = useState(false)
  const [mapError, setMapError] = useState('')
  const [truncated, setTruncated] = useState(false)
  const [mapRefresh, setMapRefresh] = useState(0)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<AirportHit[]>([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [searchNotice, setSearchNotice] = useState('')
  const [selectedAirport, setSelectedAirport] = useState<AirportHit | null>(null)
  const [detail, setDetail] = useState<AirportDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [selectedFeature, setSelectedFeature] = useState<NonNullable<GeoJsonProperties> | null>(null)
  const [focus, setFocus] = useState<[number, number] | null>(null)
  const [highlight, setHighlight] = useState<[number, number] | null>(null)
  const [deskWidth, setDeskWidth] = useState(380)
  const manifestRequest = useRef<AbortController | null>(null)
  const searchRequest = useRef<AbortController | null>(null)
  const airportRequest = useRef<AbortController | null>(null)
  const airportEpoch = useRef(0)
  const manifestRevision = useRef('')

  const refreshManifest = useCallback(() => {
    manifestRequest.current?.abort()
    const controller = new AbortController()
    manifestRequest.current = controller
    setManifestLoading(true); setManifestError('')
    void loadPublicManifest(controller.signal).then((next) => {
      if (controller.signal.aborted || manifestRequest.current !== controller) return
      if (manifestRevision.current && manifestRevision.current !== next.source.revision) {
        searchRequest.current?.abort(); airportRequest.current?.abort(); airportEpoch.current += 1
        setResults([]); setSearchLoading(false); setSearchError(''); setSearchNotice('')
        setSelectedAirport(null); setSelectedFeature(null); setDetail(null); setDetailError(''); setDetailLoading(false)
        setFeatures(EMPTY_MAP); setFocus(null); setHighlight(null)
      }
      manifestRevision.current = next.source.revision
      setManifest(next)
    }).catch((error: unknown) => {
      if (!controller.signal.aborted && manifestRequest.current === controller && !isAbort(error)) setManifestError(message(error))
    }).finally(() => { if (!controller.signal.aborted && manifestRequest.current === controller) setManifestLoading(false) })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    // Initialize the external static data subscription.
    // eslint-disable-next-line react/set-state-in-effect
    return refreshManifest()
  }, [refreshManifest])
  useEffect(() => () => { manifestRequest.current?.abort(); searchRequest.current?.abort(); airportRequest.current?.abort() }, [])

  useEffect(() => {
    const controller = new AbortController()
    const requested = viewport && manifest ? layers.filter((layer) => viewport.zoom >= LAYERS.find((item) => item.id === layer)!.minZoom) : []
    // The external map subscription invalidates the previous viewport immediately.
    // eslint-disable-next-line react/set-state-in-effect
    setFeatures(EMPTY_MAP); setTruncated(false); setMapError('')
    if (!viewport || !manifest || requested.length === 0) { setMapLoading(false); return () => controller.abort() }
    setMapLoading(true)
    const timer = window.setTimeout(() => {
      void loadPublicFeatures(manifest, requested, viewport, controller.signal).then((next) => {
        if (controller.signal.aborted) return
        setFeatures({ type: 'FeatureCollection', features: next.features })
        setTruncated(next.truncated); setMapLoading(false)
      }).catch((error: unknown) => {
        if (controller.signal.aborted || isAbort(error)) return
        setMapLoading(false); setMapError(message(error))
      })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [layers, manifest, mapRefresh, viewport])

  const chooseAirport = useCallback((airport: AirportHit, moveMap: boolean) => {
    searchRequest.current?.abort(); setSearchLoading(false)
    airportRequest.current?.abort()
    const controller = new AbortController()
    airportRequest.current = controller
    const token = ++airportEpoch.current
    setSelectedAirport(airport); setSelectedFeature(null); setDetail(null); setDetailError(''); setDetailLoading(true); setResults([]); setSearchNotice('')
    setHighlight(airport.coordinates)
    if (moveMap) setFocus([...airport.coordinates])
    void loadPublicAirport(airport.id, controller.signal).then((next) => {
      if (controller.signal.aborted || token !== airportEpoch.current) return
      setDetail(next); setDetailLoading(false)
    }).catch((error: unknown) => {
      if (controller.signal.aborted || token !== airportEpoch.current || isAbort(error)) return
      setDetailLoading(false); setDetailError(message(error))
    })
  }, [])

  const submitSearch = useCallback(async (event?: FormEvent) => {
    event?.preventDefault()
    if (!manifest || manifestLoading) return
    const term = query.trim()
    searchRequest.current?.abort()
    if (!term) { setResults([]); setSearchNotice('请输入机场标识、IATA 代码或城市名称。'); return }
    const controller = new AbortController()
    searchRequest.current = controller
    setSearchLoading(true); setSearchError(''); setSearchNotice('')
    try {
      const found = await searchPublicAirports(term, controller.signal)
      if (controller.signal.aborted) return
      setResults(found); setSearchNotice(found.length ? `${found.length} 条结果` : '没有找到匹配机场。')
    } catch (error) {
      if (!controller.signal.aborted && !isAbort(error)) setSearchError(message(error))
    } finally { if (!controller.signal.aborted) setSearchLoading(false) }
  }, [query, manifest, manifestLoading])

  const dataDate = manifest ? displayDate(manifest.source.updated_at) : '加载中…'
  const airportOverview = Boolean(viewport && layers.includes('airports') && viewport.zoom < 8)
  const sourceAirport = detail?.airport ?? null
  const shownAirport = sourceAirport ?? (selectedAirport ? {
    id: selectedAirport.id, kind: 'airport', name: selectedAirport.name, identifier: selectedAirport.identifier,
    airport_ident: null, airport_id: null, parent_id: null, branch_id: null, sequence: null, geometry: null,
    properties: {}, provenance: { asset_sha256: '', member: null, line: null, locator: '' },
  } satisfies ResearchRecord : null)
  const ourAirportsUrl = selectedAirport?.identifier ? `https://ourairports.com/airports/${encodeURIComponent(selectedAirport.identifier)}/` : ''
  const mapCount = useMemo(() => features.features.length, [features.features.length])

  return <main className="app-shell public-app" aria-label="Flight Map 公开参考版" tabIndex={0} style={{ '--desk-width': `${deskWidth}px` } as CSSProperties}>
    <AviationMap features={features} procedure={EMPTY_MAP} focus={focus} highlight={highlight} onViewport={setViewport} onFeature={(properties) => {
      if (properties.kind === 'airport') {
        const feature = features.features.find((item) => item.properties?.id === properties.id)
        if (feature?.geometry?.type !== 'Point') return
        const coordinates = feature.geometry.coordinates.slice(0, 2) as [number, number]
        if (!coordinates.every(Number.isFinite)) return
        const airport = airportFromProperties(properties, coordinates)
        if (airport) chooseAirport(airport, false)
        return
      }
      airportRequest.current?.abort(); airportEpoch.current += 1
      setDetailLoading(false); setSelectedFeature(properties); setSelectedAirport(null); setDetail(null); setDetailError(''); setFocus(null); setHighlight(null)
    }} />
    <header className="topbar glass-panel">
      <div className="brand-mark" aria-hidden="true"><span className="brand-wing">◢</span></div>
      <div className="brand-copy"><strong>FLIGHT MAP</strong><span>公开参考版 · OurAirports</span></div>
      <form className="search-box" onSubmit={(event) => void submitSearch(event)}><span aria-hidden="true">⌕</span>
        <input value={query} onChange={(event) => { searchRequest.current?.abort(); setSearchLoading(false); setQuery(event.target.value); setResults([]); setSearchError(''); setSearchNotice('') }} placeholder="搜索 KJFK、SEA 或城市" aria-label="搜索机场" />
        <button type="submit" disabled={searchLoading || manifestLoading || !manifest}>{searchLoading ? '搜索中' : '搜索'}</button>
      </form>
      <div className={`connection-state ${manifestError ? 'offline' : manifestLoading ? 'loading' : 'online'}`}><i />{manifestError ? '资料不可用' : manifestLoading ? '读取资料中' : '公开数据快照'}</div>
    </header>
    <aside className="left-panel glass-panel public-left-panel" aria-label="公开资料与图层">
      <details className="data-management">
        <summary><span className="data-date">快照日期 <b>{dataDate}</b></span><span className="data-management-label">数据管理</span></summary>
        <div className="data-management-body">
          <section><div className="section-heading"><span>公开来源</span><button className="text-button" onClick={() => refreshManifest()}>重新读取</button></div>
            {manifest ? <><a href={manifest.source.url} target="_blank" rel="noopener noreferrer">{manifest.source.name} ↗</a>
              <p className="source-detail">许可：<a href={manifest.source.license_url} target="_blank" rel="noopener noreferrer">{manifest.source.license}</a><br />修订：{manifest.source.revision || '未提供'}<br />上游更新时间：{manifest.source.updated_at || '未提供'}</p>
              {isOlderThan30Days(manifest.source.updated_at) && <p className="data-attention">上游快照日期已超过 30 天，请先核对来源更新。</p>}
              <p className="muted-copy">此日期是上游数据快照更新时间，不代表 AIRAC 有效期。</p></> : <p className="muted-copy">{manifestLoading ? '正在读取公开数据清单…' : '清单尚不可用。'}</p>}
          </section>
        </div>
      </details>
      {manifest && isOlderThan30Days(manifest.source.updated_at) && <p className="data-attention">资料快照已超过 30 天，请核对来源更新。</p>}
      <section className="map-layer-controls"><div className="section-heading"><span>数据图层</span><small>{mapCount} 个要素</small></div>
        <div className="layer-list">{LAYERS.map((layer) => <label key={layer.id} className="layer-row"><input type="checkbox" checked={layers.includes(layer.id)} onChange={(event) => setLayers(event.target.checked ? [...layers, layer.id] : layers.filter((id) => id !== layer.id))} /><i aria-hidden="true" className={`legend-swatch ${layer.id}`} /><span>{layer.name}</span><small>Z{layer.minZoom}</small></label>)}</div>
        <p className="muted-copy">机场、跑道和导航台按当前视野加载；每层最多 500 个要素。</p>
        <p className="muted-copy">FAA 航点、航路和 PDF 核对见<a href="https://github.com/NightLemon/flight-map" target="_blank" rel="noopener noreferrer">完整本机版 ↗</a>。</p>
      </section>
    </aside>
    {manifestError && <div className="public-manifest-error glass-panel" role="status">公开数据清单读取失败：{manifestError}<button className="text-button" onClick={() => refreshManifest()}>重试</button></div>}
    {(searchError || searchNotice) && <div className="floating-message glass-panel" role="status">{searchError || searchNotice}{searchError && <button className="text-button" onClick={() => void submitSearch()}>重试</button>}</div>}
    {results.length > 0 && <div className="search-results glass-panel" aria-label="机场搜索结果">{results.map((airport) => <button key={airport.id} onClick={() => chooseAirport(airport, true)}><strong>{airport.identifier}</strong><span>{airport.name || airport.municipality || '未命名机场'}</span><small>{[airport.municipality, airport.country].filter(Boolean).join(' · ')}</small></button>)}</div>}
    {mapLoading && <div className="map-caption" role="status">正在读取当前视野公开资料…</div>}
    {mapError && <div className="map-error glass-panel" role="status">地图资料读取失败：{mapError} <button className="text-button" onClick={() => setMapRefresh((value) => value + 1)}>重试</button></div>}
    {manifest && airportOverview && !mapLoading && <div className="map-caption">放大至 Z8 查看机场，或直接搜索定位</div>}
    {manifest && viewport && !airportOverview && !features.features.length && !mapLoading && !mapError && <div className="map-caption">当前视野没有可显示的公开要素</div>}
    {truncated && <div className="map-caption public-truncated">当前视野要素较多，请继续放大查看。</div>}
    <WorkspaceSplitter width={deskWidth} onWidth={setDeskWidth} />
    <aside className="right-panel glass-panel public-right-panel" aria-label="机场详情">
      {(shownAirport || selectedFeature) && <button className="text-button public-close" onClick={() => {
        airportRequest.current?.abort(); airportEpoch.current += 1
        setSelectedAirport(null); setSelectedFeature(null); setDetail(null); setDetailError(''); setDetailLoading(false); setFocus(null); setHighlight(null)
      }}>关闭详情</button>}
      <div className="panel-accent" />
      {!shownAirport && !selectedFeature && <><span className="eyebrow">PUBLIC REFERENCE</span><h2>选择一个机场</h2><p>搜索机场或点击地图要素查看公开参考资料。此页不提供运行、导航或放行依据。</p></>}
      {selectedFeature && <Properties properties={selectedFeature} />}
      {shownAirport && <><span className="eyebrow">OURAIRPORTS REFERENCE</span><h2>{shownAirport.identifier || shownAirport.name}</h2><p className="entity-name">{shownAirport.name}{selectedAirport?.municipality && ` · ${selectedAirport.municipality}`}{selectedAirport?.country && ` · ${selectedAirport.country}`}</p>
        {ourAirportsUrl && <a className="official-link" href={ourAirportsUrl} target="_blank" rel="noopener noreferrer">在 OurAirports 查看机场页 ↗</a>}
        {detailLoading && <p className="muted-copy" role="status">正在读取机场、频率和跑道资料…</p>}
        {detailError && <p className="inline-notice" role="status">机场详情读取失败：{detailError} <button className="text-button" onClick={() => selectedAirport && chooseAirport(selectedAirport, false)}>重试</button></p>}
        {detail && <><AirportCommunications items={detail.communications} loading={false} message="" /><Runways items={detail.runways} /></>}
        <section className="scope-notice"><span>!</span><p><b>非运行用途</b><br />公开参考版使用 OurAirports Public Domain 快照；使用前请以适用官方资料和运行程序核对。</p></section>
      </>}
    </aside>
    <footer className="statusbar glass-panel"><div><span className="status-dot" /><b>公开参考 · OurAirports</b></div><div>快照 <b>{dataDate}</b></div><div className="status-spacer" /><div>非运行用途 · 资料需独立核对</div></footer>
  </main>
}

export default PublicApp
