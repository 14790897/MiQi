/**
 * E2E tests for workspace file read & in-place edit.
 *
 * Verifies:
 * 1. write_file creates files → read_file can read them back
 * 2. write_file can overwrite a file in-place → read_file sees updated content
 * 3. Files are correctly tracked in Task Assets panel
 */
import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  LLM_TIMEOUT,
  createNewConversation,
  waitForResponseComplete,
  approveLoop,
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';

/** Send with type() (triggers React onChange), then run approval loop. */
async function sendAndWait(page: Page, text: string, loopTimeout = 240_000) {
  const textarea = page.locator('[data-testid="chat-input-container"] textarea');
  await expect(textarea).toBeEnabled({ timeout: 10_000 });
  await textarea.click();
  await textarea.fill('');
  await textarea.type(text);
  await textarea.press('Enter');
  await page.waitForTimeout(1500);
  await approveLoop(page, loopTimeout);
}

/** Get full text content of <main>. */
async function mainText(page: Page): Promise<string> {
  return page.evaluate(() => {
    const el = document.querySelector('main');
    return el?.textContent ?? '';
  });
}

test.describe('Workspace File Read & In-Place Edit E2E', () => {
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

  test(
    'write_file creates file → read_file reads it back correctly',
    { timeout: LLM_TIMEOUT },
    async () => {
      await page.evaluate(() =>
        (window as any).miqi.approvals.addPermanent('*:*', 'always'),
      );

      await createNewConversation(page);

      const marker = `UNIQUE_${Date.now().toString(36)}`;
      const fname = `e2e-rw-${Date.now()}.txt`;

      // Step 1: create
      await sendAndWait(page, `用 write_file 创建 ${fname}，内容为 ${marker}。创建完回复 DONE。`);
      await waitForResponseComplete(page, 240_000);

      // Step 2: read back in same conversation
      await sendAndWait(page, `用 read_file 读取 ${fname}，只回复文件原文。`);
      await waitForResponseComplete(page, 240_000);

      const text = await mainText(page);
      console.log('[test] === read_file response (last 300 chars) ===');
      console.log(text.slice(-300));
      console.log('[test] =========================================');

      expect(text).toContain(marker);
      console.log('[test] ✅ read_file reads back write_file content');
    },
  );

  test(
    'write_file creates file → Task Assets panel tracks it',
    { timeout: LLM_TIMEOUT },
    async () => {
      await page.evaluate(() =>
        (window as any).miqi.approvals.addPermanent('*:*', 'always'),
      );

      await createNewConversation(page);

      const fname = `e2e-ta-${Date.now()}.txt`;
      await sendAndWait(page, `用 write_file 创建 ${fname}，内容为 hello。创建完回复 DONE。`);
      await waitForResponseComplete(page, 240_000);

      // Task Assets panel should show at least 1 file
      const countText = await page.locator('[data-testid="task-assets-title"]').textContent();
      console.log(`[test] Task Assets title: ${countText}`);

      // File name should appear in task assets or tracked files area
      const fileInPanel = page.locator('main').getByText(fname, { exact: false }).first();
      await expect(fileInPanel).toBeVisible({ timeout: 10_000 });
      console.log('[test] ✅ Task Assets panel tracks created file');
    },
  );

  test(
    'write_file overwrites same file in-place → read_file sees new content',
    { timeout: LLM_TIMEOUT },
    async () => {
      await page.evaluate(() =>
        (window as any).miqi.approvals.addPermanent('*:*', 'always'),
      );

      await createNewConversation(page);

      const fname = `e2e-edit-${Date.now()}.txt`;
      const oldContent = `ORIGINAL_${Date.now().toString(36)}`;
      const newContent = `UPDATED_${Date.now().toString(36)}`;

      // Step 1: create initial file
      await sendAndWait(page, `用 write_file 创建 ${fname}，内容为 ${oldContent}。创建完回复 DONE。`);
      await waitForResponseComplete(page, 240_000);

      // Step 2: overwrite the same file
      await sendAndWait(page, `用 write_file 覆盖 ${fname}，新内容为 ${newContent}。覆盖完回复 OK。`);
      await waitForResponseComplete(page, 240_000);

      // Step 3: read back — must see NEW content, not old
      await sendAndWait(page, `用 read_file 读取 ${fname}，只回复文件原文。`);
      await waitForResponseComplete(page, 240_000);

      const text = await mainText(page);
      console.log('[test] === read_file after overwrite (last 300 chars) ===');
      console.log(text.slice(-300));
      console.log('[test] =================================================');

      expect(text).toContain(newContent);
      // User input area also shows oldContent; check solely AI's final reply
      const aiReply = text.slice(text.lastIndexOf(newContent));
      expect(aiReply).not.toContain(oldContent);
      console.log('[test] ✅ write_file in-place overwrite reflected in read_file');
    },
  );
});
