/**
 * E2E: Reasoning Mode (Fast/Think) — issue #680
 *
 * Validates:
 * 1. ⚡极速回答 / 🧠深度研究 switch is visible in the input icon row
 * 2. Click switches mode (active styling + sessionStorage persistence)
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

  test('mode switch is visible with both pills', async () => {
    await expect(page.getByText('极速回答', { exact: true }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('深度研究', { exact: true }).first()).toBeVisible();
  });

  test('default mode is think (zero regression)', async () => {
    const thinkBtn = page.getByRole('radio', { name: '深度研究' }).first();
    await expect(thinkBtn).toHaveAttribute('aria-checked', 'true');
  });

  test('click switches to fast and persists to sessionStorage', async () => {
    const fastBtn = page.getByRole('radio', { name: '极速回答' }).first();
    await fastBtn.click();
    await expect(fastBtn).toHaveAttribute('aria-checked', 'true');

    const thinkBtn = page.getByRole('radio', { name: '深度研究' }).first();
    await expect(thinkBtn).toHaveAttribute('aria-checked', 'false');

    // sessionStorage persisted
    const stored = await page.evaluate(() => sessionStorage.getItem('miqi-reasoning-mode'));
    expect(stored).toBe('fast');

    // Switch back to think to keep default behavior for later tests
    await thinkBtn.click();
    await expect(thinkBtn).toHaveAttribute('aria-checked', 'true');
  });

  test('fast-mode send stamps the user bubble with ⚡ tag', async () => {
    // Switch to fast
    await page.getByRole('radio', { name: '极速回答' }).first().click();
    await waitForInputReady(page);

    const input = page.locator('textarea').first();
    await input.fill('测试极速模式');
    await input.press('Enter');

    // User bubble with mode tag appears
    const userBubble = page.locator('[data-testid="chat-message-user"]').filter({ hasText: '测试极速模式' }).first();
    await expect(userBubble).toBeVisible({ timeout: 15_000 });
    await expect(userBubble.getByText('⚡ 极速回答')).toBeVisible({ timeout: 10_000 });

    // Back to think
    await page.getByRole('radio', { name: '深度研究' }).first().click();
  });
});
