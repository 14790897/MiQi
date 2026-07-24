/**
 * Shared Electron E2E setup helpers.
 *
 * All Electron-based E2E specs share the same app-launch lifecycle:
 * clean sessions → launch Electron → wait for bridge → run tests → close.
 * This module extracts that boilerplate so each spec file stays focused.
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import { resolve } from 'node:path';
import { tmpdir, homedir } from 'node:os';
import { join } from 'node:path';
import { existsSync, mkdtempSync, mkdirSync, cpSync, rmSync, readFileSync, writeFileSync } from 'node:fs';

// ─── Constants ──────────────────────────────────────────────────────

/** Absolute path to apps/desktop (Electron entry point) */
export const APPS_DESKTOP = resolve(__dirname, '../../..');

/** Default timeout for real LLM calls */
export const LLM_TIMEOUT = 180_000;

// ─── Session path helpers ────────────────────────────────────────────

/** Derive sessions directory from a MIQI_HOME path */
export function getMiqiSessionsDir(miqiHome: string): string {
  return join(miqiHome, 'workspace', 'sessions');
}

// ─── Page helpers ───────────────────────────────────────────────────

/** Wait for the chat input textarea to be present and enabled */
export async function waitForInputReady(page: Page, timeout = 60_000) {
  const textarea = page.locator('[data-testid="chat-input-container"] textarea');
  await expect(textarea).toBeEnabled({ timeout });
  return textarea;
}

/** Send a message and confirm it appears in the chat */
export async function sendMessage(page: Page, text: string) {
  const textarea = await waitForInputReady(page);
  await textarea.fill(text);
  await textarea.press('Enter');
  // Confirm user message appears in chat
  await expect(page.getByText(text).first()).toBeVisible({ timeout: 10_000 });
}

/** Wait for streaming to finish (no "Thinking…" indicator) */
export async function waitForResponseComplete(page: Page, timeout = 120_000) {
  // Phase 1: model stops generating → "Thinking…" hidden.
  try {
    await expect(page.locator('[data-testid="thinking-indicator"]')).toBeHidden({ timeout });
  } catch (err) {
    // Dump page state before re-throwing — so CI logs show what the AI
    // was doing when it got stuck (tool calls, errors, etc.)
    const mainText = await page.locator('main').textContent();
    const inProgress = await page.locator('.tag-inprogress').count();
    console.log('[diagnostic] waitForResponseComplete TIMEOUT — Thinking… still visible after 120s');
    console.log('[diagnostic] IN PROGRESS tags visible:', inProgress);
    console.log('[diagnostic] main textContent (last 1500 chars):', (mainText || '').slice(-1500));
    throw err;
  }

  // Phase 2: if the AI used tools, "IN PROGRESS" stays visible while
  // the tool runs.  Wait for it to hide (tool result rendered).
  try {
    await expect(page.locator('.tag-inprogress')).toBeHidden({ timeout: 15_000 });
  } catch {
    // Fast responses may never show IN PROGRESS.
  }

  // Phase 3: wait for textContent to have changed AND stabilized.
  // The length must increase at least once (proving streaming happened),
  // then remain stable for two consecutive polls (400ms).  Without the
  // "grown" guard, an AI call that silently fails (empty response) would
  // immediately return true after ~400ms — a false positive.
  await page.waitForFunction(() => {
    const main = document.querySelector('main');
    if (!main) return false;
    const text = main.textContent || '';
    const s = (window as any).__miqi_stream_state;
    if (!s) {
      (window as any).__miqi_stream_state = { base: text.length, stable: 0, grown: false };
      return false;
    }
    if (text.length > s.base) {
      s.base = text.length;
      s.stable = 0;
      s.grown = true;
      return false;
    }
    s.stable++;
    return s.grown && s.stable >= 2;
  }, { timeout: 5000, polling: 200 });
}

/** Poll for approval dialogs and click "永久允许" until the AI stops
 *  thinking.  Used by sandbox and session-isolation tests. */
export async function approveLoop(page: Page, timeout = 180_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const btn = page.getByTestId('approval-allow-permanent');
    if (await btn.isVisible({ timeout: 1000 }).catch(() => false)) {
      await btn.click();
      console.log('[test] Auto-approved tool');
    }
    const thinking = await page.getByTestId('thinking-indicator').isVisible().catch(() => false);
    if (!thinking) break;
    await page.waitForTimeout(1000);
  }
}

// ─── Session / Sidebar helpers ──────────────────────────────────────

/** Get the current session title from the header.
 *  Uses stable class-based selector: both old (text-sm) and new (text-[18px])
 *  UI share font-semibold.truncate on the title h2. */
export function getSessionTitle(page: Page) {
  return page.locator('h2.font-semibold.truncate').first();
}

/** Get sidebar session items (clickable buttons that switch sessions).
 *  Scoped to the sidebar panel to avoid picking up buttons in main content.
 *  New UI: session cards use rounded-xl; filter tabs (rounded-md) and the
 *  "New Session" title button are excluded by the class selector. */
