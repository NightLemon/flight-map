import { useEffect, useRef, useState } from 'react'
import type { Release, ResearchRecord } from './api'
import { officialPdfUrl, utc } from './session'

type Props = { charts: ResearchRecord[]; release: Release | undefined; loading: boolean; message: string }

export function ChartPanel(props: Props) {
  return <ChartViewer key={`${props.release?.id ?? ''}:${props.charts.map((chart) => chart.id).join('|')}`} {...props} />
}

function ChartViewer({ charts, release, loading, message }: Props) {
  const [category, setCategory] = useState('')
  const [chartId, setChartId] = useState('')
  const [previewState, setPreviewState] = useState<'loading' | 'ready' | 'failed' | 'uncertain'>('loading')
  const previewRef = useRef<HTMLDivElement>(null)
  const selected = charts.find((chart) => chart.id === chartId)
  const url = officialPdfUrl(selected?.properties.pdf_url)
  const categories = [...new Set(charts.map((chart) => String(chart.properties.chart_code ?? '其他')))].sort()

  useEffect(() => {
    if (!url) return
    previewRef.current?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
    const timer = window.setTimeout(() => setPreviewState((state) => state === 'loading' ? 'uncertain' : state), 12000)
    return () => window.clearTimeout(timer)
  }, [url])

  return <section className="chart-panel" aria-label="官方航图">
    <div className="section-heading"><span>官方航图目录</span><small>{charts.length} 张</small></div>
    {release && <p className="version-caption">{release.airac} · {utc(release.valid_to)} 截止</p>}
    {message && <p className="inline-notice">{message}</p>}
    {loading && <p role="status">正在读取航图目录…</p>}
    {!loading && charts.length === 0 && !message && <p className="muted-copy">该机场没有此版本的航图目录记录。</p>}
    {charts.length > 0 && <>
      <label className="field-label">航图类别
        <select aria-label="航图类别" value={category} onChange={(event) => { setCategory(event.target.value); setChartId('') }}>
          <option value="">全部类别</option>
          {categories.map((code) => <option key={code} value={code}>{code}</option>)}
        </select>
      </label>
      <div className="choice-list chart-list">
        {charts.filter((chart) => !category || String(chart.properties.chart_code ?? '其他') === category).map((chart) =>
          <button className={chart.id === chartId ? 'choice selected' : 'choice'} key={chart.id} onClick={() => { setChartId(chart.id); setPreviewState('loading') }}>
            <small>{String(chart.properties.chart_code ?? '')}</small><span>{chart.name}</span>
          </button>)}
      </div>
    </>}
    {selected && <div className="pdf-panel" ref={previewRef}>
      <div className="section-heading"><span>{selected.name}</span><button className="text-button" onClick={() => setChartId('')}>关闭预览</button></div>
      {url ? <>
        <a className="official-link" href={url} target="_blank" rel="noopener noreferrer">在 FAA 官方网站新窗口打开 ↗</a>
        <p className="muted-copy">浏览器可能限制 PDF 嵌入；若画面空白或显示错误，请使用上方官方链接。</p>
        {previewState === 'loading' && <p className="version-caption" role="status">正在加载 PDF…</p>}
        {(previewState === 'failed' || previewState === 'uncertain') && <p className="inline-notice" role="status">PDF 预览未能确认显示。请在官方新窗口查看。</p>}
        {previewState !== 'failed' && <iframe key={url} title={`官方航图 ${selected.name}`} src={url}
          onLoad={() => setPreviewState('ready')} onErrorCapture={() => setPreviewState('failed')} />}
        {previewState !== 'failed' && <button className="text-button" onClick={() => setPreviewState('failed')}>预览无法显示</button>}
      </> : <p className="inline-notice">此记录没有可用的 FAA 官方 PDF 地址。</p>}
    </div>}
  </section>
}
