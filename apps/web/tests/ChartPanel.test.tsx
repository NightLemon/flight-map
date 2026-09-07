import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ChartPanel } from '../src/ChartPanel'
import { chart, release } from './fixtures'

describe('official chart viewer', () => {
  it('retains an official link when PDF embedding fails', () => {
    render(<ChartPanel charts={[chart]} release={release('dtpp')} loading={false} message="" />)
    fireEvent.click(screen.getByRole('button', { name: /SYNTHETIC DEPARTURE CHART/ }))
    const iframe = screen.getByTitle('官方航图 SYNTHETIC DEPARTURE CHART')
    expect(screen.getByRole('link', { name: /FAA 官方网站/ })).toHaveAttribute('target', '_blank')
    fireEvent.error(iframe)
    expect(screen.getByText(/PDF 预览未能确认显示/)).toBeVisible()
    expect(screen.queryByTitle('官方航图 SYNTHETIC DEPARTURE CHART')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /FAA 官方网站/ })).toHaveAttribute('href', chart.properties.pdf_url)
  })
  it('unloads the previous PDF when the directory is replaced', () => {
    const view = render(<ChartPanel charts={[chart]} release={release('dtpp')} loading={false} message="" />)
    fireEvent.click(screen.getByRole('button', { name: /SYNTHETIC DEPARTURE CHART/ }))
    view.rerender(<ChartPanel charts={[]} release={undefined} loading={false} message="已撤销" />)
    expect(screen.queryByTitle(/官方航图/)).not.toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})
