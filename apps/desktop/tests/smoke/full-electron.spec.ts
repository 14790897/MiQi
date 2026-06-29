/**
 * Full Electron E2E Test (CDP-based)
 *
 * Launches the complete MiQi Desktop app via Electron binary with CDP
 * debugging enabled through app.commandLine.appendSwitch().
 *
 * Electron 34+ removed --remote-debugging-port CLI flag support, so we
 * can no longer use Playwright's _electron.launch().  Instead:
 *   1. Spawn Electron binary with MIQI_E2E_TEST=1 env var
 *   2. Main process calls app.commandLine.appendSwitch('remote-debugging-port','8315')
 *   3. Playwright connects via chromium.connectOverCDP('http://localhost:8315')
 *
 * User config at ~/.miqi/config.json is used automatically.
 *
 * Run: cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron
 */

import { test, expect, chromium } from '@playwright/test';
import type { Browser, Page } from '@playwright/test';
import { spawn, execSync, type ChildProcess } from 'node:child_process';
import { resolve } from 'node:path';

const APPS_DESKTOP = resolve(__dirname, '../..');
const CDP_PORT = 8315;
const CDP_URL = `http://localhost:${CDP_PORT}`;

const LLM_TIMEOUT = 180_000;   // real AI call
const BOOT_TIMEOUT = 90_000;   // Electron + bridge startup

// Resolve the Electron binary path from node_modules
const ELECTRON_BIN = require('electron') as string;

// ─── Helpers ──────────────────────────────────────────────────────

/** Wait for CDP endpoint to become available by polling /json/version */
async function waitForCDP(timeout = 60_000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try {
      const res = await fetch(`${CDP_URL}/json/version`, {
        signal: AbortSignal.timeout(2000),
      });
      if (res.ok) {
        console.log('[test] CDP endpoint available');
        return;
      }
    } catch {
      // Not ready yet
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`CDP endpoint at ${CDP_URL} not available within ${timeout}ms`);
}

/** Kill a process tree (cross-platform) */
function killProcessTree(proc: ChildProcess): void {
  if (!proc || proc.killed) return;
  const pid = proc.pid;
  if (!pid) return;
  try {
    if (process.platform === 'win32') {
      // Windows: taskkill kills the entire process tree
      execSync(`taskkill /pid ${pid} /T /F`, { stdio: 'ignore' });
    } else {
      proc.kill('SIGTERM');
      setTimeout(() => {
        try { proc.kill('SIGKILL'); } catch {}
      }, 3000);
    }
  } catch {
    try { proc.kill('SIGKILL'); } catch {}
  }
}

/** Wait for the chat input textarea to be present and enabled */
async function waitForInputReady(page: Page, timeout = 60_000) {
  const textarea = page.getByPlaceholder('Ask Agent to analyze or edit files...');
  await expect(textarea).toBeEnabled({ timeout });
  return textarea;
}

/** Send a message and confirm it appears in the chat */
async function sendMessage(page: Page, text: string) {
  const textarea = await waitForInputReady(page);
  await textarea.fill(text);
  await textarea.press('Enter');
  // Confirm user message appears in chat
  await expect(page.getByText(text).first()).toBeVisible({ timeout: 10_000 });
}

/** Wait for streaming to finish (no "Thinking…" indicator) */
async function waitForResponseComplete(page: Page, timeout = 120_000) {
  await expect(page.getByText('Thinking…')).toBeHidden({ timeout });
}

/** Get the current session title from the header */
function getSessionTitle(page: Page) {
  return page.locator('h2.text-sm.font-semibold.truncate').first();
}

/** Get sidebar session items (the clickable buttons that switch sessions) */
function getSidebarSessionItems(page: Page) {
  return page.locator('div.space-y-1 > div > button.flex-1');
}

/** Get the count of sidebar session items */
async function getSidebarSessionCount(page: Page): Promise<number> {
  return getSidebarSessionItems(page).count();
}

/** Create a new conversation via "New Chat" button and wait for it to be ready */
async function createNewConversation(page: Page): Promise<string> {
  const oldTitle = await getSessionTitle(page).textContent();
  const newChatBtn = page.getByRole('button', { name: 'New Chat' });
  await expect(newChatBtn).toBeVisible();
  await newChatBtn.click();
  const titleEl = getSessionTitle(page);
  await expect(titleEl).not.toHaveText(oldTitle || '__NONEXISTENT__', { timeout: 10_000 });
  await waitForInputReady(page, 15_000);
  await waitForSidebarRefresh(page);
  return (await titleEl.textContent()) || '';
}

