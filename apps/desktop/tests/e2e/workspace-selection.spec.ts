/**
 * E2E tests for workspace selection (Issue #555).
 *
 * Verifies:
 * 1. Workspace picker modal appears with all expected elements
 * 2. "Use default workspace" creates a new session and input becomes ready
 */
import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  waitForInputReady,
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';

async function dismissOverlays(page: Page) {
  await page.evaluate(() => {
    document.querySelectorAll('[data-radix-focus-guard]').forEach((e) => e.remove());
    document.querySelectorAll('[data-aria-hidden="true"]').forEach((e) => {
      if (e.classList.contains('fixed') && e.classList.contains('inset-0')) {
        (e as HTMLElement).style.display = 'none';
      }
    });
  });
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

    const modal = page.locator('[data-testid="workspace-picker-modal"]');
    await expect(modal).toBeVisible({ timeout: 5000 });
    await expect(page.locator('[data-testid="workspace-picker-browse"]')).toBeVisible();
    await expect(page.locator('[data-testid="workspace-picker-default"]')).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(modal).toBeHidden({ timeout: 3000 });
    await dismissOverlays(page);
  });

  test('default workspace creates session and input becomes ready', async () => {
    await dismissOverlays(page);
    await page.waitForTimeout(500);

    const plusBtn = page.locator('[data-testid="nav-new-session"]');
    await expect(plusBtn).toBeVisible({ timeout: 5000 });

    await plusBtn.click();
    const modal = page.locator('[data-testid="workspace-picker-modal"]');
    await expect(modal).toBeVisible({ timeout: 5000 });

    // force:true skips Playwright hit-testing — stale Radix overlays can
    // intercept pointer events from a previous dialog close.
    await page.locator('[data-testid="workspace-picker-default"]').click({ force: true });

    // createSession → onNewSession → App changes sessionKey → ChatConsole
    // remounts with key={newKey}. The Dialog portal is cleaned up by React
    // unmount. Verify the modal disappears and the new session loads.
    await expect(modal).toBeHidden({ timeout: 5000 });
    await waitForInputReady(page, 15000);
  });
});
