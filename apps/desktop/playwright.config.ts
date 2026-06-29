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
        headless: true,  // CI runs headless; use --headed locally
      },
    },
    // ② Electron E2E: launches real desktop app via CDP connection
    //    Electron 34+ removed --remote-debugging-port CLI flag, so we use
    //    app.commandLine.appendSwitch() + chromium.connectOverCDP() instead.
    {
      name: 'electron',
      testMatch: ['full-electron.spec.ts'],
      timeout: 300000,  // 5 min — Electron boot + bridge + LLM are slow
      use: {
        // Tests manage their own Electron process and CDP connection
        // No browser device config needed — connectOverCDP handles it
      },
    },
  ],

  // ---- webServer (only needed by smoke project) ---------------------------
  webServer: {
    command: 'python -m http.server 3458 --directory out/renderer',
    url: 'http://localhost:3458',
    reuseExistingServer: true,
  },
});
