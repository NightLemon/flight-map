// Opt-in real FAA verification. Ordinary CI uses only the synthetic browser suite.
import { expect, test } from '@playwright/test'

const cases = [
  { identifier: 'SEA', query: 'SEA', title: 'ILS OR LOC RWY 16C', filename: '00582IL16C.PDF' },
  { identifier: 'JFK', query: 'KJFK', title: 'VOR OR GPS RWY 13L/R', filename: '00610VG13LR.PDF' },
]

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
    page.on('pageerror', (error) => consoleErrors.push(error.message))
    page.on('response', (res) => { if (res.url().includes('/pdf?')) pdfHeaders.push(res.headers()) })
    await page.goto('/')
    await expect(page.getByText('API 已连接')).toBeVisible()
    await page.getByRole('textbox', { name: /搜索机场/ }).fill(query)
    await page.getByRole('button', { name: '搜索', exact: true }).click()
    const results = page.getByLabel('搜索结果')
    await results.getByRole('button').filter({ hasText: 'NASR' }).filter({ has: page.locator('strong', { hasText: new RegExp(`^${identifier}$`) }) }).first().click()
    const map = page.getByLabel('航空资料地图', { exact: true })
    await expect(map).toHaveAttribute('data-zoom', '10')
    await expect.poll(async () => Number(await map.getAttribute('data-feature-count')), { timeout: 15000 }).toBeGreaterThan(0)
    expect(Number(await map.getAttribute('data-latitude'))).toBeCloseTo(airport.geometry.coordinates[1], 6)
    expect(Number(await map.getAttribute('data-longitude'))).toBeCloseTo(airport.geometry.coordinates[0], 6)
    // Closing and clicking the rendered center point must reopen the real airport record.
    await page.getByRole('button', { name: '关闭', exact: true }).click()
    const mapBox = (await map.boundingBox())!
    await page.mouse.click(mapBox.x + mapBox.width / 2, mapBox.y + mapBox.height / 2)
    await expect(page.getByRole('heading', { name: identifier, exact: true })).toBeVisible()
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
    expect(pdfHeaders[0]['x-flightmap-release-id']).toBe(status.current_releases.dtpp.id)
    expect(pdfHeaders[0]['x-flightmap-pdf-sha256']).toMatch(/^[a-f0-9]{64}$/)
    await canvas.screenshot({ path: `test-results/live-${identifier.toLowerCase()}-pdf.png` })
    await page.screenshot({ path: `test-results/live-${identifier.toLowerCase()}.png`, fullPage: true })
    expect(consoleErrors).toEqual([])
  })
}
