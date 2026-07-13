/**
 * Sandbox Toggle E2E Tests
 *
 * Verifies runtime sandbox enable/disable toggle by asking the AI agent
 * to execute commands and checking whether MIQI_SANDBOX env var is set.
 *
 * Serial mode: all tests share one Electron instance and toggle state.
 *
 * Prerequisites:
 *   - Frontend rebuilt: npm run build
 *   - LLM provider configured
 *   - bwrap installed
 *
 * Run:
 *   npx playwright test --config=playwright.config.ts --project=electron sandbox-toggle.spec.ts
 */
import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  LLM_TIMEOUT,
  sendMessage,
  waitForResponseComplete,
  createNewConversation,
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';

test.describe.serial('Sandbox Toggle E2E', () => {
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

  // -- Helper: navigate to Settings General tab --
  async function openSettings(page: Page) {
    const settingsBtn = page.getByText('System Settings');
    await expect(settingsBtn).toBeVisible({ timeout: 10_000 });
    await settingsBtn.click();
    await page.waitForTimeout(1500);
    await expect(
      page.getByText('沙箱隔离')
    ).toBeVisible({ timeout: 5_000 });
  }

  // -- Helper: read toggle state label --
  async function getToggleLabel(page: Page): Promise<string> {
    // The label is the last span inside the div next to the toggle button
    const text = await page.locator(
      'button.relative.inline-flex.h-6.w-11.items-center.rounded-full ~ div span:last-child'
    ).textContent();
    return (text || '').trim();
  }

  // -- Helper: click toggle and wait --
  async function toggleSandbox(page: Page) {
    const btn = page.locator(
      'button.relative.inline-flex.h-6.w-11.items-center.rounded-full'
    );
    await expect(btn).toBeVisible({ timeout: 5_000 });
    await btn.click();
    await page.waitForTimeout(2500);
  }

  // -- Helper: ask AI to check MIQI_SANDBOX env var --
  //  Avoids whoami/pwd (blocked by bwrap seccomp) — only checks env.
  async function askSandboxEnv(page: Page): Promise<string> {
    await createNewConversation(page);
    await sendMessage(
      page,
      '用 exec 工具执行下面这行命令，只输出命令的实际结果，不要加任何解释：\n'
      + 'echo "SANDBOX_ENV:${MIQI_SANDBOX:-OFF}"',
    );
    await waitForResponseComplete(page, 180_000);
    const text = await page.locator('main').textContent();
    return text || '';
  }

  // -- Helper: check if sandbox env is present in AI output --
  function sandboxIsOn(output: string): boolean {
    // MIQI_SANDBOX is set → "SANDBOX_ENV:<key>" (not "SANDBOX_ENV:OFF")
    return /SANDBOX_ENV:(?!OFF\b)/.test(output);
  }

  // -- Helper: check if sandbox env is absent --
  function sandboxIsOff(output: string): boolean {
    return output.includes('SANDBOX_ENV:OFF');
  }

  // ── 1. Ensure sandbox is ON, then verify via AI ─────────────────
  test(
    '1-baseline: ensure sandbox enabled and AI confirms',
    { timeout: LLM_TIMEOUT },
    async () => {
      // Open settings and make sure toggle is ON
      await openSettings(page);
      const label = await getToggleLabel(page);
      console.log('[test] Toggle before baseline:', label);

      if (!label.includes('已开启')) {
        console.log('[test] Sandbox was off — toggling ON');
        await toggleSandbox(page);
        const after = await getToggleLabel(page);
        console.log('[test] Toggle after enable:', after);
      }

      // Verify via AI — sandbox env should be set
      const result = await askSandboxEnv(page);
      console.log('[test] Baseline result:', result);

      expect(sandboxIsOn(result)).toBeTruthy();
      console.log('[test] ✅ Baseline: sandbox env confirmed');
    },
  );

  // ── 2. Disable sandbox, verify via AI ──────────────────────────
  test(
    '2-disable: toggle off and AI confirms no sandbox',
    { timeout: LLM_TIMEOUT },
    async () => {
      await openSettings(page);

      const before = await getToggleLabel(page);
      console.log('[test] Toggle before disable:', before);

      expect(before.includes('已开启')).toBeTruthy();
      await toggleSandbox(page);

      const after = await getToggleLabel(page);
      console.log('[test] Toggle after disable:', after);
      expect(
        after.includes('已关闭') || after.includes('已保存')
      ).toBeTruthy();

      // Verify via AI — sandbox env should be OFF
      const result = await askSandboxEnv(page);
      console.log('[test] Disable result:', result);

      expect(sandboxIsOff(result)).toBeTruthy();
      console.log('[test] ✅ Sandbox disabled confirmed');
    },
  );

  // ── 3. Re-enable sandbox, verify via AI ────────────────────────
  test(
    '3-re-enable: toggle on and AI confirms sandbox restored',
    { timeout: LLM_TIMEOUT },
    async () => {
      await openSettings(page);

      const before = await getToggleLabel(page);
      console.log('[test] Toggle before re-enable:', before);

      if (!before.includes('已开启')) {
        await toggleSandbox(page);
        const after = await getToggleLabel(page);
        console.log('[test] Toggle after re-enable:', after);
        expect(
          after.includes('已开启') || after.includes('已保存')
        ).toBeTruthy();
      }

      // Verify via AI — sandbox should be back
      const result = await askSandboxEnv(page);
      console.log('[test] Re-enable result:', result);

      expect(sandboxIsOn(result)).toBeTruthy();
      console.log('[test] ✅ Sandbox re-enabled confirmed');
    },
  );
});
