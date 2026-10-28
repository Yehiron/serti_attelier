import { defineConfig, devices } from '@playwright/test';

/**
 * Browser end-to-end tests against the running dev stack (`make up`).
 * Each purchase test creates its own unique piece, so runs never deplete the catalog.
 * Run with `make e2e` (or `npx playwright test` from frontend/).
 */
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8090',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    locale: 'es-CO',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
});
