/**
 * E2E: Reasoning Mode (Fast/Think) — issue #680
 *
 * Validates:
 * 1. ⚡极速回答/🧠深度研究 switch is visible in the input icon row
 *    (right of the ExecutionPolicy selector)
 * 2. Click toggles mode (active styling + sessionStorage persistence)
 * 3. Sending a message stamps the user bubble with the mode tag
 * 4. Default mode is think (current behavior, zero regression)
 *
 * Run: cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron reasoning-mode.spec.ts
 */

import { test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  launchElectronApp,
  closeElectronApp,
  waitForBridgeInitialized,
  waitForInputReady,
} from './helpers/electron-setup';

test.describe('Reasoning Mode E2E', () => {
  let electronApp: ElectronApplication;
  let page: Page;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
    await waitForBridgeInitialized(page);
  }, 60_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp);
  });

  test('mode switch is visible next to the execution-policy selector', async () => {
    const modeBtn = page.getByRole('switch', { name: '回答模式切换' }).first();
    await expect(modeBtn).toBeVisible({ timeout: 15_000 });
    // Default label shows fast (默认极速版)
    await expect(modeBtn).toContainText('极速回答');
  });

  test('default mode is fast (user decision: 默认极速版)', async () => {
    const modeBtn = page.getByRole('switch', { name: '回答模式切换' }).first();
    await expect(modeBtn).toHaveAttribute('aria-checked', 'true');
    await expect(modeBtn).toContainText('⚡');
  });

  test('click toggles to think and persists to sessionStorage', async () => {
    const modeBtn = page.getByRole('switch', { name: '回答模式切换' }).first();
    await modeBtn.click();
    await expect(modeBtn).toHaveAttribute('aria-checked', 'false');
    await expect(modeBtn).toContainText('🧠');

    // sessionStorage persisted
    const stored = await page.evaluate(() => sessionStorage.getItem('miqi-reasoning-mode'));
    expect(stored).toBe('think');

    // Toggle back to fast to keep default behavior for later tests
    await modeBtn.click();
    await expect(modeBtn).toHaveAttribute('aria-checked', 'true');
  });

  test('fast-mode send stamps the user bubble with ⚡ tag', async () => {
    // Ensure fast mode active
    const modeBtn = page.getByRole('switch', { name: '回答模式切换' }).first();
    if ((await modeBtn.getAttribute('aria-checked')) !== 'true') {
      await modeBtn.click();
    }
    await waitForInputReady(page);

    const input = page.locator('textarea').first();
    await input.fill('测试极速模式');
    await input.press('Enter');

    // User bubble with mode tag appears
    const userBubble = page.locator('[data-testid="chat-message-user"]').filter({ hasText: '测试极速模式' }).first();
    await expect(userBubble).toBeVisible({ timeout: 15_000 });
    await expect(userBubble.getByText('⚡ 极速回答')).toBeVisible({ timeout: 10_000 });

    // Back to think
    await modeBtn.click();
  });
});