export function getSidebarSessionItems(page: Page) {
  const sidebar = page.locator('div.flex.flex-col.shrink-0.border-r').first();
  return sidebar.locator('button.rounded-xl');
}

/** Get the count of sidebar session items */
export async function getSidebarSessionCount(page: Page): Promise<number> {
  return getSidebarSessionItems(page).count();
}

/** Create a new conversation via sidebar "+" button and wait for it to be ready.
 *  In the redesigned UI there is no "New Chat" header button — sidebar "+" is the canonical way. */
export async function createNewConversation(page: Page): Promise<string> {
  const sidebarPlusBtn = page.locator('[data-testid="nav-new-session"]');
  await expect(sidebarPlusBtn).toBeVisible();
  await sidebarPlusBtn.click();
  // Wait for the new session to load — input becomes enabled when ChatConsole mounts
  await waitForInputReady(page, 15_000);
  await waitForSidebarRefresh(page);
  const titleEl = getSessionTitle(page);
  return (await titleEl.textContent()) || '';
}

/** Wait for sidebar to refresh after session creation/deletion */
export async function waitForSidebarRefresh(page: Page, _timeout = 10_000) {
  await page.waitForTimeout(1500);
}

/** Switch to a sidebar session by clicking through sessions until the
 *  given marker text becomes visible in the main chat area.
 *  No longer depends on a "对话" nav button — the sidebar is always visible. */
export async function switchToSessionWithMarker(
  page: Page,
  marker: string,
): Promise<boolean> {
  // Ensure the Tasks section is scrolled into view
  const tasksHeader = page.locator('[data-testid="nav-tasks-title"]');
  await tasksHeader.scrollIntoViewIfNeeded().catch(() => {});

  const items = getSidebarSessionItems(page);
  const count = await items.count();
  console.log(
    `[test] Searching ${count} sidebar sessions for marker: ${marker}`,
  );

  for (let i = 0; i < count; i++) {
    const btn = items.nth(i);
    await btn.scrollIntoViewIfNeeded().catch(() => {});
    await btn.click({ force: true, timeout: 5000 });
    const currentTitle = await getSessionTitle(page).textContent();
    console.log(`[test] Clicked session #${i} → title: ${currentTitle}`);
    await page.waitForTimeout(4000);

    // Only check the <main> chat area, not the sidebar
    const markerVisible = await page
      .locator('main')
      .getByText(marker, { exact: false })
      .isVisible()
      .catch(() => false);
    if (markerVisible) {
      console.log(`[test] Found marker "${marker}" in session #${i}`);
      return true;
    }
  }

  console.log(
    `[test] Marker "${marker}" not found in any of ${count} sessions`,
  );
  return false;
}

/** Ensure bridge is initialized (s?.initialized === true).
 *  Some tests need to call bridge APIs (e.g. approvals.clearPermanent)
 *  which require the AppServer to be fully registered. */
export async function waitForBridgeInitialized(page: Page, timeoutS = 30) {
  await page.evaluate(async (maxSec) => {
    for (let i = 0; i < maxSec; i++) {
      try {
        const s = await (window as any).miqi.runtime.status();
        if (s?.state === 'running' && s?.initialized) return;
      } catch { /* preload not injected yet */ }
      await new Promise((r) => setTimeout(r, 1000));
    }
  }, timeoutS);
}

/** Poll for sandbox manager to finish initialization.
 *
 *  On first-run (cold CI), the sandbox manager may spend 3-5 minutes
 *  doing wsl export → import → apt-get install.  Tests that use exec
 *  tools should wait here so they don't fire LLM queries into a
 *  half-initialized sandbox (which silently falls back to local exec).
 *
 *  Returns true when sandbox is ready, false on timeout. */
export async function waitForSandboxReady(page: Page, timeoutMs = 300_000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  let lastLog = 0;
  while (Date.now() < deadline) {
    try {
      const status = await page.evaluate(() => (window as any).miqi.runtime.status());
      if (status?.sandbox_available === true) {
        const elapsed = Math.round((timeoutMs - (deadline - Date.now())) / 1000);
        console.log(`[test] Sandbox ready after ${elapsed}s`);
        return true;
      }
      // Log progress every 30s so CI logs show we're not hung
      const elapsed = Math.round((timeoutMs - (deadline - Date.now())) / 1000);
      if (elapsed - lastLog >= 30) {
        console.log(`[test] Waiting for sandbox... ${elapsed}s elapsed (state: ${status?.state}, sandbox_available: ${status?.sandbox_available})`);
        lastLog = elapsed;
      }
    } catch { /* bridge not ready yet */ }
    await page.waitForTimeout(2000);
  }
  console.log('[test] Warning: sandbox not ready within timeout');
  return false;
}

// ─── App lifecycle ──────────────────────────────────────────────────

export interface ElectronFixture {
  electronApp: ElectronApplication;
  page: Page;
  /** Unique temporary MIQI_HOME directory for this test run */
  miqiHome: string;
  /** Derived sessions directory inside miqiHome */
  miqiSessionsDir: string;
}

