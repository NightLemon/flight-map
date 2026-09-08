import { ApiError, apiUrl, type Mode, type Release, versionQuery } from './api'

const MAX_PDF_BYTES = 20 * 1024 * 1024

export async function fetchChartPdf(chartId: string, release: Release, mode: Mode, signal: AbortSignal): Promise<Uint8Array<ArrayBuffer>> {
  // This endpoint accepts a stored chart identity only. Never fetch a supplied URL.
  const response = await fetch(apiUrl(`/charts/${encodeURIComponent(chartId)}/pdf?${versionQuery(release, mode)}`), {
    signal: AbortSignal.any([signal, AbortSignal.timeout(25000)]), cache: 'no-store', credentials: 'omit', redirect: 'error',
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { detail?: string }
    throw new ApiError(response.status, `${payload.detail ?? '无法读取官方 PDF'} (${response.status})`)
  }
  if (response.headers.get('X-FlightMap-Release-Id') !== release.id || response.headers.get('X-FlightMap-Chart-Id') !== chartId) {
    throw new ApiError(409, 'PDF 响应版本与本页固定航图不一致')
  }
  const expectedHash = response.headers.get('X-FlightMap-Pdf-Sha256') ?? ''
  if (!/^[a-f0-9]{64}$/i.test(expectedHash)) throw new Error('PDF 缺少有效的原件哈希')
  if (response.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase() !== 'application/pdf') throw new Error('官方响应不是 PDF')
  if (Number(response.headers.get('Content-Length')) > MAX_PDF_BYTES) throw new Error('PDF 超过 20 MiB 限制')
  const bytes = new Uint8Array(await response.arrayBuffer())
  signal.throwIfAborted()
  if (bytes.length > MAX_PDF_BYTES || new TextDecoder().decode(bytes.subarray(0, 5)) !== '%PDF-') throw new Error('PDF 文件头或大小无效')
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))
  const actualHash = Array.from(digest, (part) => part.toString(16).padStart(2, '0')).join('')
  if (actualHash !== expectedHash.toLowerCase()) throw new Error('PDF 原件哈希与响应证据不一致')
  signal.throwIfAborted()
  return bytes
}
