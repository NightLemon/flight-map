import type { Geometry } from 'geojson'
import { AirportCommunications } from './AirportCommunications'
import type { ResearchRecord } from './api'
import type { AirportDetail, ReviewNote } from './public-data'
import './PublicAirportDetails.css'

function stringValue(value: unknown) { return typeof value === 'string' || typeof value === 'number' ? String(value).trim() : '' }
function value(record: ResearchRecord, key: string) { return stringValue(record.properties[key]) }
function displayDate(date: string | undefined) { return date ? date.slice(0, 10) : '未提供' }

function safeHttpUrl(value: unknown): string | null {
  if (typeof value !== 'string' || !value.trim()) return null
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null
  } catch { return null }
}

function feetAndMeters(raw: string, label: string) {
  const feet = Number(raw)
  if (!raw || !Number.isFinite(feet)) return `${label}：来源未提供`
  const metres = feet * 0.3048
  return `${label}：${metres.toFixed(1)} m（${raw} ft，换算值）`
}

function Overview({ airport }: { airport: ResearchRecord }) {
  const properties = airport.properties
  const website = safeHttpUrl(properties.home_link)
  const facts = [
    ['类型', stringValue(properties.type)], ['城市', stringValue(properties.municipality) || stringValue(properties.city)],
    ['海拔', feetAndMeters(stringValue(properties.elevation_ft), '海拔').replace('海拔：', '')],
    ['ICAO', stringValue(properties.icao_id)], ['IATA', stringValue(properties.iata_code)],
    ['GPS', stringValue(properties.gps_code)], ['本地代码', stringValue(properties.local_code)],
  ].filter(([, item]) => item)
  return <section className="public-airport-overview" aria-label="机场概览">
    <div className="section-heading"><span>机场概览</span></div>
    <dl>{facts.map(([label, item]) => <div key={label}><dt>{label}</dt><dd>{item}</dd></div>)}</dl>
    {website && <a className="official-link" href={website} target="_blank" rel="noopener noreferrer">机场官网 ↗</a>}
  </section>
}

function hasCompleteRunwayGeometry(geometry: Geometry | null) {
  const hasEndpoints = (coordinates: number[][]) => coordinates.length >= 2 && [coordinates[0], coordinates.at(-1)!]
    .every((position) => position.length >= 2 && Number.isFinite(position[0]) && Number.isFinite(position[1]))
  return geometry?.type === 'LineString' ? hasEndpoints(geometry.coordinates) : geometry?.type === 'MultiLineString'
    && geometry.coordinates.some((line) => hasEndpoints(line))
}

function RunwayCard({ runway, closed = false }: { runway: ResearchRecord; closed?: boolean }) {
  const le = value(runway, 'le_ident') || '来源未提供'
  const he = value(runway, 'he_ident') || '来源未提供'
  const surface = value(runway, 'surface') || '来源未提供'
  const lighted = value(runway, 'lighted')
  const lights = lighted === '1' ? '有灯光（来源标记）' : lighted === '0' ? '无灯光（来源标记）' : '来源未提供'
  return <article className="public-runway-card">
    <div className="public-runway-heading"><b>起点 {le} · 终点 {he}</b>{closed && <span>来源标为关闭</span>}</div>
    <p>{feetAndMeters(value(runway, 'length_ft'), '长度')}</p>
    <p>{feetAndMeters(value(runway, 'width_ft'), '宽度')}</p>
    <p>表面：{surface}</p><p>灯光：{lights}</p>
    {!hasCompleteRunwayGeometry(runway.geometry) && <p className="public-detail-warning">来源未提供完整地图端点</p>}
  </article>
}

function Runways({ items }: { items: ResearchRecord[] }) {
  if (!items.length) return <section className="public-runways" aria-label="跑道"><div className="section-heading"><span>跑道</span></div><p className="muted-copy">来源未收录跑道记录</p></section>
  const closed = items.filter((item) => value(item, 'closed') === '1')
  const regular = items.filter((item) => value(item, 'closed') !== '1')
  return <section className="public-runways" aria-label="跑道">
    <div className="section-heading"><span>跑道</span><small>{items.length} 条来源记录</small></div>
    {regular.length > 0 && <div className="public-runway-list">{regular.map((runway) => <RunwayCard key={runway.id} runway={runway} />)}</div>}
    {closed.length > 0 && <details className="public-closed-runways"><summary>来源标为关闭 <small>{closed.length} 条</small></summary><div className="public-runway-list">{closed.map((runway) => <RunwayCard key={runway.id} runway={runway} closed />)}</div></details>}
  </section>
}

