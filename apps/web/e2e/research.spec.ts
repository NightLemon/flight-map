import { expect, test } from '@playwright/test'
import { airport, chart, geometry, legs, procedure, release, status } from '../tests/fixtures'

test('search → program branch → PDF, then publication replacement clears the desk', async ({ page }) => {
  let unavailable = false
  const requested: string[] = []
  await page.route('https://aeronav.faa.gov/**', (route) => route.abort())
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    requested.push(url.pathname + url.search)
    const envelope = { release_id: url.searchParams.get('release_id'), mode: url.searchParams.get('mode') }
    let payload: unknown
    if (url.pathname.endsWith('/status')) payload = unavailable ? status({ current_releases: {}, publication_state: 'empty' }) : status()
    else if (url.pathname.endsWith('/coverage') || url.pathname.endsWith('/sources')) payload = []
    else if (url.pathname.endsWith('/features')) payload = { ...envelope, type: 'FeatureCollection', features: [{ type: 'Feature', geometry: airport.geometry, properties: { ...airport.properties, id: airport.id, identifier: airport.identifier, name: airport.name, kind: 'airport', release_id: envelope.release_id, provenance: airport.provenance } }] }
    else if (url.pathname.endsWith('/search')) payload = { ...envelope, items: envelope.release_id === release('nasr').id ? [airport] : [] }
    else if (url.pathname.endsWith('/charts')) payload = { ...envelope, items: [chart] }
    else if (url.pathname.endsWith('/airports/KZZZ/procedures')) payload = { ...envelope, items: [procedure] }
    else if (url.pathname.endsWith('/geometry')) payload = geometry(url.searchParams.get('branch_id') ?? '')
    else if (url.pathname.includes('/procedures/')) payload = { ...envelope, record: procedure, legs, branches: ['BRANCH A', 'BRANCH B'] }
    else throw new Error(`Unmocked route ${url}`)
    await route.fulfill({ json: payload })
  })
  await page.goto('/')
  await expect(page.getByText('API 已连接')).toBeVisible()
  await page.getByRole('textbox', { name: /搜索机场/ }).fill('ZZZ')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await page.getByLabel('搜索结果').getByRole('button', { name: /SYNTHETIC TEST AIRPORT/ }).click()
  await page.getByRole('button', { name: /SYNTHETIC SID/ }).click()
  await page.getByRole('combobox', { name: '程序分支' }).selectOption('BRANCH A')
  await expect(page.getByText(/几何缺口 · Unsupported RF leg/)).toBeVisible()
  await page.getByRole('button', { name: /SYNTHETIC DEPARTURE CHART/ }).click()
  await expect(page.getByRole('link', { name: /FAA 官方网站/ })).toHaveAttribute('target', '_blank')
  await expect(page.getByRole('link', { name: /FAA 官方网站/ })).toBeVisible()
  await expect(page.getByTitle('官方航图 SYNTHETIC DEPARTURE CHART')).toBeVisible()
  await page.screenshot({ path: 'test-results/research-desktop.png', fullPage: true })
  expect(requested.filter((url) => url.includes('/geometry')).every((url) => url.includes('branch_id=BRANCH+A') && url.includes(`release_id=${release('cifp').id}`))).toBe(true)
  unavailable = true
  await page.getByRole('button', { name: '重新检查', exact: true }).click()
  await expect(page.getByText('尚无已验证的当前资料')).toBeVisible()
  await expect(page.getByTitle('官方航图 SYNTHETIC DEPARTURE CHART')).toHaveCount(0)
  await expect(page.getByText('SYNTHETIC TEST AIRPORT')).toHaveCount(0)
})

test('offline API leaves reference map and retry action without sample aviation data', async ({ page }) => {
  await page.route('**/api/v1/**', (route) => route.abort('internetdisconnected'))
  await page.goto('/')
  await expect(page.getByText('API 未连接')).toBeVisible()
  await expect(page.getByText('尚无已验证的当前资料')).toBeVisible()
  await expect(page.getByRole('button', { name: '重试', exact: true })).toBeVisible()
  await expect(page.getByLabel('搜索结果')).toHaveCount(0)
  await page.screenshot({ path: 'test-results/empty-desktop.png', fullPage: true })
})
