// Opt-in live smoke test. Requires a published real d-TPP release in the local API.
// Run with FLIGHTMAP_LIVE=1; ordinary CI uses the isolated synthetic browser tests.
import { expect, test } from '@playwright/test'

for (const identifier of ['SEA', 'JFK']) {
  test(`real d-TPP ${identifier} airport catalog → official PDF`, async ({ page, request }) => {
    const response = await request.get('/api/v1/status')
    expect(response.ok()).toBe(true)
    const snapshot = await response.json()
    expect(snapshot.current_releases.dtpp?.id).toBeTruthy()
    const consoleErrors: string[] = []
    page.on('pageerror', (error) => consoleErrors.push(error.message))
    await page.goto('/')
    await expect(page.getByText('API 已连接')).toBeVisible()
    await page.getByRole('textbox', { name: /搜索机场/ }).fill(identifier)
    await page.getByRole('button', { name: '搜索', exact: true }).click()
    const results = page.getByLabel('搜索结果')
    await results.getByRole('button').filter({ hasText: 'DTPP' }).filter({ has: page.locator('strong', { hasText: new RegExp(`^${identifier}$`) }) }).first().click()
    const chartPanel = page.getByLabel('官方航图', { exact: true })
    await expect(chartPanel.locator('.choice')).not.toHaveCount(0)
    await chartPanel.locator('.choice').first().click()
    const official = page.getByRole('link', { name: /FAA 官方网站/ })
    await expect(official).toHaveAttribute('href', /^https:\/\/[^/]*faa\.gov\/.+\.pdf$/i)
    await expect(official).toBeVisible()
    await expect(page.locator('iframe')).toBeVisible()
    await expect(page.getByText('正在加载 PDF…')).not.toBeVisible({ timeout: 20000 })
    await page.screenshot({ path: `test-results/live-${identifier.toLowerCase()}.png`, fullPage: true })
    expect(consoleErrors).toEqual([])
  })
}