/** Launch Electron app, wait for bridge ready, return { electronApp, page, miqiHome, miqiSessionsDir }.
 *
 *  - Creates a unique temporary MIQI_HOME so parallel test workers are fully isolated.
 *  - Strips ELECTRON_RUN_AS_NODE (inherited from Electron-based IDEs).
 *  - Waits for MiQi Workbench UI + bridge runtime.status() === 'running'.
 */
export async function launchElectronApp(): Promise<ElectronFixture> {
  // Create unique temporary home per test worker for full isolation.
  // Parallel workers each get their own MIQI_HOME → no race on sessions/.
  const miqiHome = mkdtempSync(join(tmpdir(), 'miqi-e2e-'));
  const miqiSessionsDir = getMiqiSessionsDir(miqiHome);
  console.log(`[test] MIQI_HOME=${miqiHome}`);

  // Copy user's provider config into the temp home so the LLM backend is reachable.
  const userConfigPath = join(homedir(), '.miqi', 'config.json');
  const destConfigPath = join(miqiHome, 'config.json');
  if (existsSync(userConfigPath)) {
    cpSync(userConfigPath, destConfigPath);
  }

  // ── E2E: always enable approval bypass so tests don't hang on dialogs ──
  // This is safer than *:* wildcard pre-approve because it takes effect
  // before the bridge starts — no race with NOT_INITIALIZED or approval popups.
  const config = existsSync(destConfigPath)
    ? JSON.parse(readFileSync(destConfigPath, 'utf-8'))
    : {};
  config.approvals = { ...config.approvals, bypass_all: true };
  // ── E2E: always disable feedback channel so tests don't hit real Feishu ──
  // Each test that needs feedback enabled can opt in by patching the config
  // after launchElectronApp.  Default OFF keeps the disabled-error path
  // verifiable for the E2E suite.
  config.channels = {
    ...config.channels,
    feishu: { ...(config.channels?.feishu ?? {}), enabled: false },
    feedback: { enabled: false, bitableAppToken: '', bitableTableId: '' },
  };
  writeFileSync(destConfigPath, JSON.stringify(config, null, 2));

  // Delete ELECTRON_RUN_AS_NODE inherited from Electron-based IDEs
  // (WorkBuddy / VSCode).  Otherwise Electron runs as plain Node.js.
  const env: Record<string, string | undefined> = { ...process.env };
  env.MIQI_HOME = miqiHome;
  delete env.ELECTRON_RUN_AS_NODE;

  const electronApp = await electron.launch({
    args: [APPS_DESKTOP],
    executablePath: require('electron') as string,
    env: env as Record<string, string>,
    // chromiumSandbox: false covers --no-sandbox + --disable-gpu
    // needed on CI (root user).  No-op on Windows.
    chromiumSandbox: false,
  });

  // Wait for the main window (skip splash window — 480x100, title "MiQi")
  let page;
  for (let i = 0; i < 100; i++) {
    const windows = electronApp.windows();
    for (const w of windows) {
      try {
        const info = await w.evaluate(() => ({ t: document.title, w: window.outerWidth }));
        if (info.w > 500 && info.t === 'MiQi Desktop') { page = w; break; }
      } catch {}
    }
    if (page) break;
    await new Promise(r => setTimeout(r, 100));
  }
  if (!page) page = await electronApp.firstWindow();
  await page.waitForLoadState('domcontentloaded');

  // Capture bridge stderr and app console errors for CI debugging
  page.on('console', (msg) => {
    const t = msg.text();
    if (
      msg.type() === 'error' ||
      t.includes('[MIQI BRIDGE STDERR]') ||
      t.includes('[miqi-bridge]') ||
      t.includes('[Bridge]') ||
      t.includes('[MiQi]') ||
      t.includes('[e2e]')
    ) {
      console.log(`[e2e-console] ${t}`);
    }
  });

  try {
    await page.getByText('MiQi Workbench').waitFor({ timeout: 30_000 });
    console.log('[test] App UI loaded');
  } catch {
    console.log('[test] App UI may still be loading — continuing');
  }

  await waitForInputReady(page);

  // Wait for bridge AppServer to finish registering methods
  const bridgeReady = await page.evaluate(async () => {
    for (let i = 0; i < 60; i++) {
      try {
        const s = await (window as any).miqi.runtime.status();
        if (s?.state === 'running') return true;
      } catch {
        /* preload not injected yet */
      }
      await new Promise((r) => setTimeout(r, 1000));
    }
    return false;
  });
  if (!bridgeReady)
    console.log('[test] Warning: bridge did not reach running state');

  console.log('[test] Ready');
  return { electronApp, page, miqiHome, miqiSessionsDir };
}

/** Close the Electron app and clean up the temporary MIQI_HOME. */
export async function closeElectronApp(app: ElectronApplication, miqiHome?: string) {
  await app?.close().catch(() => {});
  if (miqiHome && existsSync(miqiHome)) {
    rmSync(miqiHome, { recursive: true, force: true });
    console.log(`[test] Cleaned up MIQI_HOME: ${miqiHome}`);
  }
}
