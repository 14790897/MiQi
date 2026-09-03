/**
 * E2E: 工具级失败（会话隔离 PermissionError）渲染为中性警示行，而非红色报错框。
 *
 * Regression coverage for issue #921.  A tool-level failure (ToolErrorEvent,
 * recoverable=True) is part of the agent's normal self-correction loop — the
 * model receives the failure result and adapts.  Rendering it with the red
 * danger bubble (ChatConsole role 'error') makes a routine self-correction
 * look like a system crash, indistinguishable from turn-level errors
 * (timeout / provider failure).
 *
 * The backend emits ToolErrorEvent on the chat progress channel (the exact
 * payload produced by orchestrator._sanitize_exc_for_ui → loop.py's generic
 * event forwarding).  The frontend only registers its progress listeners
 * while a turn is in flight, so the spec starts a real send against
 * scripts/mock_hang.py (a provider mock that never responds, keeping the
 * turn alive), then injects the ToolErrorEvent payload into the REAL
 * renderer through the same IPC channel the bridge uses:
 *   - the message reaches the UI (transparency preserved),
 *   - it renders as a muted ⚠️ warning row, NOT in the danger color —
 *     pre-fix the same payload rendered as the red error bubble and this
 *     assertion fails,
 *   - a screenshot is saved to docs/screenshots/ for the PR.
 *
 * Run:
 *   cd apps/desktop && npm run build && npx playwright test \
 *     --config=playwright.config.ts --project=electron \
 *     -g "session isolation tool error"
 */

