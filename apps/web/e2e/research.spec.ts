import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'
import { airport, chart, geometry, legs, procedure, release, researchSnapshot, status } from '../tests/fixtures'

const pdf = readFileSync(new URL('../../../tests/fixtures/synthetic-two-page.pdf', import.meta.url))
const pdfHash = createHash('sha256').update(pdf).digest('hex')
const unavailableChart = { ...chart, id: 'unavailable-chart', name: 'SYNTHETIC UNAVAILABLE PDF' }

test('date research → airport → branch → rendered PDF, zoom, split, failure and version clearing', async ({ page }) => {
  let unavailable = false
  const requested: string[] = []
  const consoleErrors: string[] = []
  page.on('pageerror', (error) => consoleErrors.push(error.message))
  await page.route('https://aeronav.faa.gov/**', (route) => route.abort())
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url()); requested.push(url.pathname + url.search)
    const envelope = { release_id: url.searchParams.get('release_id'), snapshot_id: url.searchParams.get('snapshot_id'), mode: url.searchParams.get('mode') }
    if (url.pathname.endsWith('/pdf')) {
      if (url.pathname.includes('unavailable-chart')) { await route.fulfill({ status: 504, json: { detail: 'Synthetic official service timeout' } }); return }
      await route.fulfill({ body: pdf, headers: { 'Content-Type': 'application/pdf', 'X-FlightMap-Release-Id': release('dtpp').id,
        'X-FlightMap-Chart-Id': chart.id, 'X-FlightMap-Pdf-Sha256': pdfHash, 'Cache-Control': 'no-store' } }); return
    }
    let payload: unknown
    if (url.pathname.endsWith('/status')) payload = status({ current_releases: unavailable ? {} : { cifp: release('cifp'), dtpp: release('dtpp') },
      research: { current_time: '2026-09-08T00:00:00Z', active_snapshots: unavailable ? {} : { nasr: researchSnapshot() }, snapshots: [], attempts: [], storage_errors: [], disclaimer: 'synthetic only' } })
    else if (url.pathname.endsWith('/coverage') || url.pathname.endsWith('/sources')) payload = []
    else if (url.pathname.endsWith('/features')) payload = { ...envelope, type: 'FeatureCollection', features: [{ type: 'Feature', geometry: airport.geometry,
      properties: { ...airport.properties, datum: 'NAD83', id: airport.id, identifier: airport.identifier, name: airport.name, kind: 'airport', ...envelope, provenance: airport.provenance } }] }
    else if (url.pathname.endsWith('/search')) payload = { ...envelope, items: envelope.snapshot_id ? [{ ...airport, properties: { ...airport.properties, datum: 'NAD83' } }] : [] }
    else if (url.pathname.endsWith('/charts')) payload = { ...envelope, items: [chart, unavailableChart] }
    else if (url.pathname.endsWith('/airports/KZZZ/procedures')) payload = { ...envelope, items: [procedure] }
    else if (url.pathname.endsWith('/geometry')) payload = geometry(url.searchParams.get('branch_id') ?? '')
    else if (url.pathname.includes('/procedures/')) payload = { ...envelope, record: procedure, legs, branches: ['BRANCH A', 'BRANCH B'] }
    else throw new Error(`Unmocked route ${url}`)
    await route.fulfill({ json: payload })
  })
  await page.goto('/')
  await expect(page.getByText('API 已连接')).toBeVisible()
  await expect(page.getByRole('button', { name: '日期级研究' })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('textbox', { name: /搜索机场/ }).fill('KZZZ')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await page.getByLabel('搜索结果').getByRole('button', { name: /SYNTHETIC TEST AIRPORT/ }).click()
  await expect(page.getByLabel('航空资料地图', { exact: true })).toHaveAttribute('data-zoom', '10')
  await page.getByRole('button', { name: /SYNTHETIC SID/ }).click()
  await page.getByRole('combobox', { name: '程序分支' }).selectOption('BRANCH A')
  await expect(page.getByText(/几何缺口 · Unsupported RF leg/)).toBeVisible()
  await page.getByRole('button', { name: /SYNTHETIC DEPARTURE CHART/ }).click()
  await expect(page.getByRole('link', { name: /FAA 官方网站/ })).toHaveAttribute('target', '_blank')
  await expect(page.getByText('PDF 已显示 · 第 1 页 / 共 2 页')).toBeVisible({ timeout: 20000 })
  const canvas = page.locator('.pdf-canvas-container canvas')
  const first = await canvas.screenshot()
  expect(await canvas.evaluate((el: HTMLCanvasElement) => {
    const data = el.getContext('2d')!.getImageData(0, 0, el.width, el.height).data
    let ink = 0
    for (let i = 0; i < data.length; i += 4) if (data[i] < 200 && data[i + 1] < 200 && data[i + 2] < 200 && data[i + 3]) ink++
    return ink
  })).toBeGreaterThan(200)
  await page.getByRole('button', { name: '下一页' }).click()
  await expect(page.getByText('PDF 已显示 · 第 2 页 / 共 2 页')).toBeVisible()
  expect((await canvas.screenshot()).equals(first)).toBe(false)
  const originalWidth = await canvas.evaluate((el: HTMLCanvasElement) => el.width)
  await page.getByRole('button', { name: '放大航图' }).click()
  await expect(page.getByLabel('PDF 缩放')).toHaveText('125%')
  await expect(canvas).toHaveAttribute('data-rendered', 'true')
  expect(await canvas.evaluate((el: HTMLCanvasElement) => el.width)).toBeGreaterThan(originalWidth)
  await page.getByRole('button', { name: '适合宽度' }).click()
  const divider = page.getByRole('separator')
  const mapWidth = (await page.getByLabel('航空资料地图', { exact: true }).boundingBox())!.width
  await divider.focus(); await divider.press('ArrowLeft')
  await expect(divider).toHaveAttribute('aria-valuenow', '524')
  expect((await page.getByLabel('航空资料地图', { exact: true }).boundingBox())!.width).toBeLessThan(mapWidth)
  await expect(canvas).toHaveAttribute('data-rendered', 'true')
  await page.screenshot({ path: 'test-results/research-desktop.png', fullPage: true })
  await page.getByRole('button', { name: /SYNTHETIC UNAVAILABLE PDF/ }).click()
  await expect(page.getByText('Synthetic official service timeout (504)')).toBeVisible()
  await expect(page.getByText('API 已连接')).toBeVisible()
  await expect(page.getByRole('link', { name: /FAA 官方网站/ })).toBeVisible()
  await expect(page.getByText('SYNTHETIC TEST AIRPORT')).toBeVisible()
  expect(requested.filter((url) => url.includes('/geometry')).every((url) => url.includes('branch_id=BRANCH+A') && url.includes(`release_id=${release('cifp').id}`))).toBe(true)
  unavailable = true
  await page.getByRole('button', { name: '重新检查', exact: true }).click()
  await expect(page.getByText('尚无可用研究资料')).toBeVisible()
  await expect(page.locator('.pdf-viewer')).toHaveCount(0)
  await expect(page.getByText('SYNTHETIC TEST AIRPORT')).toHaveCount(0)
  expect(consoleErrors).toEqual([])
})

