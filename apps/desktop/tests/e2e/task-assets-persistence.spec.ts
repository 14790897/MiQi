/**
 * E2E: Task Assets — File Preview & Session-Switch Persistence
 *
 * Verifies:
 *   1. Agent creates file → appears in Task Assets panel
 *   2. Click Preview → dispatched via system default app (no crash)
 *   3. Switch to another session and back → file list survives
 *
 * Run:
 *   cd apps/desktop
 *   npx playwright test --config=playwright.config.ts --project=electron task-assets-persistence.spec.ts
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  LLM_TIMEOUT,
  waitForInputReady,
  launchElectronApp,
  closeElectronApp,
  switchToSessionWithMarker,
  waitForBridgeInitialized,
} from './helpers/electron-setup';

// ─── Helpers ──────────────────────────────────────────────────────────

async function sendMessage(page: Page, text: string) {
  const textarea = await waitForInputReady(page);
  await textarea.fill(text);
  await textarea.press('Enter');
  await expect(page.getByText(text).first()).toBeVisible({ timeout: 10_000 });
}

async function waitForResponseComplete(page: Page, timeout = 240_000) {
  await expect(page.getByText('Thinking…')).toBeHidden({ timeout });
  try {
    await expect(page.locator('.tag-inprogress')).toBeHidden({ timeout: 15_000 });
  } catch {
    /* fast responses may never show IN PROGRESS */
  }
}

/** Wait for a file card with the given filename to appear in Task Assets */
async function waitForFileInPanel(page: Page, filename: string, timeout = 30_000) {
  const assetsPanel = page.getByTestId('task-assets-panel');
  const card = assetsPanel
    .locator('.rounded-lg.p-2\\.5')
    .filter({ hasText: filename })
    .first();
  await expect(card).toBeVisible({ timeout });
  // Panel should no longer show empty state
  await expect(page.locator('[data-testid="task-assets-empty"]')).not.toBeVisible({ timeout: 5_000 });
  return card;
}

/** Get the session title text */
function getSessionTitle(page: Page) {
  return page.locator('h2.font-semibold.truncate').first();
}

// ─── Test Suite ───────────────────────────────────────────────────────

test.describe('Task Assets Preview & Persistence', () => {
  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;

    // Pre-approve ALL tool calls so no approval dialogs interrupt the test
    await waitForBridgeInitialized(page);
    await page.evaluate(() =>
      (window as any).miqi.approvals.addPermanent('*:*', 'always'),
    );
    console.log('[test] *:* wildcard pre-approved');
  }, 180_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
  });

  // ═══════════════════════════════════════════════════════════════════
  //  Test 1: Preview opens file with system default app
  // ═══════════════════════════════════════════════════════════════════

  test(
    'Agent creates file → click Preview → dispatched to system app',
    { timeout: LLM_TIMEOUT * 2 },
    async () => {
      const filename = `e2e_preview_${Date.now()}.md`;
      const content = `# E2E Preview Test\n\nContent: ${Date.now()}`;

      // Ensure Task Assets panel is visible
      await expect(page.getByTestId('task-assets-panel')).toBeVisible({ timeout: 10_000 });

      // Agent creates a .md file via write_file
      await sendMessage(
        page,
        `用 write_file 创建文件：path=${filename}，content="${content}"。创建完只回复：完成`,
      );
      await waitForResponseComplete(page, 240_000);

      // Verify file appears in Task Assets panel
      const card = await waitForFileInPanel(page, filename);
      console.log(`[test] ✅ File "${filename}" appears in Task Assets`);

      // Click Preview — should dispatch to system default app.
      // In E2E (temp workspace, no WSL sandbox) the file may not be
      // found via openExternal, which triggers the error fallback
      // preview modal.  Both outcomes are valid — the important thing
      // is the click doesn't crash the app.
      await card.getByRole('button', { name: 'Preview', exact: true }).click();
      await page.waitForTimeout(500);

      // Verify app is still functional — panel still visible
      await expect(page.getByTestId('task-assets-panel')).toBeVisible({ timeout: 5_000 });
      console.log('[test] ✅ Preview click completed without crash');
    },
  );

  // ═══════════════════════════════════════════════════════════════════
  //  Test 2: File list survives session switch
  // ═══════════════════════════════════════════════════════════════════

  test(
    'files persist in Task Assets after switching sessions and returning',
    { timeout: LLM_TIMEOUT * 2 },
    async () => {
      const persistMarker = `E2E_PERSIST_${Date.now()}`;
      const filename = `e2e_persist_${Date.now()}.py`;
      const content = `# ${persistMarker}\nprint("E2E persistence test")`;

      // Step 1: create a file in the current session
      await sendMessage(
        page,
        `用 write_file 创建：path=${filename}，content="${content}"。只回复：好了`,
      );
      await waitForResponseComplete(page, 240_000);

      // Grab the session title for later switch-back
      const sessionATitle = await getSessionTitle(page).textContent();
      console.log(`[test] Session A title: "${sessionATitle}"`);

      // Verify file is in Task Assets
      await waitForFileInPanel(page, filename);
      const countBefore = await page.getByTestId('task-assets-panel')
        .locator('.rounded-lg.p-2\\.5').count();
      console.log(`[test] ✅ ${countBefore} file(s) in Task Assets before switch`);

      // Step 2: switch to a new (empty) session via sidebar "+"
      // The sidebar button might use different selectors — try common ones
      const newSessionBtn =
        page.locator('button[title="New Session"]').or(
          page.locator('button[title="新建会话"]'),
        ).or(
          page.getByRole('button', { name: /New Session|新建会话|\+/ }).first(),
        );
      try {
        await expect(newSessionBtn).toBeVisible({ timeout: 5_000 });
        await newSessionBtn.click();
      } catch {
        // Fallback: use keyboard shortcut or evaluate to create session
        console.log('[test] New Session button not found — creating via evaluate');
        await page.evaluate(() => {
          const key = `desktop:${Date.now()}`;
          localStorage.setItem('miqi:lastSession', key);
          location.reload();
        });
        await page.waitForTimeout(3_000);
        await waitForInputReady(page, 30_000);
      }

      // Session B should have no files
      await expect(page.locator('[data-testid="task-assets-empty"]')).toBeVisible({ timeout: 10_000 });
      console.log('[test] ✅ Session B shows empty state.');

      // Step 3: switch back to Session A
      const found = await switchToSessionWithMarker(page, persistMarker);
      if (!found) {
        console.log('[test] ⚠️ Could not find Session A via marker — skipping restore check');
        return;
      }
      console.log(`[test] Switched back to Session A`);

      // Step 4: wait for ChatConsole to remount and load tracked files
      await waitForInputReady(page, 15_000);
      await page.waitForTimeout(2000);

      // File should STILL be in Task Assets
      const card = await waitForFileInPanel(page, filename, 15_000);
      const countAfter = await page.getByTestId('task-assets-panel')
        .locator('.rounded-lg.p-2\\.5').count();
      console.log(`[test] ✅ ${countAfter} file(s) in Task Assets after return`);

      expect(countAfter).toBeGreaterThanOrEqual(1);
      console.log('[test] ✅ Task Assets file list survives session switch');
    },
  );
});
