/**
 * E2E test (SANDBOX ON): create custom dir with files → switch workspace →
 * verify AI operates inside the sandbox.
 *
 * Differs from workspace-file-read-edit.spec.ts only in that the sandbox
 * is LEFT ENABLED.  Inside the bwrap sandbox:
 *   - The AI's working directory is always /home/miqi/workspace (the
 *     per-session private sandbox dir, NOT the host customWs).
 *   - write_file / read_file operate on the sandbox filesystem and the
 *     host workspace is NOT bind-mounted (Issue #221 isolation).
 *   - WSL sandboxes bind-mount /mnt, so host absolute paths (C:\... →
 *     /mnt/c/...) remain reachable when the AI is told the full path.
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
  waitForSandboxReady,
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

/** Text of the LAST assistant bubble — the model's newest reply. */
async function lastAssistantReply(page: Page): Promise<string> {
  return (await page
    .locator('[data-testid="chat-message-assistant"]')
    .last()
    .textContent()) || '';
}

test.describe('Workspace Switch E2E (Sandbox ON)', () => {
  let electronApp: ElectronApplication;
  let page: Page;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
    // Ensure the sandbox is fully initialized BEFORE the test asserts
    // sandbox behavior — otherwise exec silently falls back to host.
    const ready = await waitForSandboxReady(page, 300_000);
    if (!ready) {
      throw new Error('Sandbox manager did not become ready within 300s');
    }
  }, 420_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp);
  });

  test(
    'sandbox ON: custom dir → switch workspace → AI operates in sandbox',
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
      const resolvedCustomWs = realpathSync(customWs);
      const basename = customWs.split(/[/\\]/).pop()!;

      // ── 2. Start a fresh session ──
      await createNewConversation(page);

      // ── 3. Mock dialog.openDirectory in the MAIN process (contextBridge
      //    freezes window.miqi.* so renderer mocks are dropped) ──
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
      expect(pillText).not.toBe('默认工作目录');
      const pillPathMatch =
        pillText!.includes(customWs) || pillText!.includes(resolvedCustomWs);
      expect(
        pillPathMatch || pillText!.includes(basename),
        `expected pill "${pillText}" to contain "${customWs}" or "${resolvedCustomWs}" or "${basename}"`,
      ).toBe(true);
      console.log(`[test] ✅ Pill reflects custom workspace`);

      // ── 6. Confirm sandbox is ON (this is the point of this spec) ──
      const sandboxOn = await page.evaluate(async () => {
        try {
          const s = await (window as any).miqi.runtime.status();
          return s?.sandbox_available === true;
        } catch { return false; }
      });
      console.log(`[test] Sandbox ON: ${sandboxOn}`);
      expect(sandboxOn, 'sandbox must be enabled for this spec').toBe(true);

      // ── 7. Verify session metadata has the workspace ──
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

      // ── 8. Ask AI what its working directory is — inside the sandbox
      //    this should be /home/miqi/workspace (the per-session sandbox
      //    dir), NOT the host customWs path. ──
      await sendMessage(page, '用 exec 工具执行 pwd 获取当前工作目录，只回复 pwd 输出，不要解释。');
      await waitForResponseComplete(page);
      const pwdReply = await lastAssistantReply(page);
      console.log(`[test] AI pwd reply: ${pwdReply?.slice(0, 300)}`);
      // In sandbox the cwd is always the sandbox workspace mount.
      expect(
        pwdReply.includes('/home/miqi/workspace'),
        `expected sandbox pwd reply to contain /home/miqi/workspace, got "${pwdReply?.slice(0, 200)}"`,
      ).toBe(true);
      console.log(`[test] ✅ AI reports sandbox workspace /home/miqi/workspace`);

      // ── 9. Ask AI to write a file in the sandbox, then read it back —
      //    verifies the sandbox filesystem round-trip works. ──
      const marker = `WS_SANDBOX_${Date.now().toString(36)}`;
      const markerFile = `_e2e_sandbox_file.txt`;
      await sendMessage(page,
        `用 write_file 工具创建文件 ${markerFile}，内容为 "${marker}"。只回复是否成功。`
      );
      await waitForResponseComplete(page);
      const writeReply = await lastAssistantReply(page);
      console.log(`[test] AI write reply: ${writeReply?.slice(0, 200)}`);
      expect(
        /成功|Success|written|创建/.test(writeReply),
        `expected write_file success reply, got "${writeReply?.slice(0, 200)}"`,
      ).toBe(true);
      console.log(`[test] ✅ AI wrote file inside sandbox`);

      // Read it back inside the sandbox
      await sendMessage(page,
        `用 read_file 工具读取文件 ${markerFile}，只回复文件内容原文，不要解释。`
      );
      await waitForResponseComplete(page);
      const readReply = await lastAssistantReply(page);
      console.log(`[test] AI read reply: ${readReply?.slice(0, 200)}`);
      expect(
        readReply.includes(marker),
        `expected read reply to contain "${marker}", got "${readReply?.slice(0, 200)}"`,
      ).toBe(true);
      console.log(`[test] ✅ AI read file back inside sandbox`);

      // ── 10. Probe: can the AI read the HOST customWs file via absolute
      //    path?  WSL sandboxes bind-mount /mnt → C:\... → /mnt/c/...
      //    (Best-effort probe — logged, not asserted.)
      try {
        await sendMessage(page,
          `用 read_file 读取绝对路径 ${join(customWs, preExistingFile)}，只回复文件内容原文，不要解释。`
        );
        await waitForResponseComplete(page);
        const probeReply = await lastAssistantReply(page);
        console.log(`[test] Sandbox absolute-path read probe: ${probeReply?.slice(0, 200)}`);
        if (probeReply.includes(preExistingContent)) {
          console.log('[test] ✅ Sandbox CAN read host customWs via /mnt absolute path');
        } else {
          console.log('[test] ⚠️ Sandbox cannot read host customWs via absolute path');
        }
      } catch (e) {
        console.log(`[test] Absolute-path probe skipped: ${e}`);
      }

      // ── Cleanup ──
      try { unlinkSync(join(customWs, preExistingFile)); } catch { /* ignore */ }
      try { unlinkSync(join(customWs, 'notes.md')); } catch { /* ignore */ }
      try { rmdirSync(customWs); } catch { /* ignore */ }
    },
  );
});
