import { defineConfig, devices } from '@playwright/test';

const externalURL = process.env.DEARLY_E2E_BASE_URL;
export default defineConfig({
  testDir: './e2e', testMatch: '**/*.pw.ts', workers: 1, retries: 0,
  use: { baseURL: externalURL ?? 'http://127.0.0.1:8000', screenshot: 'only-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
  webServer: externalURL ? undefined : {
    command: 'python ../backend/run.py --db ../backend/data/e2e.sqlite3 serve',
    url: 'http://127.0.0.1:8000/health', reuseExistingServer: false,
  },
});
