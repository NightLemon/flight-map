import type { ResearchRecord } from './api'
import './AirportCommunications.css'

type Props = { items: ResearchRecord[]; loading: boolean; message: string }
const SERVICES: Record<string, string> = { 'LCL/P': '塔台', 'GND/P': '地面', 'CD/P': '放行许可', ATIS: '自动终端情报', 'D-ATIS': '数字终端情报', CTAF: '通用交通咨询', UNICOM: '机场咨询', 'APCH/P DEP/P': '进近 / 离场', 'APCH/P': '进近', 'DEP/P': '离场' }
const SERVICE_ORDER = ['D-ATIS', 'ATIS', 'LCL/P', 'GND/P', 'CD/P', 'CTAF', 'UNICOM', 'APCH/P DEP/P', 'APCH/P', 'DEP/P']

function textProperty(record: ResearchRecord, key: string) {
  const value = record.properties[key]
  return typeof value === 'string' ? value : ''
}

export function AirportCommunications({ items, loading, message }: Props) {
  const ordered = [...items].sort((a, b) => {
    const rank = (r: ResearchRecord) => { const index = SERVICE_ORDER.indexOf(textProperty(r, 'service')); return index < 0 ? SERVICE_ORDER.length : index }
    return rank(a) - rank(b)
  })
  return <section className="airport-communications" aria-label="机场通信频率">
    <div className="section-heading">
      <h2>常用通信频率</h2><small>{items.length} 项</small>
    </div>
    {message && <p className="communication-message" role="status">{message}</p>}
    {loading && <p className="muted-copy" role="status">正在读取常用通信频率…</p>}
    {!loading && !message && items.length === 0 && <p className="muted-copy">该机场没有可显示的常用通信频率。</p>}
    {items.length > 0 && <div className="communication-list">
      {ordered.map((record) => {
        const service = textProperty(record, 'service')
        const frequency = textProperty(record, 'frequency')
        const unit = textProperty(record, 'unit')
        const remarks = textProperty(record, 'remarks')
        const sector = textProperty(record, 'sectorization')
        const raw = record.properties.raw_fields as Record<string, string> | undefined
        const call = raw?.TOWER_OR_COMM_CALL || raw?.PRIMARY_APPROACH_RADIO_CALL
        return <article className="communication-item" key={record.id}>
          <div className="communication-primary">
            <p className="communication-service">{SERVICES[service] && <span>{SERVICES[service]} · </span>}{service}</p>
            <p className="communication-frequency">{frequency}{unit && ` ${unit}`}{record.properties.receive_only === true && <span> · 仅接收 (R)</span>}</p>
          </div>
          {remarks && <p className="communication-remarks"><span>说明</span>{remarks}</p>}
          {sector && <p className="communication-remarks"><span>扇区</span>{sector}</p>}
          {call && <p className="communication-remarks"><span>呼号</span>{call}</p>}
          <details className="communication-source">
            <summary>来源详情</summary>
            <dl>
              <dt>ZIP 成员</dt><dd>{record.provenance.member ?? '—'}</dd>
              <dt>行号</dt><dd>{record.provenance.line ?? '—'}</dd>
              <dt>定位信息</dt><dd>{record.provenance.locator}</dd>
              <dt>原件 SHA-256</dt><dd>{record.provenance.asset_sha256}</dd>
            </dl>
            {raw && <pre>{JSON.stringify(raw, null, 2)}</pre>}
          </details>
        </article>
      })}
    </div>}
  </section>
}
