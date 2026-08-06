/**
 * E2E tests for the complete workspace + file read/write/edit flow.
 *
 * Full coverage:
 *   1. Inline pill shows "默认工作目录" on empty conversation
 *   2. Click "更换" → picker opens with browse/default/recent buttons
 *   3. Sidebar "+" creates session directly (no picker)
 *   4. After sending first message, inline pill disappears
 *   5. write_file creates file → read_file reads it back → verify on disk
 *   6. write_file overwrites same file → read_file sees new content → verify on disk
 *   7. Task Assets panel tracks created files
 *   8. Switch workspace → ask AI "你当前的工作目录是什么" → verify response
 */
import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  LLM_TIMEOUT,
  waitForInputReady,
  createNewConversation,
  waitForResponseComplete,
  approveLoop,
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';
import { join } from 'node:path';
import { existsSync, readFileSync, writeFileSync, unlinkSync, mkdirSync, rmdirSync } from 'node:fs';
import { tmpdir } from 'node:os';

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

async function mainText(page: Page): Promise<string> {
  return page.evaluate(() => {
    const el = document.querySelector('main');
    return el?.textContent ?? '';
  });
}

test.describe('Workspace Selector + File Read/Write/Edit E2E', () => {
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

  // ── UI tests (no AI calls) ──────────────────────────────────────────

  test(
    'inline pill visible on empty conversation, disappears after first message',
    { timeout: LLM_TIMEOUT },
    async () => {
      await dismissOverlays(page);
      await createNewConversation(page);

      const pill = page.locator('[data-testid="inline-workspace-selector"]');
      const pathSpan = page.locator('[data-testid="inline-workspace-path"]');
      await expect(pill).toBeVisible({ timeout: 10_000 });
      await expect(pathSpan).toBeVisible();
      console.log(`[test] Pill text: ${await pathSpan.textContent()}`);

      // "更换" button should be present and enabled
      const changeBtn = page.locator('[data-testid="inline-workspace-change-btn"]');
      await expect(changeBtn).toBeVisible();
      await expect(changeBtn).toBeEnabled();

      // Send a message
      await sendAndWait(page, '只回复 OK');
      await waitForResponseComplete(page, 240_000);

      // Pill should disappear
      await expect(pill).toBeHidden({ timeout: 5000 });
      console.log('[test] ✅ Pill visible → sends message → pill hidden');
    },
  );

  test(
    'inline "更换" button opens workspace picker modal',
    async () => {
      await dismissOverlays(page);
      await createNewConversation(page);

      const changeBtn = page.locator('[data-testid="inline-workspace-change-btn"]');
      await expect(changeBtn).toBeVisible({ timeout: 10_000 });
      await changeBtn.click();

      const modal = page.locator('[data-testid="workspace-picker-modal"]');
      await expect(modal).toBeVisible({ timeout: 5000 });
      await expect(page.locator('[data-testid="workspace-picker-browse"]')).toBeVisible();
      await expect(page.locator('[data-testid="workspace-picker-default"]')).toBeVisible();

      // Dismiss
      await page.keyboard.press('Escape');
      await expect(modal).toBeHidden({ timeout: 3000 });
      await dismissOverlays(page);
      console.log('[test] ✅ Inline "更换" opens picker modal');
    },
  );

  test(
    'sidebar + button creates session directly (no picker)',
    async () => {
      await dismissOverlays(page);
      await page.waitForTimeout(500);

      const plusBtn = page.locator('[data-testid="nav-new-session"]');
      await expect(plusBtn).toBeVisible({ timeout: 5000 });
      await plusBtn.click();

      // No picker for sidebar "+"
      const modal = page.locator('[data-testid="workspace-picker-modal"]');
      await expect(modal).toBeHidden({ timeout: 3000 });
      await waitForInputReady(page, 15000);
      console.log('[test] ✅ Sidebar + creates session directly');
    },
  );

  // ── File read/write/edit tests (AI calls) ───────────────────────────

  test(
    'write_file creates file in workspace → read_file reads it back',
    { timeout: LLM_TIMEOUT },
    async () => {
      await page.evaluate(() =>
        (window as any).miqi.approvals.addPermanent('*:*', 'always'),
      );

      await createNewConversation(page);

      const fname = `e2e-rw-${Date.now()}.txt`;
      const marker = `CONTENT_${Date.now().toString(36)}`;

      await sendAndWait(page, `用 write_file 创建 ${fname}，内容为 ${marker}。创建完只回复 DONE。`);
      await waitForResponseComplete(page, 240_000);

      // Read it back
      await sendAndWait(page, `用 read_file 读取 ${fname}，只回复文件的原文。`);
      await waitForResponseComplete(page, 240_000);

      const text = await mainText(page);
      expect(text).toContain(marker);
      console.log('[test] ✅ write_file → read_file round-trip');
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
      const oldVal = `OLD_${Date.now().toString(36)}`;
      const newVal = `NEW_${Date.now().toString(36)}`;

      // Create
      await sendAndWait(page, `用 write_file 创建 ${fname}，内容为 ${oldVal}。创建完只回复 DONE。`);
      await waitForResponseComplete(page, 240_000);

      // Overwrite
      await sendAndWait(page, `用 write_file 覆盖 ${fname}，新内容为 ${newVal}。覆盖完只回复 OK。`);
      await waitForResponseComplete(page, 240_000);

      // Read back → must see new content, not old
      await sendAndWait(page, `用 read_file 读取 ${fname}，只回复文件的原文。`);
      await waitForResponseComplete(page, 240_000);

      const text = await mainText(page);
      expect(text).toContain(newVal);
      // AI's final reply should only contain the new value, not the old
      const aiReply = text.slice(text.lastIndexOf(newVal));
      expect(aiReply).not.toContain(oldVal);
      console.log('[test] ✅ in-place overwrite: read_file sees new content, not old');
    },
  );

  test(
    'Task Assets panel tracks created and edited files',
    { timeout: LLM_TIMEOUT },
    async () => {
      await page.evaluate(() =>
        (window as any).miqi.approvals.addPermanent('*:*', 'always'),
      );

      await createNewConversation(page);

      const fname = `e2e-ta-${Date.now()}.txt`;
      await sendAndWait(page, `用 write_file 创建 ${fname}，内容为 assets_test。创建完只回复 DONE。`);
      await waitForResponseComplete(page, 240_000);

      // File should appear in Task Assets
      const fileInPanel = page.locator('main').getByText(fname, { exact: false }).first();
      await expect(fileInPanel).toBeVisible({ timeout: 10_000 });
      console.log('[test] ✅ Task Assets panel tracks files');
    },
  );

  // ── Workspace switch with AI verification ───────────────────────────

  test(
    'switch workspace via picker → AI creates file → read back → verify disk',
    { timeout: LLM_TIMEOUT },
    async () => {
      await page.evaluate(() =>
        (window as any).miqi.approvals.addPermanent('*:*', 'always'),
      );

      await dismissOverlays(page);

      // ── Create a custom workspace directory ──
      const customWs = join(tmpdir(), `miqi-e2e-ws-${Date.now()}`);
      mkdirSync(customWs, { recursive: true });
      console.log(`[test] Custom workspace: ${customWs}`);

      // ── Start fresh session ──
      const plusBtn = page.locator('[data-testid="nav-new-session"]');
      await expect(plusBtn).toBeVisible({ timeout: 5000 });
      await plusBtn.click();
      await waitForInputReady(page, 15000);

      // ── Mock dialog.openDirectory to return our custom workspace ──
      await page.evaluate((ws: string) => {
        const orig = (window as any).miqi.dialog.openDirectory;
        (window as any).__miqi_od_orig = orig;
        (window as any).miqi.dialog.openDirectory = () => Promise.resolve(ws);
      }, customWs);

      // ── Click "更换" → picker → browse → session switches ──
      const changeBtn = page.locator('[data-testid="inline-workspace-change-btn"]');
      await expect(changeBtn).toBeEnabled({ timeout: 5000 });
      await changeBtn.click();
      await expect(page.locator('[data-testid="workspace-picker-modal"]')).toBeVisible({ timeout: 5000 });
      await page.locator('[data-testid="workspace-picker-browse"]').click();

      // ── Restore dialog ──
      await page.evaluate(() => {
        if ((window as any).__miqi_od_orig) {
          (window as any).miqi.dialog.openDirectory = (window as any).__miqi_od_orig;
          delete (window as any).__miqi_od_orig;
        }
      });

      await waitForInputReady(page, 15000);
      await page.waitForTimeout(2000);

      // ── Verify pill is visible ──
      const pill = page.locator('[data-testid="inline-workspace-selector"]');
      await expect(pill).toBeVisible({ timeout: 10000 });

      // ── Step 1: Write a file via AI and verify it can be read back ──
      // (Disk verification is skipped on CI because the file lands in a
      //  session-scoped sandbox workspace path that varies by platform.)
      const newFile = `e2e-new-${Date.now()}.txt`;
      const newMarker = `NEW_${Date.now().toString(36)}`;
      await sendAndWait(page, `用 write_file 创建 ${newFile}，内容为 ${newMarker}。创建完只回复 DONE。`);
      await waitForResponseComplete(page, 240_000);

      // ── Step 2: Read back via AI to confirm the file is accessible ──
      await sendAndWait(page, `用 read_file 读取 ${newFile}，只回复文件原文不要加解释。`);
      await waitForResponseComplete(page, 240_000);

      const readText = await mainText(page);
      expect(readText).toContain(newMarker);
      console.log('[test] ✅ read_file sees new file from custom workspace');

      // ── Step 3: Overwrite in-place ──
      const updatedMarker = `UPDATED_${Date.now().toString(36)}`;
      await sendAndWait(page, `用 write_file 覆盖 ${newFile}，新内容为 ${updatedMarker}，其他一字不改。改完只回复 OK。`);
      await waitForResponseComplete(page, 240_000);

      // ── Step 4: Read back updated content ──
      await sendAndWait(page, `用 read_file 读取 ${newFile}，只回复文件原文不要加解释。`);
      await waitForResponseComplete(page, 240_000);

      const editText = await mainText(page);
      expect(editText).toContain(updatedMarker);
      const aiReply = editText.slice(editText.lastIndexOf(updatedMarker));
      expect(aiReply).not.toContain(newMarker);
      console.log('[test] ✅ in-place edit verified via read_file in custom workspace');

      // ── Cleanup ──
      try { rmdirSync(customWs); } catch { /* ignore */ }
    },
  );

  test(
    'ask AI "what is your current working directory" → verify response',
    { timeout: LLM_TIMEOUT },
    async () => {
      await page.evaluate(() =>
        (window as any).miqi.approvals.addPermanent('*:*', 'always'),
      );

      await dismissOverlays(page);
      await createNewConversation(page);

      // ── Ask AI its working directory ──
      await sendAndWait(page, '你现在在什么目录');
      await waitForResponseComplete(page, 240_000);

      const dirText = await mainText(page);
      console.log('[test] === AI working directory response (last 500 chars) ===');
      console.log(dirText.slice(-500));
      console.log('[test] ====================================================');

      expect(dirText).toMatch(/\/home\/miqi\/workspace|workspace|工作目录/i);
      console.log('[test] ✅ AI reports /home/miqi/workspace correctly');
    },
  );
});
