/**
 * Issue #378: Session switch + return — streaming reply recovery E2E
 *
 * Verifies that after switching away from a session mid-stream and
 * returning, the in-flight reply is visible without a page refresh.
 *
 * Run:
 *   npx playwright test --config=playwright.config.ts --project=electron \
 *     -g 'Session Switch-Back Reply Recovery'
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  LLM_TIMEOUT,
  waitForInputReady,
  createNewConversation,
  approveLoop,
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';

async function sendWithoutWaiting(page: Page, text: string) {
  const inputX = page.locator('textarea, [contenteditable="true"], input[type="text"]').last();
  await expect(inputX).toBeVisible({ timeout: 10000 });
  await inputX.click();
  await inputX.fill('');
  await inputX.type(text);
  await inputX.press('Enter');
}

async function sendAndWait(page: Page, text: string, loopTimeout = 180_000) {
  const inputX = page.locator('textarea, [contenteditable="true"], input[type="text"]').last();
  await expect(inputX).toBeVisible({ timeout: 10000 });
  await inputX.click();
  await inputX.fill('');
  await inputX.type(text);
  await inputX.press('Enter');
  await page.waitForTimeout(1500);
  await approveLoop(page, loopTimeout);
}

test.describe('Session Switch-Back Reply Recovery (Issue #378)', () => {
  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;
  });

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
  });

  test('switch away mid-stream and switch back — reply must be visible (no refresh)', async () => {
    test.setTimeout(LLM_TIMEOUT);

    await createNewConversation(page);
    const markerA = `SWBACK_A_${Date.now().toString(36)}`;
    await sendWithoutWaiting(page, `只回答${markerA}`);
    await expect(page.getByTestId('thinking-indicator')).toBeVisible({ timeout: 15_000 });

    await createNewConversation(page);
    const markerB = `SWBACK_B_${Date.now().toString(36)}`;
    await sendAndWait(page, `只回答${markerB}`);

    const sidebar = page.locator('div.flex.flex-col.shrink-0.border-r').first();
    const items = sidebar.locator('button.rounded-xl');
    const count = await items.count();
    let clicked = false;
    for (let i = 0; i < count; i++) {
      const title = await items.nth(i).textContent();
      if (title?.includes(markerA)) {
        await items.nth(i).click();
        clicked = true;
        break;
      }
    }
    expect(clicked, 'Session A not found in sidebar').toBe(true);

    await page.waitForTimeout(8000);

    const contentA = (await page.locator('main').textContent()) || '';
    expect(contentA, 'Session A should contain its reply after switching back').toContain(markerA);
  });

  test('switch away after reply completes and switch back — reply persists', async () => {
    test.setTimeout(LLM_TIMEOUT);

    await createNewConversation(page);
    const markerA = `PERSIST_A_${Date.now().toString(36)}`;
    await sendAndWait(page, `只回答${markerA}`);
    expect((await page.locator('main').textContent()) || '').toContain(markerA);

    await createNewConversation(page);
    const markerB = `PERSIST_B_${Date.now().toString(36)}`;
    await sendAndWait(page, `只回答${markerB}`);

    const sidebar = page.locator('div.flex.flex-col.shrink-0.border-r').first();
    const items = sidebar.locator('button.rounded-xl');
    const count = await items.count();
    let clicked = false;
    for (let i = 0; i < count; i++) {
      const title = await items.nth(i).textContent();
      if (title?.includes(markerA)) {
        await items.nth(i).click();
        clicked = true;
        break;
      }
    }
    expect(clicked, 'Session A not found in sidebar').toBe(true);

    await page.waitForTimeout(8000);

    const contentA = (await page.locator('main').textContent()) || '';
    expect(contentA, 'Session A should still show its complete reply').toContain(markerA);
  });
});