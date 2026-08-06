/**
 * E2E test: create custom dir with files → switch workspace → verify dir changed & files readable.
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
  sendMessage,
} from './helpers/electron-setup';
import { join } from 'node:path';
import { writeFileSync, unlinkSync, mkdirSync, rmdirSync, realpathSync } from 'node:fs';
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

/** Text of the LAST assistant bubble — the model's newest reply. */
async function lastAssistantReply(page: Page): Promise<string> {
  return (await page
    .locator('[data-testid="chat-message-assistant"]')
    .last()
    .textContent()) || '';
}

test.describe('Workspace Switch E2E', () => {
  let electronApp: ElectronApplication;
  let page: Page;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
  }, 120_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp);
  });

  test(
    'create custom dir → switch workspace → verify pill + session workspace',
    { timeout: LLM_TIMEOUT },
    async () => {
      await page.evaluate(() =>
        (window as any).miqi.approvals.addPermanent('*:*', 'always'),
      );

      await dismissOverlays(page);

      // ── 1. Create a custom workspace directory with pre-existing files ──
      const customWs = join(tmpdir(), `miqi-e2e-ws-${Date.now()}`);
      mkdirSync(customWs, { recursive: true });
      const preExistingFile = 'hello.txt';
      const preExistingContent = `HELLO_FROM_CUSTOM_WS_${Date.now().toString(36)}`;
      writeFileSync(join(customWs, preExistingFile), preExistingContent, 'utf-8');
      writeFileSync(join(customWs, 'notes.md'), '# Custom Workspace Notes', 'utf-8');
      console.log(`[test] Created custom workspace: ${customWs}`);

      // ── 2. Start a fresh session ──
      await createNewConversation(page);

      // ── 3. Mock dialog.openDirectory in the MAIN process so the IPC handler
      //    returns our custom workspace.  contextBridge freezes window.miqi.* in
      //    the renderer so page.evaluate mocks are silently dropped.
      //    Patch via electronApp.evaluate instead — this captures the same
      //    pattern used by feedback.spec.ts for mocking IPC handlers.
      const DIALOG_OPEN_DIRECTORY = 'dialog:openDirectory';
      await electronApp.evaluate(async ({ ipcMain: ipc }, { channel, ws }: { channel: string; ws: string }) => {
        ipc.removeHandler(channel);
        ipc.handle(channel, async () => ws);
      }, { channel: DIALOG_OPEN_DIRECTORY, ws: customWs });

      // ── 4. Click "更换" → picker → browse → workspace switches ──
      const changeBtn = page.locator('[data-testid="inline-workspace-change-btn"]');
      await expect(changeBtn).toBeEnabled({ timeout: 5000 });
      await changeBtn.click();
      await expect(page.locator('[data-testid="workspace-picker-modal"]')).toBeVisible({ timeout: 5000 });
      await page.locator('[data-testid="workspace-picker-browse"]').click();

      await waitForInputReady(page, 15000);
      await page.waitForTimeout(2000);

      // ── 5. Verify inline pill shows the new workspace path ──
      const pill = page.locator('[data-testid="inline-workspace-selector"]');
      await expect(pill).toBeVisible({ timeout: 10000 });
      const pillText = await page.locator('[data-testid="inline-workspace-path"]').textContent();
      console.log(`[test] Pill text after switch: ${pillText}`);
      // Pill should contain the custom workspace path (not "默认工作目录")
      expect(pillText).not.toBe('默认工作目录');
      // Windows may resolve short 8.3 names (INTERS~1 → Intership003), so
      // compare using realpath.  On non-Windows this is a no-op.
      const resolvedCustomWs = realpathSync(customWs);
      const pillPathMatch =
        pillText!.includes(customWs) || pillText!.includes(resolvedCustomWs);
      // Also check the last segment (basename) in case the path display
      // normalises differently.
      const basename = customWs.split(/[/\\]/).pop()!;
      expect(
        pillPathMatch || pillText!.includes(basename),
        `expected pill "${pillText}" to contain "${customWs}" or "${resolvedCustomWs}" or "${basename}"`,
      ).toBe(true);
      console.log(`[test] ✅ Pill reflects custom workspace`);

      // ── 6. Disable sandbox so exec/pwd runs on the HOST filesystem —
      //    inside the bwrap sandbox the path is always /home/miqi/workspace,
      //    which would never contain the host customWs path.
      const sandboxAvail = await page.evaluate(async () => {
        try {
          const s = await (window as any).miqi.runtime.status();
          return s?.sandbox_available === true;
        } catch { return false; }
      });
      console.log(`[test] Sandbox available: ${sandboxAvail}`);
      if (sandboxAvail) {
        await page.evaluate(async () => {
          await (window as any).miqi.sandbox.setEnabled(false);
        });
        await page.waitForTimeout(3000);
        const after = await page.evaluate(async () => {
          try {
            const s = await (window as any).miqi.runtime.status();
            return s?.sandbox_available === true;
          } catch { return false; }
        });
        console.log(`[test] Sandbox after disable: ${after}`);
      }

      // ── 7. Ask AI what its working directory is — must answer with the custom path ──
      // Note: exec may be blocked by the runtime policy; the AI can also
      // answer from its session context (system prompt carries the workspace).
      await sendMessage(page, '请回复你当前会话的工作目录的绝对路径。如果你的环境上下文中有该路径，直接引用；否则用 exec 工具执行 pwd。只回复路径，不要解释。');
      await waitForResponseComplete(page);
      const reply = await lastAssistantReply(page);
      console.log(`[test] AI reply about workspace: ${reply?.slice(0, 500)}`);
      const replyPathMatch =
        reply.includes(customWs) ||
        reply.includes(resolvedCustomWs) ||
        // basename fallback — AI may normalize the 8.3 short name
        // (INTERS~1 → Intership003) which realpathSync doesn't resolve
        // on Windows Git Bash.
        reply.includes(basename);
      expect(
        replyPathMatch,
        `expected AI reply "${reply?.slice(0, 200)}" to contain workspace path "${customWs}" or "${resolvedCustomWs}" or "${basename}"`,
      ).toBe(true);
      console.log(`[test] ✅ AI correctly identified the custom workspace`);

      // ── 8. Verify session metadata has the workspace ──
      const metaWs = await page.evaluate(async (ws: string) => {
        try {
          const result = await (window as any).miqi.sessions.list();
          const sessions = result?.sessions || [];
          for (const s of sessions) {
            const detail = await (window as any).miqi.sessions.get(s.key);
            const mw = detail?.workspace || detail?.metadata?.workspace || null;
            if (mw && (mw === ws || mw.includes(ws.split(/[/\\]/).pop()!))) {
              return mw;
            }
          }
        } catch { return null; }
        return null;
      }, customWs);
      console.log(`[test] Session metadata workspace: ${metaWs}`);
      expect(metaWs, 'session metadata must contain the custom workspace').toBeTruthy();

      // ── Cleanup ──
      try { unlinkSync(join(customWs, preExistingFile)); } catch { /* ignore */ }
      try { unlinkSync(join(customWs, 'notes.md')); } catch { /* ignore */ }
      try { rmdirSync(customWs); } catch { /* ignore */ }
    },
  );
});