function Integrity({ detail }: { detail: AirportDetail }) {
  const frequencies = detail.communications.length + (detail.navigation_frequencies?.length ?? 0) + (detail.unclassified_frequencies?.length ?? 0)
  const missingGeometry = detail.runways.filter((runway) => !hasCompleteRunwayGeometry(runway.geometry)).length
  const closed = detail.runways.filter((runway) => value(runway, 'closed') === '1').length
  const notices = [
    ...(frequencies ? ['频率记录尚未逐项按官方资料核实，不能用作运行或导航依据。'] : ['来源未收录频率。']),
    ...(detail.runways.length ? missingGeometry ? [`${missingGeometry} 条跑道来源未提供完整地图端点。`] : [] : ['来源未收录跑道记录。']),
    ...(closed ? [`${closed} 条跑道仅按来源标记为关闭；该标记不替代当天 NOTAM。`] : []),
  ]
  return <section className="public-integrity" aria-label="资料完整性"><details>
    <summary>资料完整性 <small>{notices.length} 项提示</small></summary>
    <ul>{notices.map((notice) => <li key={notice}>{notice}</li>)}</ul>
  </details></section>
}

function ReviewNotes({ notes }: { notes: ReviewNote[] | undefined }) {
  if (!notes?.length) return null
  const fieldLabel = (field: string) => ({ name: '机场名称', 'properties.length_ft': '跑道长度', 'properties.scheduled_service': '定期服务标记' }[field] ?? '来源字段')
  return <section className="public-review-notes" aria-label="资料核查记录">
    <details><summary>资料核查记录 <small>{notes.length} 项</small></summary><div className="public-review-list">{notes.map((note) => <article key={note.id}>
      <p><b>{note.status === 'corrected' ? '已勘误' : '待核查'}</b> · {fieldLabel(note.field)}</p><p>{note.message}</p>
      <dl><div><dt>来源原值</dt><dd>{note.original_value}</dd></div>
        {note.status === 'corrected' && note.value !== undefined && <div><dt>修正值</dt><dd>{note.value}</dd></div>}
        <div><dt>核查日期</dt><dd>{displayDate(note.reviewed_at)}</dd></div><div><dt>记录</dt><dd>{note.record_id}</dd></div></dl>
      {note.evidence.length > 0 && <ul>{note.evidence.map((evidence) => {
        const href = safeHttpUrl(evidence.url)
        return <li key={`${evidence.title}:${evidence.url}`}>{href ? <a href={href} target="_blank" rel="noopener noreferrer">{evidence.title} ↗</a> : <span>{evidence.title}（来源链接不可用）</span>}{evidence.published_at && ` · 发布：${displayDate(evidence.published_at)}`}</li>
      })}</ul>}
    </article>)}</div></details>
  </section>
}

export function PublicAirportDetails({ detail }: { detail: AirportDetail }) {
  return <>
    <Overview airport={detail.airport} />
    <AirportCommunications items={detail.communications} loading={false} message="" title="语音通信频率" ariaLabel="机场通信频率" emptyMessage="来源未收录语音通信频率" />
    <div className="public-frequency-reference"><AirportCommunications items={detail.navigation_frequencies ?? []} loading={false} message="" title="导航频率参考" ariaLabel="导航频率参考" emptyMessage="来源未收录导航频率参考" /><p className="muted-copy">这些是来源中的调谐值参考，不是语音通信频率。</p></div>
    <AirportCommunications items={detail.unclassified_frequencies ?? []} loading={false} message="" title="未分类频率" ariaLabel="未分类频率" emptyMessage="来源未收录未分类频率" />
    <Runways items={detail.runways} />
    <Integrity detail={detail} />
    <ReviewNotes notes={detail.review_notes} />
  </>
}
