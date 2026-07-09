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
  await inputX.type(text);  // type triggers React onChange
  await inputX.press('Enter');
  // If textarea cleared, message was submitted
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

  test.skip(
    '01: exec in session A — file not visible in session B via exec [KNOWN BUG: _auto_exec shared fallback]',
    { timeout: LLM_TIMEOUT },
    async () => {
      test.skip(SKIP_SANDBOX_ON_CI, 'CI lacks bwrap');

      await createNewConversation(page);
      const markerA = `SKA_${Date.now()}`;
      await sendAndWait(page, `用 exec 执行: echo ${markerA} > /home/miqi/workspace/session_marker.txt && echo "WRITTEN"`);
      const respA = (await page.locator('main').textContent()) || '';
      expect(respA).toContain('WRITTEN');
      console.log('[test] ✅ Session A wrote marker file');

      await createNewConversation(page);
      await sendAndWait(page, '用 exec 执行: cat /home/miqi/workspace/session_marker.txt 2>&1; echo EXIT:$?', 120_000);
      const respB = (await page.locator('main').textContent()) || '';
      expect(respB).toMatch(/no such file|not found|EXIT:1/i);
      console.log('[test] ✅ Session B correctly isolated from Session A');
    },
  );

  test.skip(
    '02: write_file in session A — file not visible in session B via exec [KNOWN BUG: _auto_exec]',
    { timeout: LLM_TIMEOUT * 2 },
    async () => {
      test.skip(SKIP_SANDBOX_ON_CI, 'CI lacks bwrap');

      await createNewConversation(page);
      const fnameA = `wsf_${Date.now()}.txt`;
      await sendAndWait(page, `Use write_file to create ${fnameA} with content "session_isolation_test_content". Then reply: DONE`, 240_000);
      expect((await page.locator('main').textContent()) || '').toContain('DONE');
      console.log('[test] ✅ Session A wrote file via write_file');

      await createNewConversation(page);
      await sendAndWait(page, `用 exec 执行: find /home/miqi/workspace -name "${fnameA}" 2>&1; echo EXIT:$?`, 120_000);
      const respB = (await page.locator('main').textContent()) || '';
      expect(respB).not.toContain(fnameA);
      console.log('[test] ✅ Session B correctly isolated');
    },
  );

  test.skip(
    '03: same-named file independently in two sessions [KNOWN BUG: _auto_exec]',
    { timeout: LLM_TIMEOUT * 2 },
    async () => {
      test.skip(SKIP_SANDBOX_ON_CI, 'CI lacks bwrap');
      const sharedName = `shared_${Date.now()}.txt`;

      await createNewConversation(page);
      await sendAndWait(page, `用 exec 执行: echo "FROM_A" > /home/miqi/workspace/${sharedName} && echo WRITTEN_A`);
      expect((await page.locator('main').textContent()) || '').toContain('WRITTEN_A');

      await createNewConversation(page);
      await sendAndWait(page, `用 exec 执行: echo "FROM_B" > /home/miqi/workspace/${sharedName} && echo WRITTEN_B`);
      expect((await page.locator('main').textContent()) || '').toContain('WRITTEN_B');

      await createNewConversation(page);
      await sendAndWait(page, `用 exec 执行: cat /home/miqi/workspace/${sharedName} 2>&1`, 120_000);
      const resp = (await page.locator('main').textContent()) || '';
      expect(resp).toContain('FROM_A');
      expect(resp).not.toContain('FROM_B');
      console.log('[test] ✅ Sessions A/B independent, content FROM_A persists');
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
    '05: exec ls workspace',
    { timeout: LLM_TIMEOUT },
    async () => {
      test.skip(SKIP_SANDBOX_ON_CI, 'CI lacks bwrap');
      await createNewConversation(page);
      await sendAndWait(page, '用 exec 执行: ls /home/miqi/workspace/ 2>&1', 120_000);
      const resp = (await page.locator('main').textContent()) || '';
      expect(resp).not.toMatch(/no such file|denied|error/i);
      console.log('[test] ✅ exec can list session workspace');
    },
  );
});