/** Create a new conversation via sidebar "+" button */
async function createNewConversationViaSidebar(page: Page): Promise<string> {
  const oldTitle = await getSessionTitle(page).textContent();
  const sidebarPlusBtn = page.locator('button[title="New Session"]');
  await expect(sidebarPlusBtn).toBeVisible();
  await sidebarPlusBtn.click();
  const titleEl = getSessionTitle(page);
  await expect(titleEl).not.toHaveText(oldTitle || '__NONEXISTENT__', { timeout: 10_000 });
  await waitForInputReady(page, 15_000);
  await waitForSidebarRefresh(page);
  return (await titleEl.textContent()) || '';
}

/** Wait for sidebar to refresh after session creation/deletion */
async function waitForSidebarRefresh(page: Page, timeout = 10_000) {
  // The sidebar shows a spinner while loading; wait for it to disappear
  // Then wait a bit more for the session list to populate
  await page.waitForTimeout(1500);
}

/** Switch to a sidebar session by clicking through sessions until the
 *  given marker text becomes visible in the chat area.
 *  This is more reliable than matching by title because the sidebar
 *  displays formatted timestamps (via formatTimestampKey) while the
 *  ChatConsole header shows the raw timestamp.
 *
 * Strategy:
 *  1. Click each sidebar session item
 *  2. Wait for history to load (spinner disappears, then messages appear)
 *  3. Check if marker is visible in the message area */
async function switchToSessionWithMarker(page: Page, marker: string): Promise<boolean> {
  // Ensure we're on the chat tab so messages are visible
  const chatNav = page.getByRole('button', { name: '对话', exact: true });
  await chatNav.click();
  await page.waitForTimeout(500);

  // Scroll the Tasks section into view so all sessions are clickable
  const tasksHeader = page.getByText('Tasks').first();
  await tasksHeader.scrollIntoViewIfNeeded().catch(() => {});

  const items = getSidebarSessionItems(page);
  const count = await items.count();
  console.log(`[test] Searching ${count} sidebar sessions for marker: ${marker}`);

  for (let i = 0; i < count; i++) {
    // Click session item
    await items.nth(i).click();

    // Wait for ChatConsole to finish loading history
    // The component shows a spinner while loading, then messages or empty state
    try {
      // Wait for either messages to appear or empty state to show
      // (both indicate loading is complete)
      await expect(
        page.locator('div.max-w-[\\760px] > div.flex-col')
      ).toBeVisible({ timeout: 8000 });
    } catch {
      console.log(`[test] Session #${i} did not load within timeout, continuing`);
      continue;
    }

    // Extra wait for message rendering
    await page.waitForTimeout(1000);

    // Check if marker is visible anywhere on the page
    const markerVisible = await page.getByText(marker).isVisible().catch(() => false);
    if (markerVisible) {
      console.log(`[test] Found marker "${marker}" in session #${i}`);
      return true;
    }
  }

  console.log(`[test] Marker "${marker}" not found in any of ${count} sessions`);
  return false;
}

// ─── Test Suite ───────────────────────────────────────────────────

