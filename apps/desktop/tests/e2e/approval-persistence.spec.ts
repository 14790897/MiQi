/**
 * E2E: Approval Persistence (永久允许 → next call auto-approves)
 *
 * Validates that after a user clicks "永久允许" for a tool operation,
 * subsequent identical operations are automatically approved without
 * showing the approval dialog again.
 *
 * KEY: write_file approval is path-specific, not tool-wide.  The
 * permanent allowlist pattern is "write_file:<path>".  To test
 * persistence, both calls MUST target the same file path.
 *
 * Run: cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron approval-persistence.spec.ts
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  LLM_TIMEOUT,
  waitForInputReady,
  waitForResponseComplete,
  createNewConversation,
  waitForBridgeInitialized,
  approveLoop,
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';

// ─── Test Suite ───────────────────────────────────────────────────

const SKIP_APPROVAL_ON_CI =
  !!process.env.CI;

test.describe('Approval Persistence E2E', () => {
  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;
  }, 120_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
  });

  // ═══════════════════════════════════════════════════════════════
  //  Test 1: 永久允许 persists for same file path
  // ═══════════════════════════════════════════════════════════════

  test(
    '永久允许: same file path twice, second call auto-approves',
    { timeout: LLM_TIMEOUT * 3 },
    async () => {
      test.skip(SKIP_APPROVAL_ON_CI, 'CI disables commandApproval — approval dialog never appears');
      // Ensure bridge ready, clear existing approvals
      await waitForBridgeInitialized(page);
      try {
        await page.evaluate(() =>
          (window as any).miqi.approvals.clearPermanent(),
        );
      } catch { /* fine */ }

      await createNewConversation(page);

      // Use the SAME file path for both calls so permanent allowlist matches
      const filepath = `e2e_persist_${Date.now()}.txt`;

      // ── First call: same file path → shows approval dialog ──
      await sendMessage(
        page,
        `Use write_file to create ${filepath} with content "first write"`,
      );

      await expect(page.getByTestId('approval-title')).toBeVisible({
        timeout: 60_000,
      });
      console.log('[test] ✅ First call: approval dialog appeared');

      await page.getByTestId('approval-allow-permanent').click();
      console.log('[test] Clicked 永久允许');

      await waitForResponseComplete(page, 240_000);
      await expect(
        page.locator('main').getByText(filepath, { exact: false }).first(),
      ).toBeVisible({ timeout: 15_000 });
      console.log(`[test] ✅ First file created: ${filepath}`);

      // ── Second call: SAME file path → should auto-approve ──
      await sendMessage(
        page,
        `Use write_file to overwrite ${filepath} with content "second write — auto-approved"`,
      );

      await waitForResponseComplete(page, 240_000);

      // Must NOT show approval dialog again
      await expect(page.getByTestId('approval-title')).not.toBeVisible({
        timeout: 5_000,
      });
      console.log('[test] ✅ Second call: no approval dialog (auto-approved)');

      await expect(
        page.locator('main').getByText(filepath, { exact: false }).first(),
      ).toBeVisible({ timeout: 15_000 });
      console.log(`[test] ✅ Second write auto-approved: ${filepath}`);
    },
  );

  // ═══════════════════════════════════════════════════════════════
  //  Test 2: Cross-session auto-approval
  // ═══════════════════════════════════════════════════════════════

  test(
    '永久允许: persists across new conversations (same path)',
    { timeout: LLM_TIMEOUT * 3 },
    async () => {
      test.skip(SKIP_APPROVAL_ON_CI, 'CI disables commandApproval — approval dialog never appears');
      try {
        await page.evaluate(() =>
          (window as any).miqi.approvals.clearPermanent(),
        );
      } catch { /* ok */ }

      await createNewConversation(page);
      const filepath = `e2e_cross_${Date.now()}.txt`;

      // ── Conv 1: approve permanently ──
      await sendMessage(
        page,
        `Use write_file to create ${filepath} with content "cross-session test"`,
      );
      await expect(page.getByTestId('approval-title')).toBeVisible({ timeout: 60_000 });
      await page.getByTestId('approval-allow-permanent').click();
      await waitForResponseComplete(page, 240_000);
      console.log(`[test] ✅ Conv 1: approved permanently for ${filepath}`);

      // ── Conv 2: new session, same path → auto-approve ──
      await createNewConversation(page);
      await sendMessage(
        page,
        `Use write_file to overwrite ${filepath} with content "cross-session overwrite"`,
      );
      await waitForResponseComplete(page, 240_000);

      await expect(page.getByTestId('approval-title')).not.toBeVisible({ timeout: 5_000 });
      console.log('[test] ✅ Conv 2: no approval dialog (cross-session permanent allowlist)');
    },
  );

});


