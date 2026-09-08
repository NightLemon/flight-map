// Opt-in real FAA verification. Ordinary CI uses only the synthetic browser suite.
import { expect, test } from '@playwright/test'

const cases = [
  { identifier: 'SEA', query: 'SEA', title: 'ILS OR LOC RWY 16C', filename: '00582IL16C.PDF' },
  { identifier: 'JFK', query: 'KJFK', title: 'VOR OR GPS RWY 13L/R', filename: '00610VG13LR.PDF' },
]

test('real New York airports load after dragging and wheel zoom without searching', async ({ page }) => {
  test.setTimeout(90000)
  const featureUrls: URL[] = []
  const searchUrls: string[] = []
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (url.pathname.endsWith('/features')) featureUrls.push(url)
    if (url.pathname.endsWith('/search')) searchUrls.push(url.href)
  })
  await page.goto('/')
  await expect(page.getByText('API 已连接')).toBeVisible()
  const map = page.getByLabel('航空资料地图', { exact: true })
  await expect(map).toHaveAttribute('data-basemap-state', 'ready', { timeout: 20000 })
  await expect(map).toHaveAttribute('data-zoom', '3.25')
  const box = (await map.boundingBox())!
  // A physical drag from the national overview to lower Manhattan. No search or map API jump.
  const startX = box.x + box.width - 40
  const startY = box.y + box.height / 2
  await page.mouse.move(startX, startY)
  await page.mouse.down()
  await page.mouse.move(startX - 324, startY + 30, { steps: 24 })
  await page.waitForTimeout(150) // Hold still before releasing to avoid drag inertia.
  await page.mouse.up()
  await expect.poll(async () => Number(await map.getAttribute('data-longitude'))).toBeCloseTo(-74.0542, 1)
  await expect.poll(async () => Number(await map.getAttribute('data-latitude'))).toBeCloseTo(40.702, 1)
  for (let step = 1; step <= 4; step++) {
    await page.getByRole('button', { name: 'Zoom in', exact: true }).click()
    await expect.poll(async () => Number(await map.getAttribute('data-zoom'))).toBeCloseTo(3.25 + step, 1)
  }
  expect(featureUrls).toHaveLength(0)
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.wheel(0, -600)
  await expect.poll(async () => Number(await map.getAttribute('data-zoom'))).toBeGreaterThan(7.5)
  await page.mouse.wheel(0, -600)
  await expect.poll(async () => Number(await map.getAttribute('data-zoom'))).toBeGreaterThanOrEqual(8)
  await expect.poll(async () => Number(await map.getAttribute('data-feature-count')), { timeout: 15000 }).toBeGreaterThan(0)
  expect(Number(await map.getAttribute('data-feature-count'))).toBeLessThanOrEqual(500)
  expect(featureUrls.length).toBeGreaterThan(0)
  expect(featureUrls.every((url) => url.searchParams.get('limit') === '500')).toBe(true)
  expect(searchUrls).toHaveLength(0)
  await map.screenshot({ path: 'test-results/live-new-york-manual.png' })
})

