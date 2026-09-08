import { readFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'

// Only the background imagery is synthetic; reference data is the real pinned export.
const tile = readFileSync(new URL('../tests/fixtures/synthetic-basemap.png', import.meta.url))

async function search(page: Page, code: string) {
  await page.getByRole('textbox', { name: '搜索机场', exact: true }).fill(code)
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await page.getByLabel('机场搜索结果').getByRole('button', { name: new RegExp(code) }).first().click()
  await expect(page.getByRole('heading', { name: code, exact: true })).toBeVisible()
  await expect(page.getByLabel('机场通信频率')).toBeVisible()
}

test.beforeEach(async ({ page }) => {
  await page.route('https://tile.openstreetmap.org/**', (route) => route.fulfill({ body: tile, contentType: 'image/png' }))
})

test('Pages loads without a backend, starts without data pins, and JFK shows frequencies', async ({ page }) => {
  const requests: string[] = []
  const failures: string[] = []
  page.on('request', (request) => requests.push(request.url()))
  page.on('response', (response) => { if (response.status() >= 400) failures.push(response.url()) })
  await page.goto('./')
  await expect(page.getByText('公开参考版 · OurAirports', { exact: true })).toBeVisible()
  await expect(page.getByText('放大至 Z8 查看机场，或直接搜索定位')).toBeVisible()
  const map = page.getByLabel('航空资料地图', { exact: true })
  await expect(map).toHaveAttribute('data-feature-count', '0')
  await page.waitForTimeout(300)
  expect(requests.filter((url) => /reference\/.*(?:tiles|airports|search)/.test(url))).toHaveLength(0)
  await search(page, 'KJFK')
  await expect(page.getByLabel('机场通信频率').getByText(/MHz/).first()).toBeVisible()
  await expect.poll(async () => Number(await map.getAttribute('data-feature-count'))).toBeGreaterThan(0)
  await expect.poll(async () => Number(await map.getAttribute('data-zoom'))).toBeGreaterThanOrEqual(10)
  await page.getByRole('button', { name: 'Zoom out', exact: true }).click()
  await expect.poll(async () => Number(await map.getAttribute('data-zoom'))).toBeLessThan(9.1)
  await search(page, 'KJFK')
  await expect.poll(async () => Number(await map.getAttribute('data-zoom'))).toBeGreaterThanOrEqual(10)
  // Click the airport at the actual map center, then check the same detail remains usable.
  const box = (await map.boundingBox())!
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2)
  await expect(page.getByRole('heading', { name: 'KJFK', exact: true })).toBeVisible()
  await expect(page.getByLabel('机场通信频率')).toBeVisible()
  expect(requests.some((url) => /\/api\/|127\.0\.0\.1:8000|localhost:8000/.test(url))).toBe(false)
  expect(failures).toEqual([])
  await page.screenshot({ path: 'test-results/pages-desktop.png', fullPage: true })
})

test('runway and navaid layers load on demand and all pins clear when layers are disabled', async ({ page }) => {
  const requests: string[] = []
  page.on('request', (request) => requests.push(request.url()))
  await page.goto('./')
  await search(page, 'KJFK')
  const map = page.getByLabel('航空资料地图', { exact: true })
  await expect.poll(async () => Number(await map.getAttribute('data-feature-count'))).toBeGreaterThan(0)
  await page.getByRole('checkbox', { name: /机场/ }).uncheck()
  await expect(map).toHaveAttribute('data-feature-count', '0')
  await page.getByRole('checkbox', { name: /跑道/ }).check()
  await expect.poll(async () => Number(await map.getAttribute('data-feature-count'))).toBeGreaterThan(0)
  expect(requests.some((url) => url.includes('/tiles/runways/'))).toBe(true)
  await page.getByRole('checkbox', { name: /跑道/ }).uncheck()
  await page.getByRole('checkbox', { name: /导航台/ }).check()
  await expect.poll(async () => Number(await map.getAttribute('data-feature-count'))).toBeGreaterThan(0)
  expect(requests.some((url) => url.includes('/tiles/navaids/'))).toBe(true)
  await page.getByRole('checkbox', { name: /导航台/ }).uncheck()
  await expect(map).toHaveAttribute('data-feature-count', '0')
})

test('a missing static manifest is reported and retry restores the page', async ({ page }) => {
  let fail = true
  await page.route('**/reference/manifest.json', (route) => fail ? route.fulfill({ status: 503, body: '{}' }) : route.continue())
  await page.goto('./')
  await expect(page.getByText(/参考数据读取失败/).first()).toBeVisible()
  fail = false
  await page.getByRole('button', { name: '重试', exact: true }).first().click()
  await expect(page.getByText('公开数据快照', { exact: true })).toBeVisible()
  await search(page, 'KSEA')
})

test('refreshing to a different data revision clears the previous airport details', async ({ page }) => {
  let changed = false
  await page.route('**/reference/manifest.json', async (route) => {
    if (!changed) { await route.continue(); return }
    const original = await route.fetch()
    const value = await original.json()
    // A synthetic replacement manifest checks version transitions without publishing a fake dataset.
    await route.fulfill({ json: { ...value, source: { ...value.source, revision: 'b'.repeat(40) }, tiles: { airports: [], runways: [], navaids: [] } } })
  })
  await page.goto('./')
  await search(page, 'KJFK')
  changed = true
  await page.locator('details.data-management > summary').click()
  await page.getByRole('button', { name: '重新读取', exact: true }).click()
  await expect(page.getByRole('heading', { name: '选择一个机场', exact: true })).toBeVisible()
  await expect(page.getByLabel('机场通信频率')).toHaveCount(0)
  await expect(page.getByLabel('航空资料地图', { exact: true })).toHaveAttribute('data-feature-count', '0')
})

test('mobile keeps the compact controls, map and airport frequencies reachable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('./')
  await expect(page.getByText('公开数据快照', { exact: true })).toBeAttached()
  const management = page.locator('details.data-management')
  await expect(management).not.toHaveAttribute('open', '')
  await search(page, 'KSEA')
  await page.getByLabel('机场通信频率').scrollIntoViewIfNeeded()
  await expect(page.getByLabel('机场通信频率').getByText(/MHz/).first()).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/pages-mobile.png', fullPage: true })
})
