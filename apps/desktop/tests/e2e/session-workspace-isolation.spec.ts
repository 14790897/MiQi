/**
 * E2E: Session workspace isolation for file writes.
 *
 * Regression coverage for the path-normalization fix (miqibug 路径归一化):
 * write_file with an ABSOLUTE path under the default workspace root must
 * land at EXACTLY that path — the reported path always equals the requested
 * path — instead of being silently redirected into the per-session workspace
 * `<workspace>/sessions/<key>/files/`.
 *
 * Verifies:
 *   1. Agent writes with an absolute workspace-root path → file lands at the
 *      workspace root, NOT in sessions/<safe_key>/files/.
 *   2. The file still appears in the Task Assets panel.
 *   3. A second session starts with an empty Task Assets panel (isolation).
 *
 * The sandbox is disabled via patchConfig so the native (no-sandbox) path
 * is exercised deterministically.
 *
 * Run:
 *   cd apps/desktop
 *   npx playwright test --config=playwright.config.ts --project=electron session-workspace-isolation.spec.ts
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import { join, resolve } from 'node:path';
import { existsSync, readdirSync } from 'node:fs';
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
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

async function waitForFileInPanel(page: Page, filename: string, timeout = 30_000) {
  const assetsPanel = page.getByTestId('task-assets-panel');
  const card = assetsPanel
    .locator('[class*="rounded"][class*="p-"]')
    .filter({ hasText: filename.slice(0, 20) })
    .first();
  try {
    await expect(card).toBeVisible({ timeout });
  } catch {
    const fallback = assetsPanel
      .locator('.rounded-lg.p-2\\.5')
      .filter({ hasText: filename.slice(0, 20) })
      .first();
    await expect(fallback).toBeVisible({ timeout });
    return fallback;
  }
  return card;
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
 *  optimistic-UI bubble mount (same class as workspace-selection flakes). */
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

test.describe('Session Workspace Isolation E2E', () => {
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

  test('absolute workspace-root write lands at the workspace root', async () => {
    test.setTimeout(LLM_TIMEOUT * 2);
    const marker = `E2E_WSISO_${Date.now()}`;
    const filename = `e2e_wsiso_${Date.now()}.md`;
    const workspaceRoot = resolve(join(miqiHome, 'workspace'));
    const absoluteTarget = join(workspaceRoot, filename);
    const content = `# ${marker}\n\nSession workspace isolation test.`;

    await createNewConversation(page);

    // Path-normalization fix: the model writes an absolute workspace-root
    // path and the file must land at EXACTLY that path — the reported path
    // always equals the requested path.  Retry the send once — deepseek
    // no-op turns (the model replies without calling write_file) are a
    // known flake class.
    const message =
      `必须调用 write_file 工具创建文件，path 参数必须是绝对路径 "${absoluteTarget}"，content="${content}"。` +
      `创建完成后只回复"完成"。`;
    let created = false;
    for (let attempt = 0; attempt < 2 && !created; attempt++) {
      await sendMessageWithRetry(page, message);
      await waitForResponseComplete(page, 240_000);
      created = existsSync(absoluteTarget);
      if (!created) {
        console.log(`[test] ⚠️ write_file not executed (attempt ${attempt + 1}) — retrying send`);
      }
    }

    // The file must land at the workspace root…
    await expect.poll(() => existsSync(absoluteTarget), { timeout: 30_000 }).toBe(true);
    console.log(`[test] ✅ File "${filename}" found at the workspace root`);

    // …and NOT be silently redirected into sessions/<key>/files/.
    expect(
      findFileInSessionDirs(miqiHome, filename),
      `file must not be redirected into sessions/*/files/: ${filename}`
    ).toBeNull();
    console.log('[test] ✅ No session-dir copy was created');

    // The Task Assets panel still shows the file (tracked_files bookkeeping
    // points at the absolute root path).
    await waitForFileInPanel(page, filename);
    console.log('[test] ✅ File appears in Task Assets panel');
  });

  test('a new session does not see the previous session files', async () => {
    test.setTimeout(LLM_TIMEOUT);
    const marker = `E2E_WSISO_B_${Date.now()}`;
    const filename = `e2e_wsiso_b_${Date.now()}.md`;
    const workspaceRoot = resolve(join(miqiHome, 'workspace'));
    const absoluteTarget = join(workspaceRoot, filename);
    const content = `# ${marker}\n\nIsolation check.`;

    await createNewConversation(page);
    const createMessage =
      `必须调用 write_file 工具创建文件，path 参数必须是绝对路径 "${absoluteTarget}"，content="${content}"。` +
      `创建完成后只回复"完成"。`;
    // Same no-op retry loop as the first test (CodeRabbit #731 review).
    let created = false;
    for (let attempt = 0; attempt < 2 && !created; attempt++) {
      await sendMessageWithRetry(page, createMessage);
      await waitForResponseComplete(page, 240_000);
      created = existsSync(absoluteTarget);
      if (!created) {
        console.log(`[test] ⚠️ write_file not executed (attempt ${attempt + 1}) — retrying send`);
      }
    }
    await expect.poll(() => existsSync(absoluteTarget), { timeout: 30_000 }).toBe(true);

    // Switch to a fresh session — its Task Assets panel must start empty
    // (no cross-session leakage of tracked files).
    await createNewConversation(page);
    await expect(page.locator('[data-testid="task-assets-empty"]')).toBeVisible({
      timeout: 15_000,
    });
    console.log('[test] ✅ New session shows empty Task Assets');
  });
});
