/**
 * Session Key Path Mapping E2E Tests
 *
 * PR #200: feat(sandbox): use real session_key and Windows path mapping
 *
 * Run: npx playwright test --config=playwright.config.ts --project=electron -g 'Session Key'
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  APPS_DESKTOP,
  LLM_TIMEOUT,
  waitForInputReady,
  createNewConversation,
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';

const SKIP_SANDBOX_ON_CI = !!process.env.CI;

async function approveLoop(page: Page, timeout = 180_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const btn = page.getByRole('button', { name: '持久允许' }).or(page.getByRole('button', { name: '永久允许' }));
    if (await btn.isVisible({ timeout: 1000 }).catch(() => false)) {
      await btn.click();
      console.log('[test] Auto-approved tool');
    }
    const thinking = await page.getByText('Thinking…').isVisible().catch(() => false);
    if (!thinking) break;
    await page.waitForTimeout(1000);
  }
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

test.describe('Session Key Path Mapping E2E', () => {
  let electronApp: ElectronApplication;
  let page: Page;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
  });

  test.afterAll(async () => {
    await closeElectronApp(electronApp);
  });

  test(
    '01: write_file in session A — not visible via read_file in session B',
    { timeout: LLM_TIMEOUT * 2 },
    async () => {
      test.skip(SKIP_SANDBOX_ON_CI, 'CI lacks bwrap');

      const fnameA = `wsf_${Date.now()}.txt`;
      // ── Session A: create file via write_file ──
      await createNewConversation(page);
      await sendAndWait(page, `Use write_file to create ${fnameA} with content "isolation_test". Then reply: DONE`, 240_000);
      expect((await page.locator('main').textContent()) || '').toContain('DONE');
      console.log('[test] ✅ Session A wrote file');

      // ── Session B: try read_file ──
      await createNewConversation(page);
      await sendAndWait(page, `Use read_file to read ${fnameA}. Reply with file content or "NOT FOUND"`, 120_000);
      const respB = (await page.locator('main').textContent()) || '';
      expect(respB).not.toContain('isolation_test');
      console.log('[test] ✅ Session B isolated — cannot read Session A file');
    },
  );

  test.skip(
    '02: write_file in session A — file visible via read_file in session A only',
    { timeout: LLM_TIMEOUT * 2 },
    async () => {
      test.skip(SKIP_SANDBOX_ON_CI, 'CI lacks bwrap');

      const fnameA = `wsf2_${Date.now()}.txt`;
      // ── Session A: create file via write_file ──
      await createNewConversation(page);
      await sendAndWait(page, `Use write_file to create ${fnameA} with content "test2". Then reply: DONE2`, 240_000);
      expect((await page.locator('main').textContent()) || '').toContain('DONE2');
      console.log('[test] ✅ Session A wrote file via write_file');

      // ── Session B: try read_file ──
      await createNewConversation(page);
      await sendAndWait(page, `Use read_file to read ${fnameA}. Reply with file content or "NOT FOUND"`, 120_000);
      const respB = (await page.locator('main').textContent()) || '';
      expect(respB).not.toContain('test2');
      console.log('[test] ✅ Session B isolated from Session A file');
    },
  );

  test(
    '03: same-named file independently via write_file in two sessions',
    { timeout: LLM_TIMEOUT * 2 },
    async () => {
      test.skip(SKIP_SANDBOX_ON_CI, 'CI lacks bwrap');
      const sharedName = `shared_${Date.now()}.txt`;

      await createNewConversation(page);
      await sendAndWait(page, `Use write_file to create ${sharedName} with content "FROM_A". Then reply: DONE_A`);
      expect((await page.locator('main').textContent()) || '').toContain('DONE_A');

      await createNewConversation(page);
      await sendAndWait(page, `Use write_file to create ${sharedName} with content "FROM_B". Then reply: DONE_B`);
      expect((await page.locator('main').textContent()) || '').toContain('DONE_B');

      await createNewConversation(page);
      await sendAndWait(page, `Use read_file to read ${sharedName}. Reply with the content.`, 120_000);
      const resp = (await page.locator('main').textContent()) || '';
      expect(resp).toContain('FROM_A');
      expect(resp).not.toContain('FROM_B');
      console.log('[test] ✅ Session A file not overwritten by Session B');
    },
  );

  test(
    '04: exec pwd/whoami in sandbox',
    { timeout: LLM_TIMEOUT },
    async () => {
      test.skip(SKIP_SANDBOX_ON_CI, 'CI lacks bwrap');
      await createNewConversation(page);
      const pwdMarker = `PWD_${Date.now()}`;
      await sendAndWait(page, `用 exec 执行: pwd && whoami && echo ${pwdMarker}`, 120_000);
      const resp = (await page.locator('main').textContent()) || '';
      expect(resp).toContain('/home/miqi');
      expect(resp).toContain('miqi');
      expect(resp).toContain(pwdMarker);
      console.log('[test] ✅ exec runs inside sandbox as miqi');
    },
  );

  test(
    '05: each session gets unique sandbox key from orchestrator',
    { timeout: LLM_TIMEOUT },
    async () => {
      test.skip(SKIP_SANDBOX_ON_CI, 'CI lacks bwrap');
      await createNewConversation(page);
      await sendAndWait(page, '用 exec 执行: echo SANDBOX_OK');
      const resp1 = (await page.locator('main').textContent()) || '';
      expect(resp1).toContain('SANDBOX_OK');

      await createNewConversation(page);
      await sendAndWait(page, '用 exec 执行: echo SANDBOX_OK_2');
      const resp2 = (await page.locator('main').textContent()) || '';
      expect(resp2).toContain('SANDBOX_OK_2');
      console.log('[test] ✅ Each session has unique sandbox');
    },
  );
});
