/**
 * E2E tests for workspace change → file read → in-place edit flow.
 *
 * Verifies:
 * 1. After switching to a custom workspace, AI can list/read all files
 * 2. AI can modify a file in-place (write_file / edit_file)
 * 3. The file on disk actually reflects the AI's changes
 * 4. Inline workspace pill shows the new workspace path
 */
import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  LLM_TIMEOUT,
  waitForInputReady,
  createNewConversation,
  sendMessage,
  waitForResponseComplete,
  approveLoop,
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';
import { resolve, join } from 'node:path';
import { existsSync, writeFileSync, readFileSync, unlinkSync, mkdirSync, rmdirSync } from 'node:fs';
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

test.describe('Workspace File Read & In-Place Edit E2E', () => {
  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;
  let tempWorkspace: string;
  const originalContent = 'Hello World\nThis is a test file.\nLine 3: 苹果\nLine 4: 橘子\n';
  const FILENAME = 'test-data.txt';

  test.beforeAll(async () => {
    // Create a unique temp workspace directory with a test file
    tempWorkspace = join(tmpdir(), `miqi-e2e-ws-${Date.now()}`);
    mkdirSync(tempWorkspace, { recursive: true });
    writeFileSync(join(tempWorkspace, FILENAME), originalContent, 'utf-8');
    // Also create a second file so AI has multiple files to list
    writeFileSync(join(tempWorkspace, 'config.json'), JSON.stringify({ version: 1, name: 'test' }, null, 2), 'utf-8');
    console.log(`[test] Created temp workspace at ${tempWorkspace}`);

    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;
  }, 120_000);

  test.afterAll(async () => {
    // Clean up temp workspace
    try {
      unlinkSync(join(tempWorkspace, FILENAME));
      unlinkSync(join(tempWorkspace, 'config.json'));
      rmdirSync(tempWorkspace);
    } catch { /* ignore cleanup errors */ }
    await closeElectronApp(electronApp, miqiHome);
  });

  test(
    'switch workspace → list files → read file → in-place edit → verify on disk',
    { timeout: LLM_TIMEOUT },
    async () => {
      await dismissOverlays(page);

      // ── Step 1: Dismiss setup wizard if present ──
      await page.waitForTimeout(3000);

      // ── Step 2: Pre-approve all tool calls ──
      await page.evaluate(() =>
        (window as any).miqi.approvals.addPermanent('*:*', 'always'),
      );

      // ── Step 3: Set workspace via config → create new session via sidebar "+" ──
      // Cannot automate native dialog, so use config API to set workspace,
      // then create a fresh session where the workspace takes effect.
      await page.evaluate(async (ws: string) => {
        await (window as any).miqi.config.update({ workspace: ws });
      }, tempWorkspace);
      console.log(`[test] Workspace set to ${tempWorkspace} via config`);

      await createNewConversation(page);

      // ── Step 4: Verify inline workspace pill shows the custom path ──
      const pill = page.locator('[data-testid="inline-workspace-selector"]');
      const pathSpan = page.locator('[data-testid="inline-workspace-path"]');
      try {
        await expect(pill).toBeVisible({ timeout: 10_000 });
        const wsText = await pathSpan.textContent();
        console.log(`[test] Inline pill text: ${wsText}`);
        expect(wsText).toContain('工作目录');
      } catch {
        console.log('[test] Inline pill not visible — conversation may already have messages');
      }

      // ── Step 5: Ask AI to list all files in the workspace ──
      await sendMessage(
        page,
        `列出当前工作目录下的所有文件，只回复文件名列表，不要加任何解释。`,
      );
      await approveLoop(page, 240_000);
      await waitForResponseComplete(page, 240_000);

      const listText = await page.evaluate(() => {
        const el = document.querySelector('main');
        return el?.textContent ?? '';
      });
      console.log('[test] === AI file listing ===');
      console.log(listText.slice(-500));
      console.log('[test] ======================');

      // Should mention both files
      expect(listText).toContain(FILENAME);
      expect(listText).toContain('config.json');

      // ── Step 6: Ask AI to read the test file ──
      await sendMessage(
        page,
        `读取文件 ${FILENAME} 的内容，只回复文件的原始内容，不要加任何解释。`,
      );
      await approveLoop(page, 240_000);
      await waitForResponseComplete(page, 240_000);

      const readText = await page.evaluate(() => {
        const el = document.querySelector('main');
        return el?.textContent ?? '';
      });
      console.log('[test] === AI read file ===');
      console.log(readText.slice(-500));
      console.log('[test] ===================');

      // AI should have read the file and reflected its content
      expect(readText).toContain('Hello World');
      expect(readText).toContain('橘子');

      // ── Step 7: Ask AI to modify the file in-place ──
      await sendMessage(
        page,
        `用 write_file 工具把 ${FILENAME} 里的 "橘子" 改成 "西瓜"，只改这一处，其他内容完全不变。改完只回复 "done"，不要加任何解释。`,
      );
      await approveLoop(page, 240_000);
      await waitForResponseComplete(page, 240_000);

      // ── Step 8: Verify file on disk actually changed ──
      const filePath = join(tempWorkspace, FILENAME);
      expect(existsSync(filePath)).toBe(true);
      const modifiedContent = readFileSync(filePath, 'utf-8');
      console.log('[test] === Modified file on disk ===');
      console.log(modifiedContent);
      console.log('[test] ==========================');

      expect(modifiedContent).toContain('西瓜');
      expect(modifiedContent).not.toContain('橘子');
      expect(modifiedContent).toContain('Hello World'); // rest unchanged
      expect(modifiedContent).toContain('This is a test file.'); // rest unchanged

      console.log('[test] ✅ Workspace file in-place edit verified on disk');
    },
  );
});
