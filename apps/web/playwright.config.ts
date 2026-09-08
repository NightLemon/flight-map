import { defineConfig } from '@playwright/test'

const live = process.env.FLIGHTMAP_LIVE === '1'
const port = live ? 5173 : 5174

export default defineConfig({
  testDir: './e2e', fullyParallel: false,
  outputDir: live ? './test-results/live-run' : './test-results/mock-run',
  testMatch: live ? '**/live.spec.ts' : '**/research.spec.ts',
  use: { baseURL: `http://127.0.0.1:${port}`, viewport: { width: 1440, height: 1000 }, trace: 'retain-on-failure' },
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${port} --strictPort`,
    url: `http://127.0.0.1:${port}`, reuseExistingServer: !process.env.CI,
  },
})
