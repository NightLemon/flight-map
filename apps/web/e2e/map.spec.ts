import { readFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'
import { airport, researchSnapshot, status } from '../tests/fixtures'

// Synthetic colors only; the opt-in real suite verifies actual OSM map imagery.
const tile = readFileSync(new URL('../tests/fixtures/synthetic-basemap.png', import.meta.url))
const snapshot = researchSnapshot()

async function airportRoutes(page: Page, featureRequests: URL[]) {
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/status')) {
      await route.fulfill({ json: status({ current_releases: {}, research: {
        current_time: '2026-09-08T00:00:00Z', active_snapshots: { nasr: snapshot }, snapshots: [snapshot],
        attempts: [], storage_errors: [], disclaimer: 'SYNTHETIC TEST ONLY',
      } }) })
    } else if (url.pathname.endsWith('/features')) {
      featureRequests.push(url)
      const features = Array.from({ length: 12 }, (_, index) => ({
        type: 'Feature', id: `synthetic-cluster-${index}`,
        geometry: { type: 'Point', coordinates: [-98 + (index - 5.5) * 0.001, 39] },
        properties: { id: `synthetic-cluster-${index}`, identifier: `T${index}`, kind: 'airport',
          name: 'SYNTHETIC CLUSTER AIRPORT', snapshot_id: snapshot.id, provenance: airport.provenance },
      }))
      await route.fulfill({ json: { type: 'FeatureCollection', features, snapshot_id: snapshot.id, mode: 'active', truncated: false } })
    } else if (url.pathname.endsWith('/coverage') || url.pathname.endsWith('/sources')) {
      await route.fulfill({ json: [] })
    } else throw new Error(`Unmocked map request ${url}`)
  })
}

test('overview does not fetch airports; local points cluster, expand and disappear on zoom-out', async ({ page }) => {
  const requested: URL[] = []
  await airportRoutes(page, requested)
  await page.route('https://tile.openstreetmap.org/**', (route) => route.fulfill({ body: tile, contentType: 'image/png' }))
  await page.goto('/')
  const map = page.getByLabel('航空资料地图', { exact: true })
  await expect(map).toHaveAttribute('data-basemap-state', 'ready')
  await expect(page.getByText('放大地图查看附近机场，或搜索机场直接定位')).toBeVisible()
  await expect(page.getByRole('link', { name: /OpenStreetMap/ })).toBeVisible()
  // Observe beyond the request debounce so this catches an accidental initial world query.
  await page.waitForTimeout(350)
  expect(requested).toHaveLength(0)
  await expect(map).toHaveAttribute('data-feature-count', '0')
  for (let step = 1; step <= 5; step++) {
    await page.getByRole('button', { name: 'Zoom in', exact: true }).click()
    await expect.poll(async () => Number(await map.getAttribute('data-zoom'))).toBeCloseTo(3.25 + step, 1)
    if (step < 5) expect(requested).toHaveLength(0)
  }
  await expect(map).toHaveAttribute('data-feature-count', '12')
  await expect.poll(async () => Number(await map.getAttribute('data-cluster-count'))).toBeGreaterThan(0)
  expect(requested[0].searchParams.get('limit')).toBe('500')
  expect(requested[0].searchParams.get('bbox')).not.toBe('-180,-90,180,90')
  await map.screenshot({ path: 'test-results/map-cluster-synthetic.png' })
  const box = (await map.boundingBox())!
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2)
  await expect.poll(async () => Number(await map.getAttribute('data-zoom'))).toBeGreaterThanOrEqual(10)
  await expect(map).toHaveAttribute('data-cluster-count', '0')
  while (Number(await map.getAttribute('data-zoom')) >= 8) {
    const before = Number(await map.getAttribute('data-zoom'))
    await page.getByRole('button', { name: 'Zoom out', exact: true }).click()
    await expect.poll(async () => Number(await map.getAttribute('data-zoom'))).toBeLessThan(before - 0.9)
  }
  await expect(map).toHaveAttribute('data-feature-count', '0')
  const countAfterZoomOut = requested.length
  await page.waitForTimeout(350)
  expect(requested).toHaveLength(countAfterZoomOut)
})

