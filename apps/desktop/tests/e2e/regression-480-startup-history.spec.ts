/**
 * E2E Regression Test: #480 — Session content loads on startup
 *
 * Verifies:
 *   1. After creating a session with messages, restarting the app
 *      shows the last session's message history immediately —
 *      without needing to switch sessions and switch back.
 *   2. Sidebar session switching loads history (was FIXME-skipped
 *      due to #480's bridge-unready race).
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
  getSidebarSessionItems,
  createNewConversation,
  launchElectronApp,
  closeElectronApp,
  waitForBridgeInitialized,
} from './helpers/electron-setup';

// ─── Helpers ──────────────────────────────────────────────────────

/** Send a message + type in the chat textarea (triggers React onChange) */
async function typeAndSend(page: Page, text: string) {
  const textarea = await waitForInputReady(page);
  await textarea.click();
  await textarea.type(text);
  await textarea.press('Enter');
  // Wait for the user message to appear
  await expect(page.locator('main').getByText(text).first()).toBeVisible({ timeout: 10_000 });
}

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
      // ── Phase 1: Launch, create a session with known content ──
      const fixture = await launchElectronApp();
      electronApp = fixture.electronApp;
      page = fixture.page;
      miqiHome = fixture.miqiHome;

      await waitForBridgeInitialized(page);
      await page.evaluate(() =>
        (window as any).miqi.approvals.addPermanent('*:*', 'always'),
      );

      const marker = `REG480_${Date.now()}`;
      await typeAndSend(page, `只回答${marker}`);
      await waitForResponseComplete(page, 240_000);

      // Confirm marker is visible
      await expect(
        page.locator('main').getByText(marker, { exact: false }).first(),
      ).toBeVisible({ timeout: 10_000 });
      console.log(`[test] ✅ Phase 1: Created session with marker "${marker}"`);

      // ── Phase 2: Close WITHOUT deleting MIQI_HOME, then relaunch ──
      await closeElectronApp(electronApp); // no miqiHome arg → keep data
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
            /* window not ready */
          }
        }
        if (page2) break;
        await new Promise((r) => setTimeout(r, 100));
      }
      if (!page2) page2 = await app2.firstWindow();
      await page2.waitForLoadState('domcontentloaded');

      // ── Phase 3: Wait for UI + bridge ready ─────────────────────
      try {
        await page2.getByText('MiQi Workbench').waitFor({ timeout: 30_000 });
      } catch {
        console.log('[test] App UI may still be loading — continuing');
      }
      await waitForInputReady(page2, 60_000);

      // ── Phase 4: Verify marker is visible WITHOUT session switching ──
      // ChatConsole.load() retries up to ~55s.  Use a web-first assertion
      // with a generous timeout so the test self-heals regardless of bridge
      // startup speed — no fixed delay, no null-safety edge case.
      await expect(
        page2.locator('main').getByText(marker, { exact: false }).first(),
      ).toBeVisible({ timeout: 120_000 });
      console.log(`[test] ✅ Phase 3: History loaded after restart — no session switch needed`);

      // Clean up: close second app, then delete miqiHome
      await closeElectronApp(app2).catch(() => {});
      await closeElectronApp(electronApp, miqiHome).catch(() => {});
      // Prevent double-cleanup
      // @ts-ignore
      electronApp = undefined as any;
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

      // ── Step 1: Create first session with known marker ─────────
      // createNewConversation first to get a properly titled session
      const sessionATitle = await createNewConversation(page);
      console.log(`[test] Session A created: "${sessionATitle}"`);

      const marker = `SW_${Date.now()}`;
      await typeAndSend(page, `只回答${marker}`);
      await waitForResponseComplete(page, 240_000);

      // Verify marker is visible in session A
      await expect(
        page.locator('main').getByText(marker, { exact: false }).first(),
      ).toBeVisible({ timeout: 10_000 });
      console.log(`[test] ✅ Session A has marker "${marker}"`);

      // ── Step 2: Create session B ──────────────────────────────
      await createNewConversation(page);
      // Wait for sidebar to show both sessions
      await page.waitForTimeout(3000);
      await expect
        .poll(() => getSidebarSessionItems(page).count(), { timeout: 10_000 })
        .toBeGreaterThanOrEqual(2);
      console.log(`[test] Sidebar has at least 2 sessions`);

      // ── Step 3: Click the first session card (session A) in sidebar ──
      // Session cards are button.rounded-xl elements in the sidebar.
      // The first card in the list should be session A (sorted by updated_at).
      // We verify by checking main content after clicking.
      const sessionCards = getSidebarSessionItems(page);
      const numCards = await sessionCards.count();
      console.log(`[test] ${numCards} sidebar session cards found`);

      let found = false;
      for (let i = 0; i < numCards; i++) {
        const card = sessionCards.nth(i);
        await card.scrollIntoViewIfNeeded().catch(() => {});
        await card.click({ force: true, timeout: 5000 });
        console.log(`[test] Clicked sidebar card #${i}`);

        // Wait for ChatConsole to remount and load history
        await page.waitForTimeout(5000);

        const hasMarker = await page
          .locator('main')
          .getByText(marker, { exact: false })
          .first()
          .isVisible()
          .catch(() => false);

        if (hasMarker) {
          found = true;
          console.log(`[test] ✅ Found marker in sidebar card #${i}`);
          break;
        }
        console.log(`[test] Card #${i} does not contain marker`);
      }

      if (!found) {
        // Dump diagnostic info
        const mainText = await page.locator('main').textContent().catch(() => '(error)');
        console.log('[test] DIAGNOSTIC: main text (last 500):', (mainText || '').slice(-500));
      }

      expect(found).toBe(true);
      console.log(`[test] ✅ Sidebar switch back loaded history`);
    },
  );
});
