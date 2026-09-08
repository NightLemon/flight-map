import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
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

test('country browsing loads only the selected search shard and finds international airports', async ({ page }) => {
  const requests: string[] = []
  page.on('request', (request) => requests.push(request.url()))
  await page.goto('./')
  const country = page.getByLabel('限定机场搜索的国家或地区')
  await country.selectOption('CN')
  await expect(page.getByLabel('机场搜索结果').getByRole('button', { name: /ZBAA/ }).first()).toBeVisible()
  expect(requests.some((url) => /reference\/[a-f0-9]{40}\/search\/CN\.json/.test(url))).toBe(true)
  await search(page, 'ZBAA')
  await country.selectOption('IN')
  await search(page, 'VIDP')
  await expect(page.getByRole('heading', { name: 'VIDP', exact: true })).toBeVisible()
  expect(requests.some((url) => /reference\/[a-f0-9]{40}\/search\/IN\.json/.test(url))).toBe(true)
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
    await route.fulfill({ json: { ...value, dataset_revision: 'b'.repeat(40), source: { ...value.source, revision: 'b'.repeat(40) }, tiles: { airports: [], runways: [], navaids: [] } } })
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

test('reviewed export preserves source values and excludes closed runway geometry from map tiles', async ({ request }) => {
  const manifestResponse = await request.get('reference/manifest.json')
  expect(manifestResponse.ok()).toBe(true)
  const manifest = await manifestResponse.json()
  const root = `reference/${manifest.dataset_revision}`
  const reviewBytes = readFileSync(new URL('../../../reference-sources/ourairports-review.json', import.meta.url))
  expect(manifest.review.sha256).toBe(createHash('sha256').update(reviewBytes).digest('hex'))
  const reviewResponse = await request.get(`${root}/review.json`)
  expect(reviewResponse.ok()).toBe(true)
  expect(await reviewResponse.json()).toEqual(JSON.parse(reviewBytes.toString('utf-8')))
  const detail = async (id: number) => {
    const response = await request.get(`${root}/airports/${id % 256}.json`)
    expect(response.ok()).toBe(true)
    return (await response.json())[`ourairports:airport:${id}`]
  }
  const bozhou = await detail(525151)
  expect(bozhou.airport.name).toBe('Bozhou Airport')
  expect(bozhou.airport.properties.original_name).toBe('Bozhou Airport (under construction)')
  expect(bozhou.airport.properties.scheduled_service).toBe('no')
  expect(bozhou.communications).toEqual([])
  expect(bozhou.runways).toEqual([])
  expect(bozhou.review_notes.some((note: { status: string; field: string }) => note.status === 'corrected' && note.field === 'name')).toBe(true)
  const cnResponse = await request.get(`${root}/search/CN.json`)
  expect(cnResponse.ok()).toBe(true)
  const cn = await cnResponse.json()
  expect(cn.find((airport: { id: string }) => airport.id === bozhou.airport.id).name).toBe('Bozhou Airport')
  expect(cn.some((airport: { id: string }) => airport.id === 'ourairports:airport:27224')).toBe(false)

  for (const [airportId, runwayId] of [[27224, 235198], [27189, 235184]]) {
    const airport = await detail(airportId)
    const runway = airport.runways.find((item: { id: string }) => item.id === `ourairports:runway:${runwayId}`)
    expect(runway).toBeDefined() // Source history and geometry remain available in detail.
    expect(runway.geometry.type).toBe('LineString')
    const [longitude, latitude] = runway.geometry.coordinates[0]
    const tile = `${Math.floor((longitude + 180) / 5)}-${Math.floor((latitude + 90) / 5)}`
    if (manifest.tiles.runways.includes(tile)) {
      const response = await request.get(`${root}/tiles/runways/${tile}.json`)
      expect(response.ok()).toBe(true)
      const features = (await response.json()).features
      expect(features.some((item: { id: string }) => item.id === runway.id)).toBe(false)
    }
  }
  const wuhai = await detail(308728)
  expect(wuhai.navigation_frequencies).toHaveLength(3)
  expect(wuhai.navigation_frequencies.find((item: { properties: { service: string } }) => item.properties.service === 'GP 19').properties.frequency).toBe('329.3')
  expect(wuhai.communications.every((item: { properties: { frequency_category: string } }) => item.properties.frequency_category === 'communication')).toBe(true)
  const ordos = await detail(300513)
  expect(ordos.navigation_frequencies).toHaveLength(5)
  expect(manifest.counts.communications + manifest.counts.navigation_frequencies + manifest.counts.unclassified_frequencies).toBe(manifest.source_counts.communications)
})

test('airport review details distinguish corrected names, missing data and navigation frequencies', async ({ page }) => {
  await page.goto('./')
  await search(page, 'CN-0413')
  await expect(page.locator('.entity-name')).toContainText('Bozhou Airport')
  await expect(page.locator('.entity-name')).not.toContainText('under construction')
  await expect(page.getByLabel('机场概览')).toContainText('ZSBO')
  await expect(page.getByLabel('机场通信频率')).toContainText('来源未收录语音通信频率')
  await expect(page.getByLabel('资料核查记录')).toBeAttached()
  await expect(page.getByLabel('资料完整性')).toBeAttached()
  await search(page, 'ZBUH')
  await expect(page.getByLabel('导航频率参考')).toContainText('329.3')
  await expect(page.getByLabel('机场通信频率')).not.toContainText('329.3')
  await search(page, 'ZBHH')
  await expect(page.getByLabel('跑道', { exact: true })).toContainText('来源标为关闭')
})

test.describe('phone map gestures', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })

  test('one finger pans and two fingers zoom without the cooperative gesture overlay', async ({ page, context }) => {
    await page.goto('./')
    const map = page.getByLabel('航空资料地图', { exact: true })
    await expect(map).toHaveAttribute('data-basemap-state', 'ready')
    const box = (await map.boundingBox())!
    const x = box.x + box.width / 2, y = box.y + box.height / 2
    const beforeLongitude = Number(await map.getAttribute('data-longitude'))
    const session = await context.newCDPSession(page)
    const touch = (type: 'touchStart' | 'touchMove' | 'touchEnd', points: Array<{ x: number; y: number; id: number }>) =>
      session.send('Input.dispatchTouchEvent', { type, touchPoints: points })
    try {
      await touch('touchStart', [{ x, y, id: 0 }])
      for (let step = 1; step <= 8; step++) {
        await touch('touchMove', [{ x: x + step * 9, y, id: 0 }])
        // Model a continuous gesture across animation frames, not a DOM event stub.
        await page.waitForTimeout(20)
      }
      await touch('touchEnd', [])
      await expect.poll(async () => Math.abs(Number(await map.getAttribute('data-longitude')) - beforeLongitude)).toBeGreaterThan(0.1)
      await expect(page.locator('.maplibregl-cooperative-gesture-screen')).toHaveCount(0)

      const beforeZoom = Number(await map.getAttribute('data-zoom'))
      await touch('touchStart', [{ x: x - 25, y, id: 0 }, { x: x + 25, y, id: 1 }])
      for (let step = 1; step <= 8; step++) {
        const gap = 25 + step * 7
        await touch('touchMove', [{ x: x - gap, y, id: 0 }, { x: x + gap, y, id: 1 }])
        await page.waitForTimeout(20)
      }
      await touch('touchEnd', [])
      await expect.poll(async () => Number(await map.getAttribute('data-zoom'))).toBeGreaterThan(beforeZoom + 0.3)
      await expect(page.locator('.maplibregl-cooperative-gesture-screen')).toHaveCount(0)
    } finally {
      await session.detach()
    }
  })
})