// ─── Issue #378 helpers ──────────────────────────────────────────────────

async function sendWithoutWaiting(page: Page, text: string) {
  const inputX = page.locator('textarea, [contenteditable="true"], input[type="text"]').last();
  await expect(inputX).toBeVisible({ timeout: 10000 });
  await inputX.click();
  await inputX.fill('');
  await inputX.type(text);
  await inputX.press('Enter');
}

async function sendAndWait(page: Page, text: string, loopTimeout = 180_000) {
  const inputX = page.locator('textarea, [contenteditable="true"], input[type="text"]').last();
  await expect(inputX).toBeVisible({ timeout: 10000 });
  await inputX.click();
  await inputX.fill('');
  await inputX.type(text);
  await inputX.press('Enter');
  await page.waitForTimeout(1500);
  await approveLoop(page, loopTimeout);
}

// ─── Issue #378 Tests ─────────────────────────────────────────────────────

test.describe('Session Switch-Back Reply Recovery (Issue #378)', () => {
  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;
  }, 120_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
  });

  test('switch away mid-stream and switch back — reply must be visible (no refresh)', async () => {
    test.setTimeout(LLM_TIMEOUT);

    await createNewConversation(page);
    const markerA = `SWBACK_A_${Date.now().toString(36)}`;
    await sendWithoutWaiting(page, `只回答${markerA}`);
    await expect(page.getByTestId('thinking-indicator')).toBeVisible({ timeout: 15_000 });

    await createNewConversation(page);
    const markerB = `SWBACK_B_${Date.now().toString(36)}`;
    await sendAndWait(page, `只回答${markerB}`);

    const sidebar = page.locator('div.flex.flex-col.shrink-0.border-r').first();
    const items = sidebar.locator('button.rounded-xl');
    const count = await items.count();
    let clicked = false;
    for (let i = 0; i < count; i++) {
      const title = await items.nth(i).textContent();
      if (title?.includes(markerA)) {
        await items.nth(i).click();
        clicked = true;
        break;
      }
    }
    expect(clicked, 'Session A not found in sidebar').toBe(true);

    await page.waitForTimeout(8000);
    const contentA = (await page.locator('main').textContent()) || '';
    expect(contentA, 'Session A should contain its reply after switching back').toContain(markerA);
  });

  test('switch away after reply completes and switch back — reply persists', async () => {
    test.setTimeout(LLM_TIMEOUT);

    await createNewConversation(page);
    const markerA = `PERSIST_A_${Date.now().toString(36)}`;
    await sendAndWait(page, `只回答${markerA}`);
    expect((await page.locator('main').textContent()) || '').toContain(markerA);

    await createNewConversation(page);
    const markerB = `PERSIST_B_${Date.now().toString(36)}`;
    await sendAndWait(page, `只回答${markerB}`);

    const sidebar = page.locator('div.flex.flex-col.shrink-0.border-r').first();
    const items = sidebar.locator('button.rounded-xl');
    const count = await items.count();
    let clicked = false;
    for (let i = 0; i < count; i++) {
      const title = await items.nth(i).textContent();
      if (title?.includes(markerA)) {
        await items.nth(i).click();
        clicked = true;
        break;
      }
    }
    expect(clicked, 'Session A not found in sidebar').toBe(true);

    await page.waitForTimeout(8000);
    const contentA = (await page.locator('main').textContent()) || '';
    expect(contentA, 'Session A should still show its complete reply').toContain(markerA);
  });
});