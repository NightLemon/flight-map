import { useEffect, useRef, useState } from 'react'
import {
  Map as MapLibreMap,
  NavigationControl,
  ScaleControl,
  setWorkerUrl,
  type StyleSpecification,
} from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import 'maplibre-gl/dist/maplibre-gl.css'
import './App.css'

setWorkerUrl(workerUrl)

type ApiStatus = {
  current_time: string
  airac: {
    identifier: string
    valid_from: string
    valid_to: string
  }
  verified_release_available: boolean
  publication_state: string
  disclaimer: string
}

type GridFeature = {
  type: 'Feature'
  properties: Record<string, never>
  geometry: { type: 'LineString'; coordinates: number[][] }
}

const emptyStyle: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [
    {
      id: 'night-background',
      type: 'background',
      paint: { 'background-color': '#07111c' },
    },
  ],
}

function createReferenceGrid() {
  const features: GridFeature[] = []
  for (let longitude = -180; longitude <= 180; longitude += 30) {
    features.push({
      type: 'Feature',
      properties: {},
      geometry: {
        type: 'LineString',
        coordinates: Array.from({ length: 121 }, (_, index) => [
          longitude,
          -60 + index,
        ]),
      },
    })
  }
  for (let latitude = -60; latitude <= 60; latitude += 20) {
    features.push({
      type: 'Feature',
      properties: {},
      geometry: {
        type: 'LineString',
        coordinates: Array.from({ length: 361 }, (_, index) => [
          -180 + index,
          latitude,
        ]),
      },
    })
  }
  return { type: 'FeatureCollection' as const, features }
}

function AviationMap() {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const map = new MapLibreMap({
      container: containerRef.current,
      style: emptyStyle,
      center: [-98, 39],
      zoom: 3.25,
      minZoom: 1.5,
      maxZoom: 12,
      attributionControl: false,
    })

    map.addControl(new NavigationControl({ showCompass: true }), 'bottom-right')
    map.addControl(new ScaleControl({ unit: 'nautical' }), 'bottom-left')
    map.on('load', () => {
      map.addSource('reference-grid', {
        type: 'geojson',
        data: createReferenceGrid(),
      })
      map.addLayer({
        id: 'reference-grid-lines',
        type: 'line',
        source: 'reference-grid',
        paint: {
          'line-color': '#28506a',
          'line-width': 0.65,
          'line-opacity': 0.38,
        },
      })
    })

    return () => map.remove()
  }, [])

  return <div ref={containerRef} className="map-canvas" aria-label="航空资料地图" />
}

function App() {
  const [status, setStatus] = useState<ApiStatus | null>(null)
  const [apiState, setApiState] = useState<'loading' | 'online' | 'offline'>('loading')
  const [query, setQuery] = useState('')
  const [searchMessage, setSearchMessage] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    const baseUrl = import.meta.env.VITE_API_BASE_URL ?? ''
    fetch(`${baseUrl}/api/v1/status`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error('API unavailable')
        return response.json() as Promise<ApiStatus>
      })
      .then((payload) => {
        setStatus(payload)
        setApiState('online')
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setApiState('offline')
      })
    return () => controller.abort()
  }, [])

  const handleSearch = (event: React.FormEvent) => {
    event.preventDefault()
    if (!query.trim()) return
    setSearchMessage('尚无已验证发布集，搜索不会返回未经核验的数据。')
  }

  return (
    <main className="app-shell">
      <AviationMap />

      <header className="topbar glass-panel">
        <div className="brand-mark" aria-hidden="true">
          <span className="brand-wing">◢</span>
        </div>
        <div className="brand-copy">
          <strong>FLIGHT MAP</strong>
          <span>航空资料研究平台</span>
        </div>
        <form className="search-box" onSubmit={handleSearch}>
          <span aria-hidden="true">⌕</span>
          <input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value)
              setSearchMessage('')
            }}
            placeholder="搜索机场 ICAO、航点或航路"
            aria-label="搜索机场、航点或航路"
          />
          <kbd>Enter</kbd>
        </form>
        <div className={`connection-state ${apiState}`}>
          <i />
          {apiState === 'online' ? 'API 已连接' : apiState === 'loading' ? '正在连接' : 'API 未连接'}
        </div>
      </header>

      <aside className="left-panel glass-panel">
        <section>
          <div className="section-heading">
            <span>数据图层</span>
            <small>0 / 5 可用</small>
          </div>
          <div className="layer-list">
            {[
              ['机场与跑道', 'Airport'],
              ['导航台与航点', 'Navaid / Fix'],
              ['高低空航路', 'Airways'],
              ['SID / STAR', 'Procedures'],
              ['进近程序', 'Approaches'],
            ].map(([label, detail]) => (
              <div className="layer-row disabled" key={label}>
                <span className="layer-symbol" />
                <span><b>{label}</b><small>{detail}</small></span>
                <span className="locked">—</span>
              </div>
            ))}
          </div>
        </section>

        <section className="coverage-section">
          <div className="section-heading"><span>覆盖状态</span></div>
          <div className="coverage-card">
            <div className="coverage-country"><span>US</span><b>美国 · FAA</b></div>
            <span className="status-pill pending">等待导入</span>
          </div>
          <p className="muted-copy">来源已登记。只有通过许可与质量门禁的当前数据才会出现在地图上。</p>
        </section>

        <section className="trust-legend">
          <div className="section-heading"><span>资料可信度</span></div>
          <div><i className="grade-a" /> A · 官方当前</div>
          <div><i className="grade-b" /> B · 官方仅链接</div>
          <div><i className="grade-d" /> D · 社区参考</div>
        </section>
      </aside>

      <section className="empty-state glass-panel">
        <div className="radar-icon" aria-hidden="true"><i /><i /></div>
        <span className="eyebrow">FAIL-CLOSED</span>
        <h1>尚无已验证的航空资料</h1>
        <p>地图目前仅显示地理参考网格。系统不会用示例或推测数据填充真实航路。</p>
        {searchMessage && <div className="search-message">{searchMessage}</div>}
      </section>

      <aside className="right-panel glass-panel">
        <div className="panel-accent" />
        <span className="eyebrow">DATA INTEGRITY</span>
        <h2>为何地图是空的？</h2>
        <p>Flight Map 默认拒绝展示未核验、已过期或许可不明确的数据。</p>
        <ul className="integrity-list">
          <li><span>01</span><div><b>来源可追溯</b><small>保留官方 URL、原件哈希与解析器版本</small></div></li>
          <li><span>02</span><div><b>AIRAC 有效期</b><small>Preview 不进入 Current，过期自动下线</small></div></li>
          <li><span>03</span><div><b>绝不猜测几何</b><small>未知程序腿不会退化成航点连线</small></div></li>
        </ul>
        <div className="scope-notice">
          <span>!</span>
          <p><b>非运行用途</b><br />不得用于航空器导航、签派放行或替代官方飞行前简报。</p>
        </div>
      </aside>

      <footer className="statusbar glass-panel">
        <div><span className="status-dot" />发布状态 <b>EMPTY</b></div>
        <div>AIRAC <b>{status?.airac.identifier ?? '----'}</b></div>
        <div>有效起点 <b>{status ? new Date(status.airac.valid_from).toLocaleDateString('zh-CN') : '等待 API'}</b></div>
        <div className="status-spacer" />
        <div>参考网格 · 不含航空资料</div>
        <div>UTC <b>{status ? new Date(status.current_time).toISOString().slice(11, 16) : '--:--'}</b></div>
      </footer>
    </main>
  )
}

export default App
