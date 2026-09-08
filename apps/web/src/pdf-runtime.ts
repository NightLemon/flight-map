import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

GlobalWorkerOptions.workerSrc = workerUrl

export function loadPdf(data: Uint8Array<ArrayBuffer>) {
  const base = `${import.meta.env.BASE_URL}pdfjs/`
  return getDocument({ data, cMapUrl: `${base}cmaps/`, cMapPacked: true,
    standardFontDataUrl: `${base}standard_fonts/`, wasmUrl: `${base}wasm/`, iccUrl: `${base}iccs/`,
    useSystemFonts: false })
}
