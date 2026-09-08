import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AirportCommunications } from '../src/AirportCommunications'
import { record } from './fixtures'

const syntheticCommunications = [
  record({
    id: 'synthetic:communication:ground',
    properties: {
      service: '地面管制', frequency: '118.000', unit: 'MHz', remarks: '推出前联系地面管制。',
    },
    provenance: {
      asset_sha256: 'a'.repeat(64), member: 'synthetic/COMM.csv', line: 42,
      locator: 'synthetic:communication:ground',
    },
  }),
  record({
    id: 'synthetic:communication:atis',
    properties: { service: '航行情报', frequency: '123.45', unit: 'MHz', remarks: '' },
    provenance: {
      asset_sha256: 'b'.repeat(64), member: 'synthetic/COMM.csv', line: 43,
      locator: 'synthetic:communication:atis',
    },
  }),
]

describe('airport communications', () => {
  it('makes a receive-only frequency explicit and retains sector restrictions', () => {
    render(<AirportCommunications items={[{ ...syntheticCommunications[0], properties: { service: 'LCL/P', frequency: '122.1', unit: 'MHz', receive_only: true, sectorization: 'NORTH ONLY' } }]} loading={false} message="" />)
    expect(screen.getByText(/仅接收 \(R\)/)).toBeVisible()
    expect(screen.getByText('NORTH ONLY')).toBeVisible()
  })
  it('shows synthetic frequency values unchanged with remarks and collapsible source details', () => {
    render(<AirportCommunications items={syntheticCommunications} loading={false} message="" />)

    expect(screen.getByRole('region', { name: '机场通信频率' })).toBeVisible()
    expect(screen.getByRole('heading', { name: '常用通信频率' })).toBeVisible()
    expect(screen.getByText('地面管制')).toBeVisible()
    expect(screen.getByText('118.000 MHz')).toBeVisible()
    expect(screen.getByText('123.45 MHz')).toBeVisible()
    expect(screen.getByText('推出前联系地面管制。')).toBeVisible()
    expect(screen.queryByText('航行情报').parentElement).not.toHaveTextContent('说明')

    const details = screen.getAllByText('来源详情')[0].closest('details')
    expect(details).not.toHaveAttribute('open')
    fireEvent.click(screen.getAllByText('来源详情')[0])
    expect(within(details!).getByText('synthetic/COMM.csv')).toBeVisible()
    expect(screen.getByText('42')).toBeVisible()
    expect(screen.getByText('synthetic:communication:ground')).toBeVisible()
    expect(screen.getByText('a'.repeat(64))).toBeVisible()
  })

  it('clearly reports loading, errors, and an empty synthetic result', () => {
    const view = render(<AirportCommunications items={[]} loading message="" />)
    expect(screen.getByRole('status')).toHaveTextContent('正在读取常用通信频率…')

    view.rerender(<AirportCommunications items={[]} loading={false} message="通信频率暂时无法读取" />)
    expect(screen.getByRole('status')).toHaveTextContent('通信频率暂时无法读取')

    view.rerender(<AirportCommunications items={[]} loading={false} message="" />)
    expect(screen.getByText('该机场没有可显示的常用通信频率。')).toBeVisible()
  })
})