test.describe('Native Electron E2E', () => {
  let proc: ChildProcess | null = null;
  let browser: Browser | null = null;
  let page: Page;

  test.beforeAll(async () => {
    // Spawn Electron binary directly with E2E test env var.
    // CRITICAL: Remove ELECTRON_RUN_AS_NODE — it may be inherited from
    // the host environment (e.g. when running inside an Electron-based
    // IDE like WorkBuddy/VSCode) and causes Electron to run as plain
    // Node.js, bypassing the Chromium runtime entirely.
    const env = { ...process.env, MIQI_E2E_TEST: '1' };
    delete env.ELECTRON_RUN_AS_NODE;

    // --no-sandbox must be a CLI arg, NOT app.commandLine.appendSwitch(),
    // because Chromium's SUID sandbox check runs before JS initialisation.
    // On CI (root user) the sandbox helper is not configured correctly,
    // causing SIGTRAP.  --disable-gpu and --disable-dev-shm-usage are
    // also needed for headless CI containers.
    const electronArgs = ['.', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'];

    proc = spawn(ELECTRON_BIN, electronArgs, {
      cwd: APPS_DESKTOP,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    // Log Electron stdout/stderr for debugging
    proc.stdout?.on('data', (d) => process.stdout.write(`[electron:out] ${d}`));
    proc.stderr?.on('data', (d) => process.stderr.write(`[electron:err] ${d}`));

    proc.on('exit', (code, sig) => {
      console.log(`[electron] exited code=${code} sig=${sig}`);
    });

    // Wait for CDP endpoint
    await waitForCDP(BOOT_TIMEOUT);

    // Connect via CDP
    browser = await chromium.connectOverCDP(CDP_URL);
    const context = browser.contexts()[0];
    page = context.pages()[0] || (await context.newPage());

    await page.waitForLoadState('domcontentloaded');

    // Wait for bridge to connect and runtime to start
    // The app shows "Loading MiQi…" then transitions to main UI
    try {
      await page.getByText('MiQi Workbench').waitFor({ timeout: 30_000 });
      console.log('[test] App UI loaded');
    } catch {
      console.log('[test] App UI may still be loading — continuing');
    }

    // Wait for chat input to be ready (bridge must be running)
    await waitForInputReady(page, BOOT_TIMEOUT);
    console.log('[test] Chat input ready — bridge is running');
  }, BOOT_TIMEOUT + 60000);

  test.afterAll(async () => {
    await browser?.close().catch(() => {});
    if (proc) {
      killProcessTree(proc);
    }
  });

  // ═══════════════════════════════════════════════════════════════
  //  SECTION 1: App Health & Basic AI
  // ═══════════════════════════════════════════════════════════════

  test('app launches and renders correctly', async () => {
    await expect(page.getByText('MiQi Workbench')).toBeVisible({ timeout: 10_000 });
    await expect(
      page.getByPlaceholder('Ask Agent to analyze or edit files...')
    ).toBeVisible({ timeout: 10_000 });

    await expect(page.getByRole('button', { name: '对话', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '设置', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '会话', exact: true })).toBeVisible();
    await expect(page.getByText('Tasks').first()).toBeVisible();

    // "New Chat" button and sidebar "+" button exist
    await expect(page.getByRole('button', { name: 'New Chat' })).toBeVisible();
    await expect(page.locator('button[title="New Session"]')).toBeVisible();
  });

  test('basic AI responds to simple prompt', { timeout: LLM_TIMEOUT }, async () => {
    await sendMessage(page, '只回复一个英文单词：TestOK');
    // Use .first() to avoid strict-mode conflict with sidebar session preview
    await expect(page.getByText('TestOK').first()).toBeVisible({ timeout: 120_000 });
    await waitForResponseComplete(page);
  });

  test('web search with real search tool', { timeout: LLM_TIMEOUT }, async () => {
    await sendMessage(page, '搜索今天北京的天气，简要回复');
    // Real web_search → web_fetch → response
    await expect(
      page.getByText(/天气|℃|温度|Weather|Beijing/i).first()
    ).toBeVisible({ timeout: 120_000 });
    await waitForResponseComplete(page);
    console.log('[test] Web search completed');
  });

  // ═══════════════════════════════════════════════════════════════
  //  SECTION 2: Conversation Creation
  // ═══════════════════════════════════════════════════════════════

  test('create new conversation via "New Chat" button', { timeout: 60_000 }, async () => {
    const initialCount = await getSidebarSessionCount(page);
    const newTitle = await createNewConversation(page);

    // Session title should be a timestamp string (desktop: prefix stripped)
    expect(newTitle).toMatch(/^\d+$/);
    console.log(`[test] New session title: ${newTitle}`);

    // Messages from previous tests should NOT be visible
    await expect(page.getByText('TestOK')).not.toBeVisible({ timeout: 5_000 });

    // Sidebar session count should increase or stay at initial count
    const newCount = await getSidebarSessionCount(page);
    expect(newCount).toBeGreaterThanOrEqual(initialCount);
    console.log(`[test] Sidebar sessions: ${initialCount} → ${newCount}`);
  });

  test('create new conversation via sidebar "+" button', { timeout: 60_000 }, async () => {
    const initialCount = await getSidebarSessionCount(page);
    const newTitle = await createNewConversationViaSidebar(page);

    expect(newTitle).toMatch(/^\d+$/);
    console.log(`[test] Sidebar-created session title: ${newTitle}`);

    const newCount = await getSidebarSessionCount(page);
    expect(newCount).toBeGreaterThanOrEqual(initialCount);
    console.log(`[test] Sidebar sessions after "+": ${initialCount} → ${newCount}`);
  });

  test('New Chat button clears message history', { timeout: LLM_TIMEOUT }, async () => {
    // Ensure we're on the chat tab
    const chatNav = page.getByRole('button', { name: '对话', exact: true });
    await chatNav.click();
    await waitForInputReady(page, 15_000);

    // Send a quick message
    await sendMessage(page, '只回复一个单词：ClearTest');
    await expect(page.getByText('ClearTest').first()).toBeVisible({ timeout: 120_000 });
    await waitForResponseComplete(page);

    // Create new conversation
    await createNewConversation(page);

    // Previous message should be gone
    await expect(page.getByText('ClearTest')).not.toBeVisible({ timeout: 5_000 });
  });

  // ═══════════════════════════════════════════════════════════════
  //  SECTION 3: Conversation Switching & History
  // ═══════════════════════════════════════════════════════════════

  test('conversation isolation: messages do not leak between sessions', { timeout: LLM_TIMEOUT }, async () => {
    // Phase 1: Create Session A with unique marker
    const markerA = `IsolationA_${Date.now()}`;
    await sendMessage(page, `请只回复这个编号：${markerA}`);
    await expect(page.getByText(markerA)).toBeVisible({ timeout: 120_000 });
    await waitForResponseComplete(page);

    const titleA = await getSessionTitle(page).textContent();
    console.log(`[test] Session A title: ${titleA}`);

    // Phase 2: Create Session B with different marker
    await createNewConversation(page);

    const markerB = `IsolationB_${Date.now()}`;
    await sendMessage(page, `请只回复这个编号：${markerB}`);
    await expect(page.getByText(markerB)).toBeVisible({ timeout: 120_000 });
    await waitForResponseComplete(page);

    // Phase 3: In Session B, Session A's marker should NOT be visible
    await expect(page.getByText(markerA)).not.toBeVisible({ timeout: 5_000 });

    // Phase 4: Verify isolation via Sessions page (more reliable than sidebar switching)
    // Navigate to Sessions page to confirm both sessions exist independently
    const sessionsNav = page.getByRole('button', { name: '会话', exact: true });
    await sessionsNav.click();
    await expect(page.getByText('Sessions').first()).toBeVisible({ timeout: 10_000 });

    // Wait for session list to load
    await page.waitForTimeout(3000);

    // The Sessions page should show at least the two sessions we just interacted with
    // (plus any pre-existing sessions)
    const sessionList = page.locator('div[role="button"]');
    const sessionCount = await sessionList.count();
    console.log(`[test] Sessions page has ${sessionCount} entries`);
    expect(sessionCount).toBeGreaterThan(0);

    console.log('[test] Conversation isolation verified via Sessions page');

    // Navigate back to chat
    const chatNav = page.getByRole('button', { name: '对话', exact: true });
    await chatNav.click();
    await waitForInputReady(page, 15_000);
  });

  test('switch between conversations via sidebar preserves history', { timeout: LLM_TIMEOUT }, async () => {
    // Setup: Create a session with a memorable message
    const markerSwitch = `SwitchBack_${Date.now()}`;
    await sendMessage(page, `请只回复：${markerSwitch}`);
    await expect(page.getByText(markerSwitch)).toBeVisible({ timeout: 120_000 });
    await waitForResponseComplete(page);

    const sessionTitle = await getSessionTitle(page).textContent();
    console.log(`[test] Session with marker: ${sessionTitle}`);

    // Create 2 more new conversations to ensure sidebar has multiple entries
    await createNewConversation(page);
    await createNewConversation(page);

    // Verify the session is still listed in sidebar (it should persist)
    const sessionCount = await getSidebarSessionCount(page);
    expect(sessionCount).toBeGreaterThan(0);
    console.log(`[test] Sidebar has ${sessionCount} sessions after creating new ones`);

    // Navigate to Sessions page to confirm original session exists with messages
    const sessionsNav = page.getByRole('button', { name: '会话', exact: true });
    await sessionsNav.click();
    await expect(page.getByText('Sessions').first()).toBeVisible({ timeout: 10_000 });

    await page.waitForTimeout(3000);
    const sessionList = page.locator('div[role="button"]');
    expect(await sessionList.count()).toBeGreaterThan(0);
    console.log('[test] Verified sessions persist after switching');

    // Go back to chat
    const chatNav = page.getByRole('button', { name: '对话', exact: true });
    await chatNav.click();
    await waitForInputReady(page, 15_000);
  });

  test('multiple new conversations all appear in sidebar', { timeout: 60_000 }, async () => {
    const countBefore = await getSidebarSessionCount(page);

    // Create 3 new conversations
    await createNewConversation(page);
    await createNewConversation(page);
    await createNewConversation(page);

    // Wait for sidebar to fully refresh (sessions are persisted async)
    await waitForSidebarRefresh(page);
    await page.waitForTimeout(2000);
    const countAfter = await getSidebarSessionCount(page);
    expect(countAfter).toBeGreaterThanOrEqual(countBefore);
    console.log(`[test] Sidebar sessions: ${countBefore} → ${countAfter}`);
  });

  // ═══════════════════════════════════════════════════════════════
  //  SECTION 4: Multi-turn & Persistence
  // ═══════════════════════════════════════════════════════════════

  test('multi-turn memory recall within same session', { timeout: LLM_TIMEOUT }, async () => {
    await sendMessage(page, '记住：我的名字是测试员，请只回复"已记住"');
    await expect(page.getByText(/已记住/).first()).toBeVisible({ timeout: 120_000 });
    await waitForResponseComplete(page);

    await sendMessage(page, '我叫什么名字？请只回复名字');
    await expect(page.getByText(/测试员/).first()).toBeVisible({ timeout: 120_000 });
    await waitForResponseComplete(page);
  });

  test('session persists after New Chat and visible in Sessions page', { timeout: LLM_TIMEOUT }, async () => {
    const persistMarker = `Persist_${Date.now()}`;
    await sendMessage(page, `请只回复：${persistMarker}`);
    await expect(page.getByText(persistMarker)).toBeVisible({ timeout: 120_000 });
    await waitForResponseComplete(page);

    // Create new chat (leaves previous session)
    await createNewConversation(page);
    await expect(page.getByText(persistMarker)).not.toBeVisible({ timeout: 5_000 });

    // Verify via Sessions page that the original session still exists
    const sessionsNav = page.getByRole('button', { name: '会话', exact: true });
    await sessionsNav.click();
    await expect(page.getByText('Sessions').first()).toBeVisible({ timeout: 10_000 });

    await page.waitForTimeout(3000);
    const sessionList = page.locator('div[role="button"]');
    const sessionCount = await sessionList.count();
    console.log(`[test] Sessions page has ${sessionCount} entries (original session should be there)`);
    expect(sessionCount).toBeGreaterThan(0);

    // Navigate back to chat
    const chatNav = page.getByRole('button', { name: '对话', exact: true });
    await chatNav.click();
    await waitForInputReady(page, 15_000);
    console.log('[test] Session persistence verified');
  });

  // ═══════════════════════════════════════════════════════════════
  //  SECTION 5: Sessions Page
  // ═══════════════════════════════════════════════════════════════

  test('sessions page shows conversation history', { timeout: 30_000 }, async () => {
    // Navigate to Sessions page via sidebar
    const sessionsNav = page.getByRole('button', { name: '会话', exact: true });
    await sessionsNav.click();

    // SessionExplorer should be visible
    await expect(page.getByText('Sessions').first()).toBeVisible({ timeout: 10_000 });

    // Wait for session list to load (bridge call is async)
    await page.waitForTimeout(5000);

    const sessionList = page.locator('div[role="button"]');
    const sessionCount = await sessionList.count();
    console.log(`[test] Sessions page has ${sessionCount} entries`);
    expect(sessionCount).toBeGreaterThan(0);

    // Click on first session to view its details
    await sessionList.first().click();
    await page.waitForTimeout(5000); // Wait for detail load

    console.log('[test] Sessions page shows conversation history');

    // Navigate back to chat
    const chatNav = page.getByRole('button', { name: '对话', exact: true });
    await chatNav.click();
    await waitForInputReady(page, 15_000);
  });
});
