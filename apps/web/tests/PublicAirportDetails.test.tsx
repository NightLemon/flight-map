import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PublicAirportDetails } from '../src/PublicAirportDetails'
import type { AirportDetail } from '../src/public-data'
import { record } from './fixtures'

function detail(overrides: Partial<AirportDetail> = {}): AirportDetail {
  return {
    airport: record({ id: 'ourairports:airport:1', identifier: 'ZTEST', name: 'Synthetic Airport', properties: {
      type: 'medium_airport', municipality: '测试市', elevation_ft: '100', icao_id: 'ZTEST', iata_code: 'TST', gps_code: 'ZTEST', local_code: 'LOCAL', home_link: 'javascript:alert(1)',
    } }),
    communications: [record({ id: 'voice', kind: 'frequency', properties: { service: 'TWR', frequency: '118.000', unit: 'MHz' } })],
    navigation_frequencies: [record({ id: 'navigation', kind: 'frequency', properties: { service: 'LOC', frequency: '108.90', unit: 'MHz' } })],
    unclassified_frequencies: [record({ id: 'unclassified', kind: 'frequency', properties: { service: 'SOURCE TYPE', frequency: '329.3', unit: 'MHz' } })],
    runways: [record({ id: 'closed-runway', kind: 'runway', properties: { le_ident: '08R', he_ident: '26L', length_ft: '10000', width_ft: '150', surface: 'ASP', lighted: '', closed: '1' }, geometry: null })],
    ...overrides,
  }
}

describe('public airport details', () => {
  it('keeps unsafe website and evidence values out of external links', () => {
    render(<PublicAirportDetails detail={detail({ review_notes: [{
      id: 'note-1', airport_id: 'ourairports:airport:1', record_id: 'ourairports:airport:1', field: 'name', original_value: 'Old name', value: 'Corrected name', status: 'corrected', message: '已根据公开资料修正名称。', reviewed_at: '2026-09-08',
      evidence: [{ title: '不安全链接', url: 'javascript:alert(1)' }, { title: '公开公告', url: 'https://example.test/notice', published_at: '2026-09-01' }],
    }] })} />)

    fireEvent.click(screen.getByText('资料核查记录'))
    expect(screen.queryByRole('link', { name: /机场官网/ })).not.toBeInTheDocument()
    expect(screen.getByText('不安全链接（来源链接不可用）')).toBeVisible()
    const source = screen.getByRole('link', { name: '公开公告 ↗' })
    expect(source).toHaveAttribute('href', 'https://example.test/notice')
    expect(source).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('separates frequency categories and preserves source values', () => {
    render(<PublicAirportDetails detail={detail()} />)

    expect(within(screen.getByRole('region', { name: '机场通信频率' })).getByText('118.000 MHz')).toBeVisible()
    expect(within(screen.getByRole('region', { name: '导航频率参考' })).getByText('108.90 MHz')).toBeVisible()
    expect(within(screen.getByRole('region', { name: '未分类频率' })).getByText('329.3 MHz')).toBeVisible()
    expect(screen.getByText('这些是来源中的调谐值参考，不是语音通信频率。')).toBeVisible()
  })

  it('folds source-closed runways and states missing geometry and unknown lights', () => {
    render(<PublicAirportDetails detail={detail()} />)

    expect(screen.getByRole('region', { name: '跑道' })).toHaveTextContent('来源标为关闭')
    expect(screen.getByText('起点 08R · 终点 26L')).not.toBeVisible()
    fireEvent.click(screen.getAllByText('来源标为关闭')[0])
    expect(screen.getByText('起点 08R · 终点 26L')).toBeVisible()
    expect(screen.getByText('灯光：来源未提供')).toBeVisible()
    expect(screen.getByText('来源未提供完整地图端点')).toBeVisible()
  })

  it('treats a multi-segment runway with complete endpoints as mappable', () => {
    render(<PublicAirportDetails detail={detail({ runways: [record({ id: 'segmented-runway', kind: 'runway', properties: { le_ident: '01', he_ident: '19', length_ft: '5000', width_ft: '100', lighted: '1', closed: '0' }, geometry: { type: 'MultiLineString', coordinates: [[[100, 30], [100.01, 30.01]]] } })] })} />)

    expect(screen.queryByText('来源未提供完整地图端点')).not.toBeInTheDocument()
    expect(screen.getByText('灯光：有灯光（来源标记）')).toBeVisible()
  })

  it('omits the review section when notes are absent and shows original values when present', () => {
    const view = render(<PublicAirportDetails detail={detail({ review_notes: undefined })} />)
    expect(screen.queryByRole('region', { name: '资料核查记录' })).not.toBeInTheDocument()

    view.rerender(<PublicAirportDetails detail={detail({ review_notes: [{
      id: 'note-2', airport_id: 'ourairports:airport:1', record_id: 'runway-1', field: 'length_ft', original_value: '9000', status: 'needs_review', message: '长度与端点距离待核查。', evidence: [], reviewed_at: '2026-09-08',
    }] })} />)
    const review = screen.getByRole('region', { name: '资料核查记录' })
    fireEvent.click(within(review).getByText('资料核查记录'))
    expect(within(review).getByText('9000')).toBeVisible()
    expect(within(review).queryByText('修正值')).not.toBeInTheDocument()
    expect(within(review).getByText('2026-09-08')).toBeVisible()
  })
})
