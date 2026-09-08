// Synthetic records for tests only. None are imported by the application.
import type { GeometryResponse, Release, ResearchRecord, SnapshotStatus, Status } from '../src/api'

export function researchSnapshot(overrides: Partial<SnapshotStatus> = {}): SnapshotStatus {
  return { id: 'nasr-research-synthetic-2609', source_id: 'synthetic-test', product_id: 'nasr',
    official_effective_date: '2026-09-03', date_precision: 'day', exact_validity_status: 'unknown',
    date_evidence: ['synthetic date evidence'], input_sha256: ['a'.repeat(64)], parser_version: 'synthetic-only', schema_version: 'research-1',
    capabilities: ['airports'], update_interval_days: 28, update_interval_evidence: ['synthetic interval'],
    state: 'active', date_status: 'researchable', expected_update_date: '2026-10-01', counts: { airports: 1 }, ...overrides }
}

export function release(product: string, overrides: Partial<Release> = {}): Release {
  return { id: `synthetic-${product}-2609`, source_id: 'synthetic-test', product_id: product, airac: '2609',
    valid_from: '2026-09-03T09:01:00Z', valid_to: '2026-10-01T09:01:00Z', parser_version: 'test-only',
    quality_status: 'verified', state: 'current', capabilities: product === 'nasr' ? ['airports'] : product === 'cifp' ? ['procedures', 'runways', 'navaids', 'waypoints', 'airways'] : ['charts'],
    issues: [], input_sha256: ['a'.repeat(64)], validity_evidence: ['synthetic test fixture'], ...overrides }
}
export function status(overrides: Partial<Status> = {}): Status {
  const releases = ['nasr', 'cifp', 'dtpp'].map((product) => release(product))
  return { current_time: '2026-09-07T00:00:00Z', airac: { identifier: '2609', valid_from: '2026-09-03T00:00:00Z', valid_to: '2026-10-01T00:00:00Z' },
    verified_release_available: true, publication_state: 'current', disclaimer: 'Synthetic test fixture',
    current_releases: Object.fromEntries(releases.map((item) => [item.product_id, item])), releases, ...overrides }
}
export function record(overrides: Partial<ResearchRecord> = {}): ResearchRecord {
  return { id: 'test:airport:ZZZ', kind: 'airport', name: 'SYNTHETIC TEST AIRPORT', identifier: 'ZZZ',
    airport_id: null, airport_ident: null, parent_id: null, branch_id: null, sequence: null,
    geometry: { type: 'Point', coordinates: [-100, 35] }, properties: { icao_id: 'KZZZ' },
    provenance: { asset_sha256: 'a'.repeat(64), member: 'synthetic.csv', line: 1, locator: 'synthetic-row:1' }, ...overrides }
}
export const airport = record()
export const procedure = record({ id: 'test:procedure:SID', kind: 'procedure', name: 'SYNTHETIC SID', identifier: 'TEST1', geometry: null, properties: { procedure_type: 'SID' } })
export const legs = [
  record({ id: 'leg1', kind: 'leg', name: 'START', identifier: 'START', branch_id: 'BRANCH A', sequence: 10, properties: { path_terminator: 'IF' } }),
  record({ id: 'leg2', kind: 'leg', name: 'GAP', identifier: 'GAP', branch_id: 'BRANCH A', sequence: 20, properties: { path_terminator: 'RF' } }),
  record({ id: 'leg3', kind: 'leg', name: 'END', identifier: 'END', branch_id: 'BRANCH B', sequence: 10, properties: { path_terminator: 'IF' } }),
]
export const chart = record({ id: 'test:chart:DP', kind: 'chart', name: 'SYNTHETIC DEPARTURE CHART', geometry: null, properties: { chart_code: 'DP', pdf_url: 'https://aeronav.faa.gov/d-tpp/2609/synthetic-test.pdf' } })
export function geometry(branch: string): GeometryResponse {
  return { type: 'FeatureCollection', release_id: release('cifp').id, mode: 'current',
    features: branch === 'BRANCH A' ? [{ type: 'Feature', geometry: { type: 'Point', coordinates: [-100, 35] }, properties: { leg_id: 'leg1' } }] : [],
    gaps: branch === 'BRANCH A' ? [{ leg_id: 'leg2', reason: 'Unsupported RF leg; no replacement line' }] : [],
    notice: 'Synthetic nominal geometry; no turn prediction' }
}