import { test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import { spawn, type ChildProcess } from 'node:child_process';
import { join } from 'node:path';
import {
  sendMessage,
  waitForBridgeInitialized,
  launchElectronApp,
  closeElectronApp,
  createNewConversation,
  APPS_DESKTOP,
} from './helpers/electron-setup';

const REPO_ROOT = join(APPS_DESKTOP, '..', '..');

/** Danger colors used by the red error bubble (dark + light theme). */
const DANGER_COLORS = ['rgb(255, 97, 97)', 'rgb(192, 64, 64)'];

/** The exact ToolErrorEvent payload the backend sends for the session-
 *  isolation PermissionError (message shaped by _sanitize_exc_for_ui). */
const TOOL_ERROR_PAYLOAD = {
  event: 'ToolErrorEvent',
  data: {
    turn_id: 'e2e-turn',
    tool_name: 'read_file',
    tool_call_id: 'call_cross_read',
    message:
      'PermissionError: 路径位于其他会话的 files 目录内——会话隔离禁止跨会话访问。 不要重试或枚举 sessions[path]',
    recoverable: true,
  },
};

/** Start scripts/mock_hang.py on an ephemeral port. */
async function startMockHang(): Promise<{ proc: ChildProcess; mockUrl: string }> {
  const python = process.env.MIQI_PYTHON_PATH || 'python';
  const port = 20000 + Math.floor(Math.random() * 20000);
  const proc = spawn(python, [join(REPO_ROOT, 'scripts', 'mock_hang.py'), String(port)], {
    cwd: REPO_ROOT,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
    windowsHide: true,
  });

  let readyUrl = '';
  let stderrTail = '';
  proc.stdout?.on('data', (d) => {
    const t = String(d);
    console.log(`[mock-hang] ${t.trim()}`);
    const m = t.match(/http:\/\/127\.0\.0\.1:(\d+)\/v1/);
    if (m) readyUrl = `http://127.0.0.1:${m[1]}/v1`;
  });
  proc.stderr?.on('data', (d) => {
    stderrTail = (stderrTail + String(d)).slice(-2000);
  });
  proc.on('exit', (code) => console.log(`[test] mock hang server exited: ${code}`));

  const deadline = Date.now() + 30_000;
  while (!readyUrl && Date.now() < deadline) {
    if (proc.exitCode !== null) {
      throw new Error(`mock hang server exited early (code ${proc.exitCode}): ${stderrTail}`);
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  if (!readyUrl) {
    proc.kill();
    throw new Error(`mock hang startup line not seen in 30s: ${stderrTail}`);
  }
  console.log(`[test] mock hang ready at ${readyUrl}`);
  return { proc, mockUrl: readyUrl };
}

test.describe('Session isolation tool error rendering', () => {
  // macOS CI cannot run this spec: the runner's undici fetch fails against
  // a local 127.0.0.1 listener and the spawned mock's stdout pipe never
  // delivers (same trimming strategy as confirm-card.spec.ts #710).
  test.skip(
    process.platform === 'darwin' && !!process.env.CI,
    'macOS CI cannot reach the local mock server'
  );

  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;
  let mockServer: ChildProcess;

  test.beforeAll(async () => {
    const mock = await startMockHang();
    mockServer = mock.proc;
    const fixture = await launchElectronApp((config: any) => {
      // Point EVERY configured provider at the hanging mock (same pattern as
      // bridge-chinese-error.spec.ts).  Pin the default model to deepseek so
      // the patched provider is always the one exercised — no real API call
      // may ever leave this spec.
      const providers = config.providers ?? {};
      for (const [name, p] of Object.entries(providers)) {
        if (p && typeof p === 'object') {
          (p as any).apiBase = mock.mockUrl;
          if (!(p as any).apiKey) (p as any).apiKey = 'mock-key';
        }
      }
      config.agents = config.agents ?? {};
      config.agents.defaults = config.agents.defaults ?? {};
      config.agents.defaults.model = 'deepseek/deepseek-chat';
      const deepseek = (providers as any).deepseek ?? {};
      deepseek.apiBase = mock.mockUrl;
      deepseek.apiKey = `${deepseek.apiKey ?? 'sk-mock-key'}`;
      (providers as any).deepseek = deepseek;
      config.providers = providers;
      // No WSL sandbox needed — the frontend rendering contract is what is
      // under test here.
      config.tools = { ...config.tools, sandbox: { ...config.tools?.sandbox, enabled: false } };
    });
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;

    await waitForBridgeInitialized(page);
  });

  test.afterAll(async () => {
    mockServer?.kill();
    await closeElectronApp(electronApp, miqiHome);
  });

  test(
    'ToolErrorEvent renders as a neutral warning row, not a red error bubble',
    { timeout: 120_000 },
    async () => {
      // createNewConversation returns the session TITLE; the progress
      // channel filters on session_key, so resolve the real key via the
      // sessions API (newest session by created_at is the one just made).
      const title = await createNewConversation(page);
      const sessionKey = await page.evaluate(async (expectedTitle) => {
        const list = await (window as any).miqi.sessions.list();
        const sessions = (list?.sessions ?? []) as Array<{
          key: string;
          title?: string;
          created_at?: string;
        }>;
        const byTitle = sessions.find((s) => s.title === expectedTitle);
        if (byTitle) return byTitle.key;
        sessions.sort((a, b) => (a.created_at ?? '').localeCompare(b.created_at ?? ''));
        return sessions[sessions.length - 1]?.key ?? '';
      }, title);
      expect(sessionKey, 'session key must resolve').not.toBe('');
      console.log(`[tool-error-neutral] active session key: ${sessionKey}`);

      // Start a real send — the frontend registers its chat event listeners
      // only while a turn is in flight.  The hanging mock keeps the turn
      // alive for the rest of the test.
      await sendMessage(page, `会话隔离渲染回归测试 ${Date.now()}`);
      await page.waitForTimeout(3000);

      // Inject the events the backend would emit during a real turn, on the
      // same IPC channel the bridge forwards ('chat:progress'): first a
      // tool-call begin row (like ToolCallBeginEvent), then the
      // ToolErrorEvent itself.
      const injectProgress = (payload: Record<string, unknown>) =>
        electronApp.evaluate(({ BrowserWindow }, p) => {
          const win = BrowserWindow.getAllWindows().find(
            (w) => w.getTitle() === 'MiQroForge Desktop'
          );
          if (!win) throw new Error('main window not found');
          win.webContents.send('chat:progress', p);
        }, payload);

      await injectProgress({
        text: 'read_file 读取其他会话文件',
        tool_hint: true,
        tool_call_id: 'call_cross_read',
        session_key: sessionKey,
      });
      await injectProgress({ ...TOOL_ERROR_PAYLOAD, session_key: sessionKey });

      // 1. The isolation message must reach the UI (transparency preserved),
      //    rendered as a ⚠️ warning row.
      await expect
        .poll(
          () =>
            page.evaluate(() =>
              Array.from(document.querySelectorAll('div')).some((d) =>
                (d.textContent ?? '').includes('⚠️ PermissionError: 路径位于其他会话')
              )
            ),
          { timeout: 15_000 }
        )
        .toBe(true);
      console.log('[tool-error-neutral] ✅ warning row is visible');

      // 2. …but NOT in the danger color.  Pre-fix, the same payload rendered
      //    as the red error bubble (color: var(--danger)).
      const dangerHits = await page.evaluate((dangerColors) => {
        const hits: string[] = [];
        for (const el of Array.from(document.querySelectorAll('div, span, p'))) {
          const text = (el as HTMLElement).textContent ?? '';
          if (!text.includes('会话隔离禁止跨会话访问')) continue;
          const color = getComputedStyle(el).color;
          if ((dangerColors as string[]).includes(color)) hits.push(color);
        }
        return hits;
      }, DANGER_COLORS);
      expect(dangerHits, 'isolation message must not render in the danger color').toHaveLength(0);
      console.log('[tool-error-neutral] ✅ no danger-colored element carries the message');

      // Screenshot for the PR (before/after evidence).
      await page.screenshot({
        path: join(REPO_ROOT, 'docs', 'screenshots', 'tool-error-warning-after.png'),
      });
      console.log('[tool-error-neutral] ✅ screenshot saved to docs/screenshots/');
    }
  );
});
