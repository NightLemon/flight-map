import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
vi.mock('../src/PdfViewer', () => ({ PdfViewer: ({ title }: { title: string }) => <div><canvas title={`官方航图 ${title}`} /><p>PDF 显示失败，可使用 FAA 官方链接。</p></div> }))
import { ChartPanel } from '../src/ChartPanel'
import { chart, release } from './fixtures'

describe('official chart viewer', () => {
  it('retains the official link when its PDF viewer reports failure', () => {
    render(<ChartPanel charts={[chart]} release={release('dtpp')} loading={false} message="" />)
    fireEvent.click(screen.getByRole('button', { name: /SYNTHETIC DEPARTURE CHART/ }))
    expect(screen.getByRole('link', { name: /FAA 官方网站/ })).toHaveAttribute('target', '_blank')
    expect(screen.getByText(/PDF 显示失败/)).toBeVisible()
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
