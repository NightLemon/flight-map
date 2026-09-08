import { useEffect, useRef, useState } from 'react'
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist'
import { ApiError, errorMessage, isAbort, type Mode, type Release } from './api'
import { fetchChartPdf } from './pdf-client'
import { loadPdf } from './pdf-runtime'

type Props = { chartId: string; title: string; release: Release; mode: Mode; onInvalid?: (error: unknown) => void }

export function PdfViewer({ chartId, title, release, mode, onInvalid }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const taskRef = useRef<RenderTask | null>(null)
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null)
  const pageNumber = 1
  const zoom = 1
  const [width, setWidth] = useState(0)
  const [state, setState] = useState<'loading' | 'rendering' | 'ready' | 'failed'>('loading')
  const [error, setError] = useState('')
  const invalidRef = useRef(onInvalid)
  useEffect(() => { invalidRef.current = onInvalid }, [onInvalid])

  const clearCanvas = () => {
    taskRef.current?.cancel(); taskRef.current = null
    if (canvasRef.current) { canvasRef.current.width = 0; canvasRef.current.height = 0 }
  }

  useEffect(() => {
    const controller = new AbortController()
    let task: ReturnType<typeof loadPdf> | undefined
    fetchChartPdf(chartId, release, mode, controller.signal).then(async (bytes) => {
      if (controller.signal.aborted) return
      task = loadPdf(bytes)
      const next = await task.promise
      if (!controller.signal.aborted) setDocument(next)
    }).catch((reason: unknown) => {
      if (controller.signal.aborted || isAbort(reason)) return
      clearCanvas(); setState('failed'); setError(errorMessage(reason))
      if (reason instanceof ApiError && [403, 409, 410].includes(reason.status)) invalidRef.current?.(reason)
    })
    return () => { controller.abort(); clearCanvas(); void task?.destroy() }
  }, [chartId, release, mode])

  useEffect(() => {
    if (!containerRef.current) return
    const target = containerRef.current
    const measure = () => setWidth(Math.max(1, target.clientWidth - 2))
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(target)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!document || !width || !canvasRef.current) return
    let active = true
    const canvas = canvasRef.current
    // External PDF rendering owns the canvas; clear its previous page before starting.
    // eslint-disable-next-line react/set-state-in-effect
    clearCanvas(); setState('rendering'); setError('')
    document.getPage(pageNumber).then(async (page) => {
      if (!active) return
      const natural = page.getViewport({ scale: 1 })
      const viewport = page.getViewport({ scale: width / natural.width * zoom })
      const density = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = Math.ceil(viewport.width * density); canvas.height = Math.ceil(viewport.height * density)
      canvas.style.width = `${viewport.width}px`; canvas.style.height = `${viewport.height}px`
      const task = page.render({ canvas, viewport, transform: density === 1 ? undefined : [density, 0, 0, density, 0, 0] })
      taskRef.current = task
      await task.promise
      if (active) { taskRef.current = null; setState('ready') }
    }).catch((reason: unknown) => {
      if (!active) return
      clearCanvas(); setState('failed'); setError(errorMessage(reason))
    })
    return () => { active = false; clearCanvas() }
  }, [document, pageNumber, width, zoom])


  return <div className="pdf-viewer" aria-label={`PDF 查看器 ${title}`}>
    <p className="version-caption" role="status">{state === 'ready' ? `PDF 已显示 · 第 ${pageNumber} 页 / 共 ${document?.numPages} 页` : state === 'failed' ? 'PDF 显示失败，可使用 FAA 官方链接。' : state === 'loading' ? '正在获取官方 PDF…' : '正在绘制 PDF 页面…'}</p>
    {error && <p role="status" className="inline-notice">{error}</p>}
    <div ref={containerRef} className="pdf-canvas-container">
      <canvas ref={canvasRef} aria-label={`官方航图 ${title} · 第 ${pageNumber} 页`} data-rendered={state === 'ready' ? 'true' : 'false'} style={{ visibility: state === 'ready' ? 'visible' : 'hidden' }} />
    </div>
  </div>
}