for (const { identifier, query, title, filename } of cases) {
  test(`real NASR ${identifier} point → map focus → actual official PDF pixels`, async ({ page, request }) => {
    test.setTimeout(90000)
    const response = await request.get('/api/v1/status')
    expect(response.ok()).toBe(true)
    const status = await response.json()
    const snapshot = status.research.active_snapshots.nasr
    expect(snapshot.id).toBeTruthy()
    expect(snapshot.official_effective_date).toBe(status.current_releases.dtpp.valid_from.slice(0, 10))
    const search = await request.get(`/api/v1/research/search?snapshot_id=${snapshot.id}&q=${query}&mode=active`)
    expect(search.ok()).toBe(true)
    const records = await search.json()
    const airport = records.items.find((item: { identifier: string }) => item.identifier === identifier)
    expect(airport.geometry.type).toBe('Point')
    expect(airport.properties.datum).toBe('NAD83')
    if (identifier === 'JFK') expect(airport.geometry.coordinates).toEqual([-73.77869222, 40.63992805])
    const consoleErrors: string[] = []
    const pdfHeaders: Record<string, string>[] = []
    const pdfUrls: string[] = []
    const featureUrls: string[] = []
    const loadedTiles: string[] = []
    page.on('pageerror', (error) => consoleErrors.push(error.message))
    page.on('request', (req) => { if (new URL(req.url()).pathname.endsWith('/features')) featureUrls.push(req.url()) })
    page.on('response', (res) => {
      if (res.url().includes('/pdf?')) { pdfHeaders.push(res.headers()); pdfUrls.push(res.url()) }
      if (res.url().startsWith('https://tile.openstreetmap.org/') && res.ok()) loadedTiles.push(res.url())
    })
    await page.goto('/')
    await expect(page.getByText('API 已连接')).toBeVisible()
    const map = page.getByLabel('航空资料地图', { exact: true })
    await expect(map).toHaveAttribute('data-basemap-state', 'ready', { timeout: 20000 })
    await expect(page.getByText('放大地图查看附近机场，或搜索机场直接定位')).toBeVisible()
    await page.waitForTimeout(350)
    expect(featureUrls).toHaveLength(0)
    expect(loadedTiles.length).toBeGreaterThan(0)
    await expect(map).toHaveAttribute('data-feature-count', '0')
    await map.screenshot({ path: `test-results/live-${identifier.toLowerCase()}-overview.png` })
    await page.getByRole('textbox', { name: /搜索机场/ }).fill(query)
    await page.getByRole('button', { name: '搜索', exact: true }).click()
    const results = page.getByLabel('搜索结果')
    await results.getByRole('button').filter({ hasText: 'NASR' }).filter({ has: page.locator('strong', { hasText: new RegExp(`^${identifier}$`) }) }).first().click()
    await expect(map).toHaveAttribute('data-zoom', '10')
    await expect.poll(async () => Number(await map.getAttribute('data-feature-count')), { timeout: 15000 }).toBeGreaterThan(0)
    expect(Number(await map.getAttribute('data-feature-count'))).toBeLessThanOrEqual(500)
    expect(featureUrls.every((url) => new URL(url).searchParams.get('limit') === '500')).toBe(true)
    expect(Number(await map.getAttribute('data-latitude'))).toBeCloseTo(airport.geometry.coordinates[1], 6)
    expect(Number(await map.getAttribute('data-longitude'))).toBeCloseTo(airport.geometry.coordinates[0], 6)
    await map.screenshot({ path: `test-results/live-${identifier.toLowerCase()}-local-map.png` })
    // Closing and clicking the rendered center point must reopen the real airport record.
    await page.getByRole('button', { name: '关闭', exact: true }).click()
    const mapBox = (await map.boundingBox())!
    await page.mouse.click(mapBox.x + mapBox.width / 2, mapBox.y + mapBox.height / 2)
    await expect(page.getByRole('heading', { name: identifier, exact: true })).toBeVisible()
    const communications = page.getByRole('region', { name: '机场通信频率' })
    await expect(communications.getByText(identifier === 'JFK' ? '121.9 MHz' : '121.7 MHz', { exact: true })).toBeVisible({ timeout: 15000 })
    await communications.screenshot({ path: `test-results/live-${identifier.toLowerCase()}-communications.png` })
    await page.getByLabel('官方航图', { exact: true }).getByRole('button', { name: `IAP ${title}`, exact: true }).click()
    await expect(page.getByRole('link', { name: /FAA 官方网站/ })).toHaveAttribute('href', `https://aeronav.faa.gov/d-tpp/2609/${filename}`)
    await expect(page.getByText(/PDF 已显示 · 第 1 页 \/ 共 \d+ 页/)).toBeVisible({ timeout: 30000 })
    const canvas = page.locator('.pdf-canvas-container canvas')
    const ink = await canvas.evaluate((element: HTMLCanvasElement) => {
      const data = element.getContext('2d')!.getImageData(0, 0, element.width, element.height).data
      let pixels = 0
      for (let i = 0; i < data.length; i += 4) if (data[i] < 210 && data[i + 1] < 210 && data[i + 2] < 210 && data[i + 3] > 0) pixels++
      return pixels
    })
    expect(ink).toBeGreaterThan(5000)
    const apiBase = (process.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')
    const expectedApi = new URL(`${apiBase}/api/v1/`, page.url())
    const pdfUrl = new URL(pdfUrls[0])
    expect(pdfUrl.origin).toBe(expectedApi.origin)
    expect(pdfUrl.pathname.startsWith(`${expectedApi.pathname}charts/`)).toBe(true)
    expect(pdfHeaders[0]['x-flightmap-release-id']).toBe(status.current_releases.dtpp.id)
    expect(pdfHeaders[0]['x-flightmap-pdf-sha256']).toMatch(/^[a-f0-9]{64}$/)
    await canvas.screenshot({ path: `test-results/live-${identifier.toLowerCase()}-pdf.png` })
    await page.screenshot({ path: `test-results/live-${identifier.toLowerCase()}.png`, fullPage: true })
    expect(consoleErrors).toEqual([])
  })
}

test('real New York NASR runways, navaids, waypoints and airways load independently', async ({ page }) => {
  test.setTimeout(90000)
  const payloads = new Map<string, { features: { properties: { kind: string }; geometry: { type: string } }[] }>()
  page.on('response', async (res) => {
    const url = new URL(res.url())
    if (url.pathname.endsWith('/research/features') && res.ok()) payloads.set(url.searchParams.get('layer')!, await res.json())
  })
  await page.goto('/')
  await expect(page.getByText('API 已连接')).toBeVisible()
  await page.getByRole('textbox', { name: /搜索机场/ }).fill('KJFK')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await page.getByLabel('搜索结果').getByRole('button').filter({ hasText: 'NASR' }).filter({ has: page.locator('strong', { hasText: /^JFK$/ }) }).first().click()
  const map = page.getByLabel('航空资料地图', { exact: true })
  await expect(map).toHaveAttribute('data-zoom', '10')
  for (const [label, layer, kind, geometry] of [
    ['跑道', 'runways', 'runway', 'LineString'], ['导航台', 'navaids', 'navaid', 'Point'],
    ['航点', 'waypoints', 'waypoint', 'Point'], ['航路', 'airways', 'airway', 'LineString'],
  ]) {
    await page.getByRole('checkbox', { name: new RegExp(label) }).check()
    await expect.poll(() => payloads.get(layer)?.features.length ?? 0, { timeout: 15000 }).toBeGreaterThan(0)
    expect(payloads.get(layer)!.features.length).toBeLessThanOrEqual(500)
    expect(payloads.get(layer)!.features.every((f) => f.properties.kind === kind && f.geometry.type === geometry)).toBe(true)
  }
  await expect(page.getByText('正在读取当前视野的机场与图层…')).not.toBeVisible()
  await map.screenshot({ path: 'test-results/live-new-york-all-layers.png' })
})
