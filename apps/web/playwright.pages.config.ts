import { defineConfig } from '@playwright/test'

const remote = process.env.FLIGHTMAP_PAGES_URL
export default defineConfig({
  testDir: './e2e', testMatch: '**/pages.spec.ts', fullyParallel: false,
  outputDir: './test-results/pages', timeout: 60000,
  expect: { timeout: 15000 },
  use: { baseURL: remote || 'http://127.0.0.1:5175/flight-map/', viewport: { width: 1440, height: 1000 }, trace: 'retain-on-failure' },
  webServer: remote ? undefined : {
    command: 'npm run preview -- --host 127.0.0.1 --port 5175 --strictPort',
    url: 'http://127.0.0.1:5175/flight-map/', reuseExistingServer: !process.env.CI,
  },
})