test('unavailable base tiles leave airport controls and API connection usable', async ({ page }) => {
  const requested: URL[] = []
  await airportRoutes(page, requested)
  await page.route('https://tile.openstreetmap.org/**', (route) => route.abort())
  await page.goto('/')
  const map = page.getByLabel('航空资料地图', { exact: true })
  await expect(map).toHaveAttribute('data-basemap-state', 'error')
  await expect(page.getByText('API 已连接')).toBeVisible()
  await expect(page.getByRole('textbox', { name: /搜索机场/ })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Zoom in', exact: true })).toBeEnabled()
  await expect(map).toHaveAttribute('data-feature-count', '0')
  expect(requested).toHaveLength(0)
})

test('enabled line and point layers render; clicking a runway retrieves its original record', async ({ page }) => {
  const snapshot2 = researchSnapshot({ schema_version: 'research-2', capabilities: ['airports', 'runways', 'navaids', 'waypoints', 'airways', 'communications'] })
  const runway = { ...airport, id: 'synthetic-runway', kind: 'runway', identifier: '04/22', name: 'SYNTHETIC RUNWAY', geometry: { type: 'LineString', coordinates: [[-98.03, 39], [-97.97, 39]] } }
  const requested: string[] = []
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route('https://tile.openstreetmap.org/**', (route) => route.fulfill({ body: tile, contentType: 'image/png' }))
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    const envelope = { snapshot_id: snapshot2.id, mode: 'active', disclaimer: 'SYNTHETIC ONLY' }
    if (url.pathname.endsWith('/status')) return route.fulfill({ json: status({ current_releases: {}, research: { current_time: '2026-09-08T00:00:00Z', active_snapshots: { nasr: snapshot2 }, snapshots: [snapshot2], attempts: [], storage_errors: [], disclaimer: 'SYNTHETIC ONLY' } }) })
    if (url.pathname.endsWith('/coverage') || url.pathname.endsWith('/sources')) return route.fulfill({ json: [] })
    if (url.pathname.endsWith('/features')) {
      const layer = url.searchParams.get('layer')!
      requested.push(layer)
      const features = layer === 'airports' ? [] : [{ type: 'Feature',
        geometry: layer === 'runways' ? runway.geometry : layer === 'airways' ? { type: 'LineString', coordinates: [[-98.02, 38.98], [-97.98, 38.98]] } : { type: 'Point', coordinates: [-98, layer === 'navaids' ? 39.02 : 39.04] },
        properties: { id: layer === 'runways' ? runway.id : layer, identifier: layer === 'runways' ? '04/22' : layer, kind: { runways: 'runway', airways: 'airway', navaids: 'navaid', waypoints: 'waypoint' }[layer], name: 'SYNTHETIC ONLY', snapshot_id: snapshot2.id, provenance: airport.provenance },
      }]
      return route.fulfill({ json: { ...envelope, type: 'FeatureCollection', features } })
    }
    if (url.pathname.endsWith('/records/synthetic-runway')) return route.fulfill({ json: { ...envelope, record: runway } })
    throw new Error(`Unmocked layer request ${url}`)
  })
  await page.goto('/')
  await expect(page.getByText('API 已连接')).toBeVisible()
  for (const label of ['跑道', '导航台', '航点', '航路']) await page.getByRole('checkbox', { name: new RegExp(label) }).check()
  await page.waitForTimeout(350)
  expect(requested).toHaveLength(0)
  const map = page.getByLabel('航空资料地图', { exact: true })
  for (let step = 1; step <= 7; step++) {
    await page.getByRole('button', { name: 'Zoom in', exact: true }).click()
    await expect.poll(async () => Number(await map.getAttribute('data-zoom'))).toBeCloseTo(3.25 + step, 1)
  }
  await expect(map).toHaveAttribute('data-feature-count', '4')
  const box = (await map.boundingBox())!
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2)
  await expect(page.getByRole('heading', { name: '04/22', exact: true })).toBeVisible()
  await expect(page.getByText('SYNTHETIC RUNWAY', { exact: true })).toBeVisible()
  await expect(map).toHaveAttribute('data-zoom', '10.25')
  await map.screenshot({ path: 'test-results/map-all-layers-synthetic.png' })
  expect(errors).toEqual([])
})

test('narrow map supports Ctrl + wheel zoom and airport loading while ordinary wheel scrolls the page', async ({ page }) => {
  await page.setViewportSize({ width: 519, height: 642 })
  const requested: URL[] = []
  await airportRoutes(page, requested)
  await page.route('https://tile.openstreetmap.org/**', (route) => route.fulfill({ body: tile, contentType: 'image/png' }))
  await page.goto('/')
  const map = page.getByLabel('航空资料地图', { exact: true })
  const shell = page.getByRole('main', { name: '研究工作区' })
  await expect(page.getByText('API 已连接')).toBeVisible()
  for (let step = 1; step <= 4; step++) {
    await page.getByRole('button', { name: 'Zoom in', exact: true }).click()
    await expect.poll(async () => Number(await map.getAttribute('data-zoom'))).toBeCloseTo(3.25 + step, 1)
  }
  expect(requested).toHaveLength(0)
  let box = (await map.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  const beforeScroll = await shell.evaluate((el) => el.scrollTop)
  await page.mouse.wheel(0, 100)
  await expect.poll(() => shell.evaluate((el) => el.scrollTop)).toBeGreaterThan(beforeScroll)
  await expect(map).toHaveAttribute('data-zoom', '7.25')
  box = (await map.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.keyboard.down('Control')
  await page.mouse.wheel(0, -600)
  await expect.poll(async () => Number(await map.getAttribute('data-zoom'))).toBeGreaterThan(7.5)
  await page.mouse.wheel(0, -600)
  await page.keyboard.up('Control')
  await expect.poll(async () => Number(await map.getAttribute('data-zoom'))).toBeGreaterThanOrEqual(8)
  await expect(map).toHaveAttribute('data-feature-count', '12')
  expect(requested.length).toBeGreaterThan(0)
})
