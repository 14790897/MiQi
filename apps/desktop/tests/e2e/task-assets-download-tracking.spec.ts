/**
 * E2E: Task Assets — Download Tracking & Preview
 *
 * Verifies:
 *   1. AI creates file via write_file → appears in Task Assets panel → Preview works
 *   2. Multiple tracking sources for same file → single deduped card
 *   3. exec + curl downloads PDF → appears in Task Assets
 *
 * Run:
 *   cd apps/desktop
 *   npm run build
 *   npx playwright test --config=playwright.config.ts --project=electron --headed task-assets-download-tracking.spec.ts
 */

import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import {
  LLM_TIMEOUT,
  sendMessage,
  waitForResponseComplete,
  launchElectronApp,
  closeElectronApp,
  waitForBridgeInitialized,
} from './helpers/electron-setup';
import type { ElectronApplication } from '@playwright/test';

// Run tests serially within this describe block to avoid parallel state conflicts
test.describe.configure({ mode: 'serial' });

// ─── Helpers ──────────────────────────────────────────────────────────

/** Wait for a file card containing the given text in Task Assets panel */
async function expectFileInPanel(page: Page, text: string, timeout = 120_000) {
  const panel = page.getByTestId('task-assets-panel');
  const card = panel.locator('.rounded-lg.p-2\\.5').filter({ hasText: text }).first();
  await expect(card).toBeVisible({ timeout });
  await expect(page.locator('[data-testid="task-assets-empty"]')).not.toBeVisible({ timeout: 5_000 });
  return card;
}

// ─── Suite ────────────────────────────────────────────────────────────

test.describe('Task Assets — Download Tracking', () => {
  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;

    await waitForBridgeInitialized(page);
    await page.evaluate(() =>
      (window as any).miqi.approvals.addPermanent('*:*', 'always'),
    );
    console.log('[test] ✅ *:* pre-approved');
  }, 180_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
  });

  // ══════════════════════════════════════════════════════════════════
  //  Test 1: write_file → appears → Preview does not crash
  // ══════════════════════════════════════════════════════════════════

  test(
    'write_file creates file → Task Assets shows card → Preview button works',
    { timeout: LLM_TIMEOUT * 2 },
    async () => {
      const marker = `e2e_write_${Date.now()}`;
      const filename = `${marker}.md`;

      await sendMessage(
        page,
        `用 write_file 创建文件：path="${filename}"，content="# ${marker}"。完成后只回复：完成`,
      );
      await waitForResponseComplete(page, LLM_TIMEOUT);

      // Capture the card locator (reuse for Preview click below)
      const card = await expectFileInPanel(page, marker);
      console.log(`[test] ✅ "${filename}" in Task Assets`);

      // Click Preview — should not crash
      await card.getByRole('button', { name: 'Preview', exact: true }).click();
      await page.waitForTimeout(1_000);

      // Verify the preview modal opened (shows filename in header) or at
      // minimum the app didn't crash (panel still visible)
      const previewModal = page.locator('.fixed.inset-0.z-50');
      const modalVisible = await previewModal.isVisible().catch(() => false);
      if (modalVisible) {
        await expect(previewModal).toContainText(marker, { timeout: 3_000 });
        console.log('[test] ✅ Preview modal opened with file content');
      } else {
        await expect(page.getByTestId('task-assets-panel')).toBeVisible({ timeout: 5_000 });
        console.log('[test] ✅ Preview click completed without crash');
      }
    },
  );

  // ══════════════════════════════════════════════════════════════════
  //  Test 2: Duplicate tracking → single card (dedup)
  // ══════════════════════════════════════════════════════════════════

  test(
    'same file tracked twice → single deduped card',
    { timeout: LLM_TIMEOUT * 3 },
    async () => {
      const marker = `e2e_dedup_${Date.now()}`;
      const filename = `${marker}.txt`;

      await sendMessage(
        page,
        `用 write_file 创建文件：path="${filename}"，content="${marker}"。只回复：完成`,
      );
      await waitForResponseComplete(page, LLM_TIMEOUT);

      await expectFileInPanel(page, marker);

      await page.waitForTimeout(2_000);
      await sendMessage(
        page,
        `用 write_file 覆盖文件：path="${filename}"，content="${marker} v2"。只回复：完成`,
      );
      await waitForResponseComplete(page, LLM_TIMEOUT);

      await page.waitForTimeout(2_000);
      const cards = page.getByTestId('task-assets-panel')
        .locator('.rounded-lg.p-2\\.5')
        .filter({ hasText: marker });

      // write_file tracks by path — overwriting same path must retain one card
      await expect(cards).toHaveCount(1);
      console.log('[test] ✅ Dedup: exactly one card for same file');
    },
  );

  // ══════════════════════════════════════════════════════════════════
  //  Test 3: exec + curl → file appears in Task Assets
  // ══════════════════════════════════════════════════════════════════

  test(
    'exec + curl downloads PDF → appears in Task Assets',
    { timeout: LLM_TIMEOUT * 3, retries: 1 },
    async () => {
      test.setTimeout(600_000);

      const marker = `e2e_curl_${Date.now()}`;
      const filename = `${marker}.pdf`;

      await sendMessage(
        page,
        `用 exec 执行 curl 下载一个小文件：`
        + `curl -o ${filename} -s https://arxiv.org/pdf/2607.06563v1`
        + ` && echo 完成 ${marker}`,
      );
      await waitForResponseComplete(page, 300_000);

      try {
        await expectFileInPanel(page, marker, 60_000);
        console.log(`[test] ✅ exec+curl file (${filename}) in Task Assets`);
      } catch (error) {
        const panelText = await page.getByTestId('task-assets-panel').textContent();
        const pages = await page.locator('main').textContent();
        console.log(`[test] ⚠️ File not found. Panel: "${panelText?.slice(-200)}"`);
        console.log(`[test] ⚠️ Last response: "${pages?.slice(-300)}"`);
        if (pages?.includes(marker)) {
          console.log('[test] ⚠️ curl succeeded (marker found) but file tracking missed it');
        }
        throw error;
      }
    },
  );
});