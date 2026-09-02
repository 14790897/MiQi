/**
 * E2E: 路径归一化交付验证 —— agent 不被提示任何路径信息，自己创建文件后，
 * 能否从工具结果中获取并报告 REAL 落盘路径（sessions/<key>/files/）。
 *
 * 背景（miqibug 路径归一化）：write_file 对工作区根路径做会话隔离归一化，
 * 落盘路径 ≠ 传入路径。修复后在工具结果里双声明请求路径与真实路径。
 * 本 spec 验证端到端：用户只说"创建文件"，不告诉路径；随后追问"文件在哪"，
 * agent 必须能答出含 sessions 的真实路径（而不是复述请求路径/相对名）。
 *
 * Run:
 *   cd apps/desktop
 *   npx playwright test --config=playwright.config.ts --project=electron delivery-path-truth.spec.ts
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import { join, resolve } from 'node:path';
import { existsSync, readdirSync, realpathSync } from 'node:fs';
import {
  LLM_TIMEOUT,
  waitForInputReady,
  sendMessage,
  waitForResponseComplete,
  waitForBridgeInitialized,
  launchElectronApp,
  closeElectronApp,
  createNewConversation,
} from './helpers/electron-setup';

// ─── Helpers ──────────────────────────────────────────────────────────

/** Find the first session files dir containing *filename* under
 *  <miqiHome>/workspace/sessions/. Returns the full path or null. */
function findFileInSessionDirs(miqiHome: string, filename: string): string | null {
  const sessionsDir = join(miqiHome, 'workspace', 'sessions');
  if (!existsSync(sessionsDir)) return null;
  for (const entry of readdirSync(sessionsDir, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const candidate = join(sessionsDir, entry.name, 'files', filename);
    if (existsSync(candidate)) {
      // Canonicalize 8.3 short names (INTERS~1 → Intership003): the bridge
      // reports the long canonical form while Node's tmpdir may hand out the
      // short alias for the same directory.  Only the native realpath
      // expands short names — the JS implementation keeps the short form.
      const nativeRealpath = (realpathSync as unknown as { native: (p: string) => string }).native;
      try {
        return nativeRealpath(candidate);
      } catch {
        return candidate;
      }
    }
  }
  return null;
}

/** Dismiss stale Radix overlays that can swallow the first Enter (cold-start). */
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

/** sendMessage with one retry — the first Enter of a cold app can race the
 *  optimistic-UI bubble mount. */
async function sendMessageWithRetry(page: Page, text: string) {
  await dismissOverlays(page);
  for (let attempt = 0; ; attempt++) {
    try {
      await sendMessage(page, text);
      return;
    } catch {
      if (attempt >= 1) throw new Error('sendMessage failed after retries');
      console.log(`[test] send failed (attempt ${attempt + 1}) — retrying`);
      await page.waitForTimeout(1000);
      const textarea = page.locator('[data-testid="chat-input-container"] textarea');
      await textarea.fill('').catch(() => {});
      await dismissOverlays(page);
    }
  }
}

// ─── Suite ────────────────────────────────────────────────────────────

test.describe('Delivery Path Truth E2E', () => {
  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp((config) => {
      // Deterministic native path: no WSL sandbox in this spec.
      config.tools = { ...config.tools, sandbox: { ...config.tools?.sandbox, enabled: false } };
    });
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;

    await waitForBridgeInitialized(page);
  });

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
  });

  test('agent reports the real normalized path without being told', async () => {
    test.setTimeout(LLM_TIMEOUT * 2);
    const marker = `PATH_PROBE_${Date.now()}`;
    const filename = `path_probe_${Date.now()}.md`;

    await createNewConversation(page);

    // ── 第一轮：只要求创建文件，不告知任何路径/目录信息 ──
    const createMessage = `请创建一个文件 ${filename}，内容为 "${marker}"。创建完成后只回复"完成"。`;
    let created = false;
    for (let attempt = 0; attempt < 2 && !created; attempt++) {
      await sendMessageWithRetry(page, createMessage);
      await waitForResponseComplete(page, 240_000);
      created = findFileInSessionDirs(miqiHome, filename) !== null;
      if (!created) {
        console.log(`[test] ⚠️ file not created (attempt ${attempt + 1}) — retrying send`);
      }
    }
    // 归一化落盘：文件必须出现在 sessions/*/files/（会话隔离），并保留真实绝对路径
    let realPath: string | null = null;
    await expect
      .poll(
        async () => {
          realPath = findFileInSessionDirs(miqiHome, filename);
          return realPath !== null;
        },
        { timeout: 30_000 }
      )
      .toBe(true);
    if (!realPath) throw new Error('file was never normalized into a session files dir');
    console.log(`[test] ✅ File normalized into ${realPath}`);

    // ── 第二轮：追问实际路径，不提供任何线索 ──
    // 只断言追问后新增的那条 assistant 回复——整个聊天区文本里早前的
    // 工具结果已经包含会话路径，读全文会导致假通过（CodeRabbit 评审）。
    // 追问回合同样带重试：真实 LLM 偶尔对追问只回"完成"不答路径
    // （与创建回合的 no-op turn 同类 flake）。
    const assistantBubbles = page.locator('[data-testid="chat-message-assistant"]');
    const norm = (s: string) => s.replace(/\\/g, '/').toLowerCase();
    let reply = '';
    for (let attempt = 0; attempt < 2; attempt++) {
      const bubblesBefore = await assistantBubbles.count();
      await sendMessageWithRetry(
        page,
        `你刚才创建的文件 ${filename} 实际保存在哪里？请只回复该文件的完整绝对路径。`
      );
      await waitForResponseComplete(page, 120_000);
      await expect
        .poll(async () => assistantBubbles.count(), { timeout: 30_000 })
        .toBeGreaterThan(bubblesBefore);
      reply = (await assistantBubbles.last().textContent()) || '';
      if (norm(reply).includes(norm(realPath))) break;
      console.log(`[test] ⚠️ follow-up answer missed the path (attempt ${attempt + 1}) — retrying`);
    }

    // 核心断言：追问回复必须包含真实落盘的完整绝对路径（精确匹配；
    // 归一化分隔符/大小写以容忍平台差异，但仍要求整条路径完整出现）。
    expect(norm(reply)).toContain(norm(realPath));
    console.log(`[test] ✅ Agent reported the exact real path for ${filename}`);
  });
});
