import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../src/api'
import { release } from './fixtures'

const mock = vi.hoisted(() => ({ fetch: vi.fn(), load: vi.fn() }))
vi.mock('../src/pdf-client', () => ({ fetchChartPdf: mock.fetch }))
vi.mock('../src/pdf-runtime', () => ({ loadPdf: mock.load }))
import { PdfViewer } from '../src/PdfViewer'

let finish: () => void
let renderPage: ReturnType<typeof vi.fn>
let cancel: ReturnType<typeof vi.fn>
let destroy: ReturnType<typeof vi.fn>
const props = () => ({ chartId: 'test-chart', title: 'SYNTHETIC TEST', release: release('dtpp'), mode: 'current' as const })
beforeEach(() => {
  cancel = vi.fn(); destroy = vi.fn()
  renderPage = vi.fn(() => ({ promise: new Promise<void>((resolve) => { finish = resolve }), cancel }))
  const doc = { numPages: 2, getPage: vi.fn(async () => ({ getViewport: ({ scale }: { scale: number }) => ({ width: 612 * scale, height: 792 * scale }), render: renderPage })) }
  mock.fetch.mockReset().mockResolvedValue(new Uint8Array([1]))
  mock.load.mockReset().mockReturnValue({ promise: Promise.resolve(doc), destroy })
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
})
afterEach(() => vi.unstubAllGlobals())

describe('PDF page rendering lifecycle', () => {
  it('only reports success after render finishes and clears the canvas immediately on page change', async () => {
    render(<PdfViewer {...props()} />)
    await waitFor(() => expect(renderPage).toHaveBeenCalledTimes(1))
    expect(screen.queryByText(/PDF 已显示/)).not.toBeInTheDocument()
    await act(async () => finish())
    expect(screen.getByText('PDF 已显示 · 第 1 页 / 共 2 页')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '下一页' }))
    expect(screen.getByLabelText('官方航图 SYNTHETIC TEST · 第 2 页')).toHaveAttribute('width', '0')
    expect(screen.queryByText(/PDF 已显示/)).not.toBeInTheDocument()
    await waitFor(() => expect(renderPage).toHaveBeenCalledTimes(2))
    await act(async () => finish())
    expect(screen.getByText('PDF 已显示 · 第 2 页 / 共 2 页')).toBeVisible()
    expect(screen.getByRole('button', { name: '下一页' })).toBeDisabled()
  })
  it('cancels the render, destroys its worker task and aborts bytes when unmounted', async () => {
    const view = render(<PdfViewer {...props()} />)
    await waitFor(() => expect(renderPage).toHaveBeenCalled())
    const signal = mock.fetch.mock.calls[0][3] as AbortSignal
    view.unmount()
    expect(cancel).toHaveBeenCalled(); expect(destroy).toHaveBeenCalled(); expect(signal.aborted).toBe(true)
    await act(async () => finish())
    expect(screen.queryByText(/PDF 已显示/)).not.toBeInTheDocument()
  })
  it('clears the page for zoom and fit changes and renders at the requested scale', async () => {
    render(<PdfViewer {...props()} />)
    await waitFor(() => expect(renderPage).toHaveBeenCalled())
    await act(async () => finish())
    fireEvent.click(screen.getByRole('button', { name: '放大航图' }))
    expect(screen.getByLabelText('PDF 缩放')).toHaveTextContent('125%')
    expect(screen.queryByText(/PDF 已显示/)).not.toBeInTheDocument()
    await waitFor(() => expect(renderPage).toHaveBeenCalledTimes(2)); await act(async () => finish())
    fireEvent.click(screen.getByRole('button', { name: '适合宽度' }))
    expect(screen.getByLabelText('PDF 缩放')).toHaveTextContent('100%')
  })
  it.each([502, 504])('keeps upstream %i local to the chart panel', async (code) => {
    mock.fetch.mockRejectedValue(new ApiError(code, 'Official PDF unavailable'))
    const invalid = vi.fn(); render(<PdfViewer {...props()} onInvalid={invalid} />)
    await screen.findByText('Official PDF unavailable')
    expect(invalid).not.toHaveBeenCalled()
    expect(screen.queryByText(/PDF 已显示/)).not.toBeInTheDocument()
  })
  it.each([403, 409, 410])('invalidates the pinned session after PDF gate error %i', async (code) => {
    mock.fetch.mockRejectedValue(new ApiError(code, 'Version unavailable'))
    const invalid = vi.fn(); render(<PdfViewer {...props()} onInvalid={invalid} />)
    await waitFor(() => expect(invalid).toHaveBeenCalled())
  })
})