test('offline API leaves reference map and retry action without sample aviation data', async ({ page }) => {
  await page.route('**/api/v1/**', (route) => route.abort('internetdisconnected'))
  await page.goto('/')
  await expect(page.getByText('API 未连接')).toBeVisible()
  await expect(page.getByText('尚无可用研究资料')).toBeVisible()
  await expect(page.getByRole('button', { name: '重试', exact: true })).toBeVisible()
  await expect(page.getByLabel('搜索结果')).toHaveCount(0)
  await page.screenshot({ path: 'test-results/empty-desktop.png', fullPage: true })
})

test('519×642 wheel and keyboard reach the research desk and PDF controls without programmatic scrolling', async ({ page }) => {
  await page.setViewportSize({ width: 519, height: 642 })
  await page.route('https://aeronav.faa.gov/**', (route) => route.abort())
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    const envelope = { snapshot_id: url.searchParams.get('snapshot_id'), release_id: url.searchParams.get('release_id'), mode: url.searchParams.get('mode') }
    if (url.pathname.endsWith('/pdf')) {
      await route.fulfill({ body: pdf, headers: { 'Content-Type': 'application/pdf', 'X-FlightMap-Release-Id': release('dtpp').id,
        'X-FlightMap-Chart-Id': chart.id, 'X-FlightMap-Pdf-Sha256': pdfHash } }); return
    }
    let payload: unknown
    if (url.pathname.endsWith('/status')) payload = status({ current_releases: { dtpp: release('dtpp') },
      research: { current_time: '2026-09-08T00:00:00Z', active_snapshots: { nasr: researchSnapshot() }, snapshots: [], attempts: [], storage_errors: [], disclaimer: 'synthetic only' } })
    else if (url.pathname.endsWith('/coverage') || url.pathname.endsWith('/sources')) payload = []
    else if (url.pathname.endsWith('/features')) payload = { ...envelope, type: 'FeatureCollection', features: [{ type: 'Feature', geometry: airport.geometry,
      properties: { ...airport.properties, datum: 'NAD83', id: airport.id, identifier: airport.identifier, name: airport.name, kind: 'airport', ...envelope, provenance: airport.provenance } }] }
    else if (url.pathname.endsWith('/search')) payload = { ...envelope, items: envelope.snapshot_id ? [airport] : [] }
    else if (url.pathname.endsWith('/charts')) payload = { ...envelope, items: [chart] }
    else throw new Error(`Unexpected narrow-layout request ${url}`)
    await route.fulfill({ json: payload })
  })
  await page.goto('/')
  await expect(page.getByText('API 已连接')).toBeVisible()
  await page.getByRole('textbox', { name: /搜索机场/ }).fill('ZZZ')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await page.getByLabel('搜索结果').getByRole('button', { name: /SYNTHETIC TEST AIRPORT/ }).click()
  const shell = page.getByRole('main', { name: '研究工作区' })
  const map = page.getByLabel('航空资料地图', { exact: true })
  await expect(map).toHaveAttribute('data-zoom', '10')
  expect(await shell.evaluate((el) => el.clientHeight)).toBe(642)
  expect(await shell.evaluate((el) => el.scrollHeight)).toBeGreaterThan(642)
  await expect(page.getByRole('heading', { name: 'ZZZ', exact: true })).not.toBeInViewport()

  // The pointer is over the visible map, not a scrollbar or an obscured panel.
  await page.mouse.move(259, 480)
  await page.mouse.wheel(0, 430)
  await expect.poll(() => shell.evaluate((el) => el.scrollTop)).toBeGreaterThan(300)
  await expect(map).toHaveAttribute('data-zoom', '10')
  const heading = page.getByRole('heading', { name: 'ZZZ', exact: true })
  await expect(heading).toBeInViewport({ ratio: 1 })
  expect((await heading.boundingBox())!.y).toBeGreaterThan(132)

  // Focus only chooses the keyboard's scroll owner; PageDown performs the scroll.
  await shell.focus()
  const beforePageDown = await shell.evaluate((el) => el.scrollTop)
  await page.keyboard.press('PageDown')
  await expect.poll(() => shell.evaluate((el) => el.scrollTop)).toBeGreaterThan(beforePageDown)
  const chartButton = page.getByRole('button', { name: /SYNTHETIC DEPARTURE CHART/ })
  await expect(chartButton).toBeInViewport({ ratio: 1 })
  await chartButton.click()
  await expect(page.getByText('PDF 已显示 · 第 1 页 / 共 2 页')).toBeVisible()
  const nextPage = page.getByRole('button', { name: '下一页' })
  await expect(nextPage).toBeInViewport({ ratio: 1 })
  expect((await nextPage.boundingBox())!.y).toBeGreaterThan(132)
  // Tabbing from the selected chart reaches close, the official link, then next page.
  await page.keyboard.press('Tab'); await page.keyboard.press('Tab'); await page.keyboard.press('Tab')
  await expect(nextPage).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByText('PDF 已显示 · 第 2 页 / 共 2 页')).toBeVisible()
  expect((await page.locator('.pdf-canvas-container canvas').boundingBox())!.width).toBeLessThan(519)
  await page.screenshot({ path: 'test-results/research-narrow-519.png' })
})
