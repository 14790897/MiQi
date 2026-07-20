/**
 * E2E: Execution Policy Mode Selector
 *
 * Validates:
 * 1. Mode selector dropdown opens and shows 4 options
 * 2. Each mode can be selected via click
 * 3. Keyboard shortcuts 1-4 work
 * 4. Bypass mode shows confirmation dialog
 * 5. Mode switch toast appears
 *
 * Run: cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron execution-policy.spec.ts
 */

import { test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  launchElectronApp,
  closeElectronApp,
  waitForBridgeInitialized,
  waitForInputReady,
} from './helpers/electron-setup';

test.describe('Execution Policy E2E', () => {
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

  test('mode selector is visible in input area', async () => {
    // The ExecutionPolicySelector button should be near the input
    const modeBtn = page.locator('button').filter({ hasText: /规划|手动|接受编辑|绕过/ }).first();
    await expect(modeBtn).toBeVisible({ timeout: 10_000 });
  });

  test('clicking mode button opens dropdown with 4 modes', async () => {
    const modeBtn = page.locator('button').filter({ hasText: /规划|手动|接受编辑|绕过/ }).first();
    await modeBtn.click();
    await page.waitForTimeout(300);

    // 4 items should be visible
    const planItem = page.getByText('规划', { exact: true }).first();
    const manualItem = page.getByText('手动', { exact: true }).first();
    const editsItem = page.getByText('接受编辑', { exact: true }).first();
    const bypassItem = page.getByText('绕过权限', { exact: true }).first();

    await expect(planItem).toBeVisible({ timeout: 3_000 });
    await expect(manualItem).toBeVisible({ timeout: 3_000 });
    await expect(editsItem).toBeVisible({ timeout: 3_000 });
    await expect(bypassItem).toBeVisible({ timeout: 3_000 });
  });

  test('switching mode updates the button label', async () => {
    const modeBtn = page.locator('button').filter({ hasText: /规划|手动|接受编辑|绕过/ }).first();

    // Click to open
    await modeBtn.click();
    await page.waitForTimeout(300);

    // Select "手动"
    await page.getByText('手动', { exact: true }).first().click();
    await page.waitForTimeout(500);

    // Button should now show "手动"
    await expect(modeBtn).toContainText('手动', { timeout: 3_000 });
  });

  test('bypass mode shows confirmation dialog', async () => {
    const modeBtn = page.locator('button').filter({ hasText: /规划|手动|接受编辑|绕过/ }).first();
    await modeBtn.click();
    await page.waitForTimeout(300);

    // Select "绕过权限"
    await page.getByText('绕过权限', { exact: true }).first().click();
    await page.waitForTimeout(500);

    // Confirmation dialog should appear
    const dialog = page.getByText('开启绕过权限');
    await expect(dialog).toBeVisible({ timeout: 3_000 });

    // Dismiss it
    await page.getByText('取消').last().click();
    await page.waitForTimeout(300);
  });

  test('keyboard shortcuts 1-4 switch modes', async () => {
    // Press '1' = Plan
    await page.keyboard.press('1');
    await page.waitForTimeout(300);
    const modeBtn = page.locator('button').filter({ hasText: /规划|手动|接受编辑|绕过/ }).first();
    await expect(modeBtn).toContainText('规划', { timeout: 3_000 });

    // Press '3' = Accept edits
    await page.keyboard.press('3');
    await page.waitForTimeout(300);
    await expect(modeBtn).toContainText('接受编辑', { timeout: 3_000 });
  });

  test('toast appears on mode switch', async () => {
    const modeBtn = page.locator('button').filter({ hasText: /规划|手动|接受编辑|绕过/ }).first();
    await modeBtn.click();
    await page.waitForTimeout(300);

    // Select Plan
    await page.getByText('规划', { exact: true }).first().click();
    await page.waitForTimeout(500);

    // Toast should appear
    const toast = page.getByText('✓ 规划 已启用');
    await expect(toast).toBeVisible({ timeout: 3_000 });
  });

  test('input is still usable after mode switch', async () => {
    // Ensure input works
    const textarea = await waitForInputReady(page);
    await textarea.fill('test');
    await expect(textarea).toHaveValue('test');
  });
});
