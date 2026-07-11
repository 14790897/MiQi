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
import { existsSync, mkdtempSync, mkdirSync, cpSync, rmSync } from 'node:fs';

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
  const textarea = page.getByPlaceholder(
    'Ask Agent to analyze or edit files...',
  );
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
  // "Thinking…" disappears when the AI model finishes generating.
  await expect(page.getByText('Thinking…')).toBeHidden({ timeout });
  // "IN PROGRESS" disappears when streaming animation finishes and
  // ChatConsole calls setStreaming(false).  Without this, textContent
  // reads can be stale on slow CI (e.g. WSL runner).
  await expect(page.getByText('IN PROGRESS')).toBeHidden({ timeout: 15_000 });
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
  const sidebarPlusBtn = page.locator('button[title="New Session"]');
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
  const tasksHeader = page.getByText('Tasks').first();
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
  if (existsSync(userConfigPath)) {
    cpSync(userConfigPath, join(miqiHome, 'config.json'));
  }

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

  const page = await electronApp.firstWindow();
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
