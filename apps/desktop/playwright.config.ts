import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/smoke',
  testMatch: '**/*.spec.ts',
  testIgnore: '**/*.test.ts',  // Exclude vitest files from Playwright scan
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: 'html',
  timeout: 30000,
  use: {
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  // ---- Projects -----------------------------------------------------------
  projects: [
    // ① Smoke tests: mock bridge → runs in Chromium browser
    {
      name: 'smoke',
      testMatch: 'smoke.spec.ts',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: 'http://localhost:3458',
        headless: false,
      },
    },
    // ② Electron E2E: launches real desktop app via _electron.launch()
    {
      name: 'electron',
      testMatch: ['full-electron.spec.ts'],
      use: {
        // Electron tests manage their own launch; no browser device needed
        headless: false,
      },
    },
  ],

  // ---- webServer (only needed by smoke project) ---------------------------
  webServer: {
    command: 'python -m http.server 3458 --directory out/renderer',
    url: 'http://localhost:3458',
    reuseExistingServer: false,
  },
});
