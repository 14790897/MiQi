/**
 * E2E: Reasoning Mode (Fast/Think) — issue #680
 *
 * Validates:
 * 1. ⚡极速回答/🧠深度研究 menu button is visible in the input icon row
 *    (right of the ExecutionPolicy selector)
 * 2. Click opens the menu; selecting an item switches mode + persists
 *    to sessionStorage
 * 3. Sending a message stamps the user bubble with the mode tag
 * 4. Default mode is fast (user decision: 默认极速版)
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

const MODE_BTN = 'button[aria-label="回答模式"]';

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

  test('mode menu button is visible next to the execution-policy selector', async () => {
    const modeBtn = page.locator(MODE_BTN).first();
    await expect(modeBtn).toBeVisible({ timeout: 15_000 });
    // Default label shows fast (默认极速版)
    await expect(modeBtn).toContainText('极速回答');
  });

  test('default mode is fast (user decision: 默认极速版)', async () => {
    const modeBtn = page.locator(MODE_BTN).first();
    await expect(modeBtn).toContainText('极速回答');
    await expect(modeBtn).not.toContainText('深度研究');
  });

  test('menu opens with both options and selecting think persists', async () => {
    const modeBtn = page.locator(MODE_BTN).first();
    await modeBtn.click();

    // Menu shows both options
    await expect(page.getByText('深度研究', { exact: true }).first()).toBeVisible({
      timeout: 5_000,
    });
    await expect(page.getByText('极速回答', { exact: true }).first()).toBeVisible();

    // Select think
    await page.locator('button', { hasText: '深度研究' }).last().click();
    await expect(modeBtn).toContainText('深度研究');

    // sessionStorage persisted
    const stored = await page.evaluate(() => sessionStorage.getItem('miqi-reasoning-mode'));
    expect(stored).toBe('think');

    // Back to fast for later tests
    await modeBtn.click();
    await page.locator('button', { hasText: '极速回答' }).last().click();
    await expect(modeBtn).toContainText('极速回答');
  });

  test('fast-mode send completes and assistant answer carries 🚀 icon', async () => {
    // Ensure fast mode active (default)
    const modeBtn = page.locator(MODE_BTN).first();
    if ((await modeBtn.textContent())?.includes('深度研究')) {
      await modeBtn.click();
      await page.locator('button', { hasText: '极速回答' }).last().click();
    }
    await waitForInputReady(page);

    const input = page.locator('textarea').first();
    await input.fill('只回答"好的"两个字');
    await input.press('Enter');

    // User bubble appears
    const userBubble = page
      .locator('[data-testid="chat-message-user"]')
      .filter({ hasText: '只回答' })
      .first();
    await expect(userBubble).toBeVisible({ timeout: 15_000 });

    // No text label on the user bubble anymore (removed #680 跟进) —
    // the assistant answer carries the 🚀 fast-mode icon instead.
    await expect(userBubble.getByText('极速回答')).toHaveCount(0);

    // Assistant answer appears with 🚀 icon (fast mode).  Scope the locator
    // to the ASSISTANT bubble (CodeRabbit #783): the user input itself
    // contains 好的, so a global match could pass before any answer renders.
    const answer = page
      .locator('[data-testid="chat-message-assistant"]')
      .filter({ hasText: '好的' })
      .last();
    await expect(answer).toBeVisible({ timeout: 60_000 });
    // And the fast-mode 🚀 icon rides on that same bubble (test name promise).
    await expect(answer).toContainText('🚀');
  });
});
