import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/smoke',
  testMatch: '**/*.spec.ts',
  testIgnore: '**/*.test.ts',  // Exclude vitest files from Playwright scan
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [
    ['html', { outputFolder: 'test-reports/html', open: 'never' }],
    ['json', { outputFile: 'test-reports/results.json' }],
  ],
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
      testMatch: ['smoke.spec.ts', 'issue-*.spec.ts', 'logs.spec.ts'],
      use: {
        ...devices['Desktop Chrome'],
        baseURL: 'http://localhost:3458',
        headless: true,  // CI runs headless; use --headed locally
      },
    },
    // ② Electron E2E: launches real desktop app via _electron.launch()
    //    Playwright 1.58+ (PR #39012) fixed the Electron 34 compatibility
    //    issue by switching from CLI flag to appendSwitch().
    {
      name: 'electron',
      testDir: './tests/e2e',
      testMatch: ['full-electron.spec.ts', 'approval-persistence.spec.ts'],
      timeout: 600_000,  // 10 min — pptx-generator + LLM can be slow
    },
  ],

  // ---- webServer (only needed by smoke project) ---------------------------
  webServer: {
    command: 'python -m http.server 3458 --directory out/renderer',
    url: 'http://localhost:3458',
    reuseExistingServer: true,
  },
});
