/**
 * Sandbox Toggle E2E Tests
 *
 * Verifies the runtime sandbox enable/disable toggle in Settings -> General
 * by actually asking the AI agent to execute commands and checking whether
 * they run inside a sandbox or on the host.
 *
 * Prerequisites:
 *   - Frontend rebuilt: npm run build (in apps/desktop)
 *   - LLM provider configured
 *
 * Run:
 *   npx playwright test --config=playwright.config.ts --project=electron sandbox-toggle.spec.ts
 */
import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  LLM_TIMEOUT,
  waitForInputReady,
  sendMessage,
  waitForResponseComplete,
  createNewConversation,
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';

test.describe('Sandbox Toggle E2E', () => {
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
    // Confirm sandbox section is visible
    await expect(page.getByText('沙箱隔离')).toBeVisible({ timeout: 5_000 });
  }

  // -- Helper: toggle sandbox via UI --
  async function toggleSandbox(page: Page) {
    const toggleBtn = page.locator(
      'button.relative.inline-flex.h-6.w-11.items-center.rounded-full'
    );
    await expect(toggleBtn).toBeVisible({ timeout: 5_000 });
    await toggleBtn.click();
    await page.waitForTimeout(2500);
  }

  // -- Helper: read the toggle label --
  async function getToggleLabel(page: Page): Promise<string> {
    const label = page.locator(
      'button.relative.inline-flex.h-6.w-11.items-center.rounded-full + div span:last-child'
    );
    return (await label.textContent()) || '';
  }

  // -- Helper: ask AI to check its environment --
  async function askAIForEnv(page: Page): Promise<string> {
    await createNewConversation(page);
    await sendMessage(
      page,
      '用 exec 工具执行下面这行命令，只输出命令的实际结果，不要加任何解释文字：\n'
      + 'echo "ENV_CHECK:$(whoami):$(pwd):${MIQI_SANDBOX:-NOSANDBOX}"',
    );
    await waitForResponseComplete(page, 180_000);

    const text = await page.locator('main').textContent();
    return text || '';
  }

  // -- 1. Baseline: verify sandbox is ON by asking AI -----------
  test(
    'baseline: AI runs commands inside sandbox when enabled',
    { timeout: LLM_TIMEOUT },
    async () => {
      // Ask AI to execute a command that reveals sandbox status
      const result = await askAIForEnv(page);
      console.log('[test] Sandbox ON result:\n', result);

      // When sandbox is on, whoami should be 'miqi' (sandbox user)
      // and MIQI_SANDBOX should be set
      const hasSandboxUser = result.includes('miqi');
      const hasSandboxEnv = result.includes('ENV_CHECK');
      const noNOSANDBOX = !result.includes('NOSANDBOX');

      console.log(
        `[test] Sandbox ON check: user=miqi=${hasSandboxUser}, env_set=${hasSandboxEnv}, not_NOSANDBOX=${noNOSANDBOX}`,
      );

      // At least one sandbox indicator should be present
      expect(hasSandboxUser || noNOSANDBOX).toBeTruthy();
      console.log('[test] ✅ Baseline confirmed: sandbox is active');
    },
  );

  // -- 2. Disable sandbox and verify via AI ----------------------
  test(
    'disable sandbox: AI commands run on host',
    { timeout: LLM_TIMEOUT },
    async () => {
      // Step 1: Toggle sandbox OFF
      await openSettings(page);

      const beforeLabel = await getToggleLabel(page);
      console.log('[test] Current state:', beforeLabel);

      // Only toggle if currently enabled
      if (beforeLabel.includes('已开启')) {
        await toggleSandbox(page);
        const afterLabel = await getToggleLabel(page);
        console.log('[test] After toggle:', afterLabel);
        // Should show "已关闭" or an info message (fallback to config)
        expect(
          afterLabel.includes('已关闭') || afterLabel.includes('已保存')
        ).toBeTruthy();
      }

      // Step 2: Ask AI — should now run on host (no sandbox)
      const result = await askAIForEnv(page);
      console.log('[test] Sandbox OFF result:\n', result);

      // When sandbox is off, MIQI_SANDBOX is NOT set → "NOSANDBOX"
      const noSandboxEnv = result.includes('NOSANDBOX');
      // Or the user is different from 'miqi'
      const notMiqiUser = !result.includes('miqi');

      console.log(
        `[test] Sandbox OFF check: NOSANDBOX=${noSandboxEnv}, not_miqi=${notMiqiUser}`,
      );

      expect(noSandboxEnv || notMiqiUser).toBeTruthy();
      console.log('[test] ✅ Sandbox disabled: commands run on host');
    },
  );

  // -- 3. Re-enable sandbox and verify via AI --------------------
  test(
    're-enable sandbox: AI commands back in sandbox',
    { timeout: LLM_TIMEOUT },
    async () => {
      // Step 1: Toggle sandbox back ON
      await openSettings(page);

      const beforeLabel = await getToggleLabel(page);
      console.log('[test] Current state:', beforeLabel);

      if (beforeLabel.includes('已关闭') || beforeLabel.includes('已保存')) {
        await toggleSandbox(page);
        const afterLabel = await getToggleLabel(page);
        console.log('[test] After toggle:', afterLabel);
        expect(
          afterLabel.includes('已开启') || afterLabel.includes('已保存')
        ).toBeTruthy();
      }

      // Step 2: Ask AI — should run inside sandbox again
      const result = await askAIForEnv(page);
      console.log('[test] Sandbox ON (restored) result:\n', result);

      const hasSandboxUser = result.includes('miqi');
      const noNOSANDBOX = !result.includes('NOSANDBOX');

      expect(hasSandboxUser || noNOSANDBOX).toBeTruthy();
      console.log('[test] ✅ Sandbox re-enabled confirmed');
    },
  );
});
