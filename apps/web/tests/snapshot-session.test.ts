import { describe, expect, it } from 'vitest'
import { assertSnapshot, snapshotQuery } from '../src/api'
import { selectedSnapshot, snapshotChartDate, snapshotChoices } from '../src/session'
import { release, researchSnapshot, status } from './fixtures'

describe('date-level research session', () => {
  const active = researchSnapshot({ date_status: 'update-due' })
  const old = researchSnapshot({ id: 'old', state: 'history' })
  const future = researchSnapshot({ id: 'future', state: 'preview', date_status: 'future' })
  const data = status({ research: { current_time: '2026-09-08T00:00:00Z', active_snapshots: { nasr: active },
    snapshots: [active, old, future, researchSnapshot({ id: 'revoked', state: 'revoked' })], attempts: [], storage_errors: [], disclaimer: 'test only' } })

  it('permits clearly marked older research data, while history and preview require an explicit ID', () => {
    expect(selectedSnapshot(data, 'active', '')).toEqual(active)
    expect(selectedSnapshot(data, 'history', '')).toBeUndefined()
    expect(selectedSnapshot(data, 'history', 'old')).toEqual(old)
    expect(selectedSnapshot(data, 'history', 'future')).toBeUndefined()
    expect(snapshotChoices(data, 'preview')).toEqual([future])
  })
  it('pins immutable snapshot and rejects changed ID or mode', () => {
    expect(new URLSearchParams(snapshotQuery(active, 'active')).get('snapshot_id')).toBe(active.id)
    expect(() => assertSnapshot({ snapshot_id: 'old', mode: 'active' }, active, 'active')).toThrow(/快照/)
    expect(() => assertSnapshot({ snapshot_id: active.id, mode: 'history' }, active, 'active')).toThrow(/快照/)
  })
  it('pairs airport snapshots and chart releases only by the exact official date', () => {
    expect(snapshotChartDate(active, release('dtpp'))).toBe(true)
    expect(snapshotChartDate(active, release('dtpp', { valid_from: '2026-09-04T00:00:00Z' }))).toBe(false)
    expect(snapshotChartDate(active, release('dtpp', { valid_from: 'bad date' }))).toBe(false)
    expect(snapshotChartDate(undefined, release('dtpp'))).toBe(false)
  })
})
