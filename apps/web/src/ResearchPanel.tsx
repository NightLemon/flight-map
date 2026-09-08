import type { GeometryResponse, Mode, Procedure, Release, ResearchRecord, SearchResult, SnapshotStatus } from './api'
import { ChartPanel } from './ChartPanel'
import { utc } from './session'

type Props = {
  selected: SearchResult | null; release: Release | undefined
  snapshot?: SnapshotStatus
  procedureRelease: Release | undefined
  procedures: ResearchRecord[]; detail: Procedure | null; branch: string; geometry: GeometryResponse | null
  charts: ResearchRecord[]; chartRelease: Release | undefined; chartMessage: string
  loading: boolean; chartsLoading: boolean; message: string
  onProcedure: (record: ResearchRecord) => void; onBranch: (branch: string) => void
  onClose: () => void
  mode?: Mode; onInvalid?: (error: unknown) => void
}

export function RecordEvidence({ record, release, snapshot }: { record: ResearchRecord; release?: Release; snapshot?: SnapshotStatus }) {
  const version = snapshot ?? release
  return <details className="evidence">
    <summary>来源、原始字段与有效期</summary>
    <dl>
      <dt>实体 ID</dt><dd>{record.id}</dd>
      <dt>来源</dt><dd>{version?.source_id ?? '—'}</dd>
      <dt>{snapshot ? '研究快照' : '发布'}</dt><dd>{version?.id ?? '—'}</dd>
      <dt>解析器</dt><dd>{version?.parser_version ?? '—'}</dd>
      {snapshot ? <><dt>官方日期 · 精度：日</dt><dd>{snapshot.official_effective_date} · 精确生效时刻未知</dd><dt>日期依据</dt><dd>{snapshot.date_evidence.join('\n')}</dd></> : <><dt>生效</dt><dd>{utc(release?.valid_from)}</dd><dt>截止</dt><dd>{utc(release?.valid_to)}</dd></>}
      <dt>坐标基准</dt><dd>{String(record.properties.coordinate_datum ?? record.properties.datum ?? '未提供')}</dd>
      <dt>原件 SHA-256</dt><dd>{record.provenance.asset_sha256}</dd>
      <dt>ZIP 成员</dt><dd>{record.provenance.member ?? '—'}</dd>
      <dt>原件位置</dt><dd>{record.provenance.locator}{record.provenance.line ? ` · 行 ${record.provenance.line}` : ''}</dd>
    </dl>
    <pre>{JSON.stringify(record.properties, null, 2)}</pre>
  </details>
}

export function ResearchPanel(props: Props) {
  const { selected, release, detail, branch, geometry } = props
  const legs = detail?.legs.filter((leg) => leg.branch_id === branch) ?? []
  const gapById = new Map(geometry?.gaps.map((gap) => [gap.leg_id, gap.reason]) ?? [])
  return <aside className="right-panel glass-panel" aria-label="资料研究面板">
    {!selected ? <>
      <div className="panel-accent" /><span className="eyebrow">RESEARCH DESK</span>
      <h2>从一个机场开始</h2>
      <p className="muted-copy">搜索机场标识或名称，在地图上定位，查看程序记录与官方航图。</p>
      <ol className="research-steps"><li>选择并固定资料版本</li><li>搜索机场、航点或航路</li><li>选择程序分支，核对原始腿与航图</li></ol>
      <div className="scope-notice"><span>!</span><p><b>仅供研究与学习</b><br />不得用于导航、签派放行或替代官方飞行前简报。</p></div>
      <p className="muted-copy">地图线段仅表示有依据的名义几何。资料缺口会明确保留。</p>
    </> : <>
      <div className="section-heading"><span>{selected.kind.toUpperCase()}</span><button className="text-button" onClick={props.onClose}>关闭</button></div>
      <h2>{selected.identifier || selected.name}</h2>
      {selected.identifier && <p className="entity-name">{selected.name}</p>}
      {props.snapshot && <p className="inline-notice">官方日期 {props.snapshot.official_effective_date} · {String(selected.properties.coordinate_datum ?? selected.properties.datum ?? '坐标基准见原字段')}<br />精确生效时刻未知，仅用于日期级研究。</p>}
      <RecordEvidence record={selected} release={release} snapshot={props.snapshot} />
      {props.message && <p role="status" className="inline-notice">{props.message}</p>}
      {props.loading && <p role="status" className="muted-copy">正在读取结构化程序…</p>}
      {props.procedures.length > 0 && <section>
        <div className="section-heading"><span>程序记录</span><small>{props.procedures.length} 条</small></div>
        <div className="choice-list">
          {props.procedures.map((record) => <button key={record.id} className={record.id === detail?.record.id ? 'choice selected' : 'choice'} onClick={() => props.onProcedure(record)}>
            <small>{String(record.properties.procedure_type ?? '程序')}</small><span>{record.name || record.identifier}</span>
          </button>)}
        </div>
      </section>}
      {detail && <section aria-label="程序详情">
        <div className="section-heading"><span>{detail.record.name}</span></div>
        <label className="field-label">程序分支
          <select aria-label="程序分支" value={branch} onChange={(event) => props.onBranch(event.target.value)}>
            <option value="">选择一个分支</option>
            {detail.branches.map((id) => <option key={id} value={id}>{id}</option>)}
          </select>
        </label>
        {branch && <>
          <p className="geometry-notice">{geometry?.notice ?? 'IF / TF 名义几何不包含完整飞行转弯轨迹预测。'}</p>
          {geometry && <p className="version-caption">{geometry.features.length} 个几何要素 · {geometry.gaps.length} 个缺口</p>}
          <div className="leg-list" aria-label="程序腿">
            {legs.map((leg) => <article className={gapById.has(leg.id) ? 'leg has-gap' : 'leg'} key={leg.id}>
              <div className="leg-heading"><span>{leg.sequence ?? '—'}</span><strong>{String(leg.properties.path_terminator ?? '—')}</strong><b>{leg.identifier || leg.name || '未命名腿'}</b></div>
              {gapById.has(leg.id) && <p className="gap-reason">几何缺口 · {gapById.get(leg.id)}</p>}
              <RecordEvidence record={leg} release={props.procedureRelease} />
            </article>)}
          </div>
        </>}
      </section>}
      {(selected.kind === 'airport' || selected.kind === 'procedure') && <ChartPanel charts={props.charts} release={props.chartRelease} loading={props.chartsLoading} message={props.chartMessage} mode={props.mode} onInvalid={props.onInvalid} />}
    </>}
  </aside>
}
