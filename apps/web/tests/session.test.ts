import { describe, expect, it } from 'vitest'
import { assertVersion, ApiError, versionQuery } from '../src/api'
import { expired, officialPdfUrl, releaseKey, sameChartCycle, selectedReleases } from '../src/session'
import { release, status } from './fixtures'

describe('publication session', () => {
  it('does not automatically select preview or historical products', () => {
    const past = release('dtpp', { state: 'history', id: 'old', airac: '2608' })
    const snapshot = status({ releases: [past] })
    expect(selectedReleases(snapshot, 'history', {})).toEqual({})
    expect(selectedReleases(snapshot, 'history', { dtpp: 'old' })).toEqual({ dtpp: past })
    expect(selectedReleases(snapshot, 'preview', { dtpp: 'old' })).toEqual({})
  })
  it('expires the full set at the earliest exclusive boundary', () => {
    const publications = { nasr: release('nasr'), dtpp: release('dtpp', { valid_to: '2026-09-10T09:01:00Z' }) }
    expect(expired(publications, Date.parse('2026-09-10T09:00:59Z'))).toBe(false)
    expect(expired(publications, Date.parse('2026-09-10T09:01:00Z'))).toBe(true)
    expect(expired(publications, Date.parse('2026-09-01T00:00:00Z'))).toBe(true)
  })
  it('pins the actual release id including corrected editions and rejects mismatched responses', () => {
    const current = release('nasr')
    const correction = release('nasr', { id: `${current.id}-correction` })
    expect(releaseKey({ nasr: current }, 'current')).not.toBe(releaseKey({ nasr: correction }, 'current'))
    expect(new URLSearchParams(versionQuery(correction, 'current')).get('release_id')).toBe(correction.id)
    expect(() => assertVersion({ release_id: current.id, mode: 'current' }, correction, 'current')).toThrow(ApiError)
  })
  it('does not pair another cycle or accept non-FAA PDF urls', () => {
    expect(sameChartCycle(release('cifp'), release('dtpp', { airac: '2608' }))).toBe(false)
    expect(officialPdfUrl('https://aeronav.faa.gov/d-tpp/2609/sample.pdf')).toContain('faa.gov')
    expect(officialPdfUrl('https://faa.gov.example.com/sample.pdf')).toBeNull()
    expect(officialPdfUrl('javascript:alert(1)')).toBeNull()
  })
  it('pairs same-cycle releases only when their valid intervals overlap', () => {
    const procedure = release('cifp')
    expect(sameChartCycle(procedure, release('dtpp'))).toBe(true)
    expect(sameChartCycle(procedure, release('dtpp', { valid_from: '2026-09-20T09:01:00Z', valid_to: '2026-10-10T09:01:00Z' }))).toBe(true)
    expect(sameChartCycle(procedure, release('dtpp', { valid_from: procedure.valid_to, valid_to: '2026-10-29T09:01:00Z' }))).toBe(false)
    expect(sameChartCycle(procedure, release('dtpp', { valid_from: '2026-08-01T09:01:00Z', valid_to: '2026-09-01T09:01:00Z' }))).toBe(false)
    expect(sameChartCycle(procedure, release('dtpp', { valid_from: procedure.valid_to, valid_to: procedure.valid_from }))).toBe(false)
    expect(sameChartCycle(undefined, release('dtpp'))).toBe(false)
    expect(sameChartCycle(procedure, undefined)).toBe(false)
  })
  it.each(['valid_from', 'valid_to'] as const)('rejects an unparseable %s in either release', (field) => {
    expect(sameChartCycle(release('cifp', { [field]: 'invalid-date' }), release('dtpp'))).toBe(false)
    expect(sameChartCycle(release('cifp'), release('dtpp', { [field]: 'invalid-date' }))).toBe(false)
  })
})
