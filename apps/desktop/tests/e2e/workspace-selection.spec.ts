/**
 * E2E tests for workspace selection (Issue #555).
 *
 * Verifies:
 * 1. Workspace picker modal appears with all expected elements
 * 2. "Use default workspace" creates a new session
 */
import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  waitForInputReady,
  launchElectronApp,
  closeElectronApp,
  getSidebarSessionItems,
} from './helpers/electron-setup';

/** Remove stale Radix overlays that can block clicks between tests. */
async function dismissOverlays(page: Page) {
  // Radix leaves overlay divs in DOM after modal close — remove them
  await page.evaluate(() => {
    document.querySelectorAll('[data-radix-focus-guard]').forEach((e) => e.remove());
    document.querySelectorAll('[data-aria-hidden="true"]').forEach((e) => {
      if (e.classList.contains('fixed') && e.classList.contains('inset-0')) {
        (e as HTMLElement).style.display = 'none';
      }
    });
  });
  // Also press Escape to dismiss anything open
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
}

test.describe('Workspace Selection E2E', () => {
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

  test('workspace picker modal appears on new session click', async () => {
    const plusBtn = page.locator('[data-testid="nav-new-session"]');
    await expect(plusBtn).toBeVisible();
    await plusBtn.click();

    // Modal should appear with key elements
    const modal = page.locator('[data-testid="workspace-picker-modal"]');
    await expect(modal).toBeVisible({ timeout: 5000 });
    await expect(page.locator('[data-testid="workspace-picker-browse"]')).toBeVisible();
    await expect(page.locator('[data-testid="workspace-picker-default"]')).toBeVisible();

    // Dismiss via Escape
    await page.keyboard.press('Escape');
    await expect(modal).toBeHidden({ timeout: 3000 });

    // Clean up any lingering Radix overlays
    await dismissOverlays(page);
  });

  test('default workspace creates session and input becomes ready', async () => {
    // Clean up stray overlays from previous test
    await dismissOverlays(page);
    await page.waitForTimeout(500);

    const plusBtn = page.locator('[data-testid="nav-new-session"]');
    await expect(plusBtn).toBeVisible({ timeout: 5000 });

    // Click "+" to open picker, then click "使用默认工作目录"
    await plusBtn.click();
    const modal = page.locator('[data-testid="workspace-picker-modal"]');
    await expect(modal).toBeVisible({ timeout: 5000 });
    await page.locator('[data-testid="workspace-picker-default"]').click();

    // Modal should close
    await expect(modal).toBeHidden({ timeout: 3000 });

    // Input should become ready — means a new session loaded
    await waitForInputReady(page, 15000);

    // Verify sidebar has session items
    const sidebarItems = getSidebarSessionItems(page);
    const count = await sidebarItems.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });
});
