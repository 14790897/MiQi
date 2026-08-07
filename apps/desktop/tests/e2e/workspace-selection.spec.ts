/**
 * E2E tests for workspace selection (Issue #555).
 *
 * Verifies:
 * 1. Sidebar "+" creates session directly (no picker)
 * 2. Inline workspace selector pill visible on empty conversation
 * 3. Inline "更换" button opens workspace picker modal
 * 4. Inline workspace selector disappears after first message
 */
import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  waitForInputReady,
  createNewConversation,
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

  test('sidebar + creates session directly without workspace picker', async () => {
    await dismissOverlays(page);
    await page.waitForTimeout(500);

    const plusBtn = page.locator('[data-testid="nav-new-session"]');
    await expect(plusBtn).toBeVisible({ timeout: 5000 });
    await plusBtn.click();

    // Workspace picker should NOT appear for sidebar "+"
    const modal = page.locator('[data-testid="workspace-picker-modal"]');
    await expect(modal).toBeHidden({ timeout: 3000 });

    // Input should become ready immediately
    await waitForInputReady(page, 15000);
  });

  test('inline workspace selector visible on empty conversation', async () => {
    await dismissOverlays(page);
    await createNewConversation(page);

    // Pill should be visible showing current workspace or default
    const pill = page.locator('[data-testid="inline-workspace-selector"]');
    await expect(pill).toBeVisible({ timeout: 10_000 });

    const pathSpan = page.locator('[data-testid="inline-workspace-path"]');
    await expect(pathSpan).toBeVisible();

    // "更换" button should be present
    const changeBtn = page.locator('[data-testid="inline-workspace-change-btn"]');
    await expect(changeBtn).toBeVisible();
    await expect(changeBtn).toBeEnabled();
  });

  test('inline change button opens workspace picker modal', async () => {
    await dismissOverlays(page);
    await createNewConversation(page);

    // Click the inline "更换" button
    const changeBtn = page.locator('[data-testid="inline-workspace-change-btn"]');
    await expect(changeBtn).toBeVisible({ timeout: 10_000 });
    await changeBtn.click();

    // Workspace picker modal should appear
    const modal = page.locator('[data-testid="workspace-picker-modal"]');
    await expect(modal).toBeVisible({ timeout: 5000 });
    await expect(page.locator('[data-testid="workspace-picker-browse"]')).toBeVisible();
    await expect(page.locator('[data-testid="workspace-picker-default"]')).toBeVisible();

    // Dismiss
    await page.keyboard.press('Escape');
    await expect(modal).toBeHidden({ timeout: 3000 });
    await dismissOverlays(page);
  });

  test('inline workspace selector disappears after first message', async () => {
    await dismissOverlays(page);
    await createNewConversation(page);

    // Pill should be visible before sending
    const pill = page.locator('[data-testid="inline-workspace-selector"]');
    await expect(pill).toBeVisible({ timeout: 10_000 });

    // Send a short message
    const textarea = page.locator('[data-testid="chat-input-container"] textarea');
    await expect(textarea).toBeEnabled();
    await textarea.type('你好');
    await textarea.press('Enter');

    // Confirm user message appears
    await expect(page.getByText('你好').first()).toBeVisible({ timeout: 10_000 });

    // Pill should disappear after message is sent
    await expect(pill).toBeHidden({ timeout: 5000 });
  });
});
