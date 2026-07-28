/**
 * E2E Regression Test: #480 — Session content loads on startup
 *
 * Verifies:
 *   1. After creating a session with messages, restarting the app
 *      shows the last session's message history immediately —
 *      without needing to switch sessions and switch back.
 *   2. Bridge-unready retry logic in ChatConsole.load() works:
 *      exponential-backoff retries allow messages to appear once
 *      the bridge becomes ready, rather than permanently showing
 *      the empty welcome screen.
 *
 * Run:
 *   cd apps/desktop
 *   npx playwright test --config=playwright.config.ts --project=electron -g "regression-480"
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  APPS_DESKTOP,
  LLM_TIMEOUT,
  waitForInputReady,
  sendMessage,
  waitForResponseComplete,
  getSessionTitle,
  launchElectronApp,
  closeElectronApp,
  waitForBridgeInitialized,
  createNewConversation,
  switchToSessionWithMarker,
} from './helpers/electron-setup';

// ─── Test Suite ───────────────────────────────────────────────────

test.describe('Regression #480: Session loads on startup', () => {
  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome).catch(() => {});
  });

  // ═══════════════════════════════════════════════════════════════
  //  Test 1: First launch → create session → restart → history visible
  // ═══════════════════════════════════════════════════════════════

  test(
    'session history visible on restart without switching sessions',
    { timeout: LLM_TIMEOUT * 3 },
    async () => {
      // ── Phase 1: First launch, create a session with known content ──
      const fixture = await launchElectronApp();
      electronApp = fixture.electronApp;
      page = fixture.page;
      miqiHome = fixture.miqiHome;

      await waitForBridgeInitialized(page);
      await page.evaluate(() =>
        (window as any).miqi.approvals.addPermanent('*:*', 'always'),
      );

      const marker = `REG480_${Date.now()}`;
      await sendMessage(page, `只回答${marker}`);
      await waitForResponseComplete(page, 240_000);

      // Confirm marker is visible in the current session
      await expect(
        page.locator('main').getByText(marker, { exact: false }).first(),
      ).toBeVisible({ timeout: 10_000 });
      console.log(`[test] ✅ Phase 1: Created session with marker "${marker}"`);

      // ── Phase 2: Close and relaunch with same MIQI_HOME ──
      await closeElectronApp(electronApp, miqiHome);
      await new Promise((r) => setTimeout(r, 3000));

      const env: Record<string, string | undefined> = { ...process.env };
      env.MIQI_HOME = miqiHome;
      delete env.ELECTRON_RUN_AS_NODE;

      const app2 = await electron.launch({
        args: [APPS_DESKTOP],
        executablePath: require('electron') as string,
        env: env as Record<string, string>,
        chromiumSandbox: false,
      });

      let page2: Page | undefined;
      for (let i = 0; i < 100; i++) {
        const windows = app2.windows();
        for (const w of windows) {
          try {
            const info = await w.evaluate(() => ({
              t: document.title,
              w: window.outerWidth,
            }));
            if (info.w > 500 && info.t === 'MiQi Desktop') {
              page2 = w;
              break;
            }
          } catch {
            /* window may not be ready yet */
          }
        }
        if (page2) break;
        await new Promise((r) => setTimeout(r, 100));
      }
      if (!page2) page2 = await app2.firstWindow();
      await page2.waitForLoadState('domcontentloaded');

      // ── Phase 3: Wait for the app to load ──────────────────────────
      // The key assertion: the retry logic in ChatConsole.load() should
      // have fetched session history even if the bridge was not immediately
      // ready. Wait for input to be ready, then check for the marker.
      try {
        await page2.getByText('MiQi Workbench').waitFor({ timeout: 30_000 });
      } catch {
        console.log('[test] App UI may still be loading — continuing');
      }
      await waitForInputReady(page2, 60_000);

      // Give the retry logic time to complete (max ~9s for full backoff)
      await page2.waitForTimeout(12_000);

      // ── Phase 4: Verify marker is visible WITHOUT session switching ──
      const markerVisible = await page2
        .locator('main')
        .getByText(marker, { exact: false })
        .first()
        .isVisible({ timeout: 10_000 })
        .catch(() => false);

      if (!markerVisible) {
        // Dump diagnostic info before failing
        const mainText = await page2.locator('main').textContent().catch(() => '(error)');
        const titleText = await getSessionTitle(page2)
          .textContent()
          .catch(() => '(error)');
        console.log('[test] DIAGNOSTIC: Session title:', titleText);
        console.log(
          '[test] DIAGNOSTIC: Main text (last 500 chars):',
          (mainText || '').slice(-500),
        );
        // Check if the loading spinner is gone (historyLoaded should be true)
        const hasSpinner = await page2
          .locator('.animate-spin')
          .first()
          .isVisible()
          .catch(() => false);
        console.log('[test] DIAGNOSTIC: Loading spinner visible:', hasSpinner);
      }

      expect(markerVisible).toBe(true);
      console.log(
        `[test] ✅ Phase 3: History loaded after restart — marker "${marker}" visible without session switch`,
      );

      // Clean up the second app instance
      await closeElectronApp(app2).catch(() => {});
      // Don't double-close miqiHome — set electronApp to dummy so afterAll no-ops
      electronApp = app2;
      miqiHome = '';
    },
  );

  // ═══════════════════════════════════════════════════════════════
  //  Test 2: Sidebar session switch loads history (was FIXME-skipped)
  // ═══════════════════════════════════════════════════════════════

  test(
    'sidebar switch back loads history after #480 fix',
    { timeout: LLM_TIMEOUT * 2 },
    async () => {
      const fixture = await launchElectronApp();
      electronApp = fixture.electronApp;
      page = fixture.page;
      miqiHome = fixture.miqiHome;

      await waitForBridgeInitialized(page);
      await page.evaluate(() =>
        (window as any).miqi.approvals.addPermanent('*:*', 'always'),
      );

      // Create first session with known marker
      const marker = `SW_${Date.now()}`;
      await sendMessage(page, `只回答${marker}`);
      await waitForResponseComplete(page, 240_000);

      // Create a second session so we have something to switch from
      await createNewConversation(page);

      // Switch back to the first session via sidebar
      const found = await switchToSessionWithMarker(page, marker);
      expect(found).toBe(true);

      // Marker should be visible in the main chat area
      await expect(
        page.locator('main').getByText(marker, { exact: false }).first(),
      ).toBeVisible({ timeout: 15_000 });

      console.log(
        `[test] ✅ Sidebar switch back loaded history — marker "${marker}" visible`,
      );
    },
  );
});
