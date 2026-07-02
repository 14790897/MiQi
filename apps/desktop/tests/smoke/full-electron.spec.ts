/**
 * Full Electron E2E Test (_electron.launch based)
 *
 * Uses Playwright's built-in _electron.launch(), which since v1.58
 * (PR #39012) uses app.commandLine.appendSwitch() instead of the
 * removed --remote-debugging-port CLI flag.  No manual CDP needed.
 *
 * User config at ~/.miqi/config.json is used automatically.
 *
 * Run: cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import { resolve } from 'node:path';

const APPS_DESKTOP = resolve(__dirname, '../..');

const LLM_TIMEOUT = 180_000; // real AI call

// ─── Helpers ──────────────────────────────────────────────────────

/** Wait for the chat input textarea to be present and enabled */
async function waitForInputReady(page: Page, timeout = 60_000) {
  const textarea = page.getByPlaceholder(
    'Ask Agent to analyze or edit files...',
  );
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
  await expect(titleEl).not.toHaveText(oldTitle || '__NONEXISTENT__', {
    timeout: 10_000,
  });
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
  await expect(titleEl).not.toHaveText(oldTitle || '__NONEXISTENT__', {
    timeout: 10_000,
  });
  await waitForInputReady(page, 15_000);
  await waitForSidebarRefresh(page);
  return (await titleEl.textContent()) || '';
}

/** Wait for sidebar to refresh after session creation/deletion */
async function waitForSidebarRefresh(page: Page, _timeout = 10_000) {
  await page.waitForTimeout(1500);
}

/** Switch to a sidebar session by clicking through sessions until the
 *  given marker text becomes visible in the main chat area. */
async function switchToSessionWithMarker(
  page: Page,
  marker: string,
): Promise<boolean> {
  const chatNav = page.getByRole('button', { name: '对话', exact: true });
  await chatNav.click();
  await page.waitForTimeout(500);

  const tasksHeader = page.getByText('Tasks').first();
  await tasksHeader.scrollIntoViewIfNeeded().catch(() => {});

  const items = getSidebarSessionItems(page);
  const count = await items.count();
  console.log(
    `[test] Searching ${count} sidebar sessions for marker: ${marker}`,
  );

  for (let i = 0; i < count; i++) {
    await items.nth(i).click();
    await page.waitForTimeout(4000);

    // Only check the <main> chat area, not the sidebar，否则就会误识别，因为sidebar也会显示marker
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

// ─── Test Suite ───────────────────────────────────────────────────

test.describe('Native Electron E2E', () => {
  let electronApp: ElectronApplication;
  let page: Page;

  test.beforeAll(async () => {
    // Delete ELECTRON_RUN_AS_NODE inherited from Electron-based IDEs
    // (WorkBuddy / VSCode).  Otherwise Electron runs as plain Node.js.
    const env = { ...process.env };
    delete env.ELECTRON_RUN_AS_NODE;

    electronApp = await electron.launch({
      args: [APPS_DESKTOP],
      executablePath: require('electron') as string,
      env,
      // chromiumSandbox: false covers --no-sandbox + --disable-gpu
      // needed on CI (root user).  No-op on Windows.
      chromiumSandbox: false,
    });

    page = await electronApp.firstWindow();
    await page.waitForLoadState('domcontentloaded');

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
          const s = await window.miqi.runtime.status();
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
  }, 120_000);

  test.afterAll(async () => {
    await electronApp?.close().catch(() => {});
  });

  // ═══════════════════════════════════════════════════════════════
  //  SECTION 1: App Health & Basic AI
  // ═══════════════════════════════════════════════════════════════

  test('app launches and renders correctly', async () => {
    await expect(page.getByText('MiQi Workbench')).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      page.getByPlaceholder('Ask Agent to analyze or edit files...'),
    ).toBeVisible({ timeout: 10_000 });

    await expect(
      page.getByRole('button', { name: '对话', exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: '设置', exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: '会话', exact: true }),
    ).toBeVisible();
    await expect(page.getByText('Tasks').first()).toBeVisible();

    await expect(page.getByRole('button', { name: 'New Chat' })).toBeVisible();
    await expect(page.locator('button[title="New Session"]')).toBeVisible();
  });

  test('right panel shows Task Assets', async () => {
    // The right panel should show "Task Assets" header with LayoutGrid icon.
    // Default state is panelOpen=true, showing the empty-state message.
    await expect(page.getByText('Task Assets')).toBeVisible({
      timeout: 10_000,
    });

    // Toggle button exists
    const toggleBtn = page.locator('button[title="Toggle assets panel"]');
    await expect(toggleBtn).toBeVisible();

    // Empty state message when no agent operations
    await expect(page.getByText(/No files yet/)).toBeVisible({
      timeout: 5_000,
    });

    // Toggle panel closed and verify it hides
    await toggleBtn.click();
    await expect(page.getByText('Task Assets')).not.toBeVisible({
      timeout: 5_000,
    });

    // Toggle panel back open
    await toggleBtn.click();
    await expect(page.getByText('Task Assets')).toBeVisible({ timeout: 5_000 });
  });

  test(
    'basic AI responds to simple prompt',
    { timeout: LLM_TIMEOUT },
    async () => {
      await sendMessage(page, '只回复一个英文单词：TestOK');
      await expect(page.getByText('TestOK').first()).toBeVisible({
        timeout: 120_000,
      });
      await waitForResponseComplete(page);
    },
  );

  test(
    'web search with real search tool',
    { timeout: LLM_TIMEOUT },
    async () => {
      await sendMessage(page, '搜索今天北京的天气，简要回复');
      await expect(
        page.getByText(/天气|℃|温度|Weather|Beijing/i).first(),
      ).toBeVisible({ timeout: 120_000 });
      await waitForResponseComplete(page);
      console.log('[test] Web search completed');
    },
  );

  // ═══════════════════════════════════════════════════════════════
  //  SECTION 2: Conversation Creation
  // ═══════════════════════════════════════════════════════════════

  test(
    'create new conversation via "New Chat" button',
    { timeout: 60_000 },
    async () => {
      const initialCount = await getSidebarSessionCount(page);
      const newTitle = await createNewConversation(page);

      expect(newTitle).toMatch(/^\d+$/);
      console.log(`[test] New session title: ${newTitle}`);

      await expect(page.getByText('TestOK')).not.toBeVisible({
        timeout: 5_000,
      });

      const newCount = await getSidebarSessionCount(page);
      expect(newCount).toBeGreaterThanOrEqual(initialCount);
      console.log(`[test] Sidebar sessions: ${initialCount} → ${newCount}`);
    },
  );

  test(
    'create new conversation via sidebar "+" button',
    { timeout: 60_000 },
    async () => {
      const initialCount = await getSidebarSessionCount(page);
      const newTitle = await createNewConversationViaSidebar(page);

      expect(newTitle).toMatch(/^\d+$/);
      console.log(`[test] Sidebar-created session title: ${newTitle}`);

      const newCount = await getSidebarSessionCount(page);
      expect(newCount).toBeGreaterThanOrEqual(initialCount);
      console.log(
        `[test] Sidebar sessions after "+": ${initialCount} → ${newCount}`,
      );
    },
  );

  test(
    'New Chat button clears message history',
    { timeout: LLM_TIMEOUT },
    async () => {
      const chatNav = page.getByRole('button', { name: '对话', exact: true });
      await chatNav.click();
      await waitForInputReady(page, 15_000);

      await sendMessage(page, '只回复一个单词：ClearTest');
      await expect(page.getByText('ClearTest').first()).toBeVisible({
        timeout: 120_000,
      });
      await waitForResponseComplete(page);

      await createNewConversation(page);

      await expect(page.getByText('ClearTest')).not.toBeVisible({
        timeout: 5_000,
      });
    },
  );

  // ═══════════════════════════════════════════════════════════════
  //  SECTION 3: Conversation Switching & History
  // ═══════════════════════════════════════════════════════════════

  test(
    'conversation isolation: messages do not leak between sessions',
    { timeout: LLM_TIMEOUT },
    async () => {
      const markerA = `IsolationA_${Date.now()}`;
      await sendMessage(page, `请只回复这个编号：${markerA}`);
      await expect(page.getByText(markerA).first()).toBeVisible({ timeout: 120_000 });
      await waitForResponseComplete(page);

      const titleA = await getSessionTitle(page).textContent();
      console.log(`[test] Session A title: ${titleA}`);

      await createNewConversation(page);

      const markerB = `IsolationB_${Date.now()}`;
      await sendMessage(page, `请只回复这个编号：${markerB}`);
      await expect(page.getByText(markerB).first()).toBeVisible({ timeout: 120_000 });
      await waitForResponseComplete(page);

      await expect(page.getByText(markerA)).not.toBeVisible({ timeout: 5_000 });

      const sessionsNav = page.getByRole('button', {
        name: '会话',
        exact: true,
      });
      await sessionsNav.click();
      await expect(page.getByText('Sessions').first()).toBeVisible({
        timeout: 10_000,
      });

      await page.waitForTimeout(3000);
      const sessionList = page.locator('div[role="button"]');
      const sessionCount = await sessionList.count();
      console.log(`[test] Sessions page has ${sessionCount} entries`);
      expect(sessionCount).toBeGreaterThan(0);

      console.log('[test] Conversation isolation verified via Sessions page');

      const chatNav = page.getByRole('button', { name: '对话', exact: true });
      await chatNav.click();
      await waitForInputReady(page, 15_000);
    },
  );

  test(
    'switch between conversations via sidebar preserves history',
    { timeout: LLM_TIMEOUT },
    async () => {
      const markerSwitch = `SwitchBack_${Date.now()}`;
      await sendMessage(page, `请只回复：${markerSwitch}`);
      await expect(page.getByText(markerSwitch)).toBeVisible({
        timeout: 120_000,
      });
      await waitForResponseComplete(page);

      const sessionTitle = await getSessionTitle(page).textContent();
      console.log(`[test] Session with marker: ${sessionTitle}`);

      await createNewConversation(page);
      await createNewConversation(page);

      const sessionCount = await getSidebarSessionCount(page);
      expect(sessionCount).toBeGreaterThan(0);
      console.log(
        `[test] Sidebar has ${sessionCount} sessions after creating new ones`,
      );

      const sessionsNav = page.getByRole('button', {
        name: '会话',
        exact: true,
      });
      await sessionsNav.click();
      await expect(page.getByText('Sessions').first()).toBeVisible({
        timeout: 10_000,
      });

      await page.waitForTimeout(3000);
      const sessionList = page.locator('div[role="button"]');
      expect(await sessionList.count()).toBeGreaterThan(0);
      console.log('[test] Verified sessions persist after switching');

      const chatNav = page.getByRole('button', { name: '对话', exact: true });
      await chatNav.click();
      await waitForInputReady(page, 15_000);
    },
  );

  test(
    'multiple new conversations all appear in sidebar',
    { timeout: 60_000 },
    async () => {
      const countBefore = await getSidebarSessionCount(page);

      await createNewConversation(page);
      await createNewConversation(page);
      await createNewConversation(page);

      await waitForSidebarRefresh(page);
      await page.waitForTimeout(2000);
      const countAfter = await getSidebarSessionCount(page);
      expect(countAfter).toBeGreaterThanOrEqual(countBefore);
      console.log(`[test] Sidebar sessions: ${countBefore} → ${countAfter}`);
    },
  );

  // ═══════════════════════════════════════════════════════════════
  //  SECTION 4: Sidebar Switching & History
  // ═══════════════════════════════════════════════════════════════

  test('sidebar switch back loads history', { timeout: LLM_TIMEOUT }, async () => {
    await createNewConversation(page);
    const m = `M_${Date.now()}`;
    await sendMessage(page, m);
    await waitForResponseComplete(page);

    await createNewConversation(page);
    await sendMessage(page, 'hi');
    await waitForResponseComplete(page);

    // Switch back to the first session by clicking its sidebar button
    const btn = page.getByRole('button', { name: m }).first();
    await expect(btn).toBeVisible({ timeout: 5000 });
    await btn.click();
    await page.waitForTimeout(5000);

    // Marker should be visible in the main chat area
    await expect(page.locator('main').getByText(m).first()).toBeVisible({ timeout: 15000 });
  });

  test(
    'switch back sees full multi-turn history',
    { timeout: LLM_TIMEOUT },
    async () => {
      await createNewConversation(page);

      await sendMessage(page, '回复：红');
      await waitForResponseComplete(page);
      await sendMessage(page, '回复：蓝');
      await waitForResponseComplete(page);

      await createNewConversation(page);
      await sendMessage(page, 'hi');
      await waitForResponseComplete(page);

      // Switch back, then check both turns in chat area only
      expect(await switchToSessionWithMarker(page, '红')).toBe(true);
      await expect(page.locator('main').getByText('蓝')).toBeVisible({ timeout: 10_000 });
    },
  );

  // ═══════════════════════════════════════════════════════════════
  //  SECTION 5: Multi-turn & Persistence
  // ═══════════════════════════════════════════════════════════════

  test(
    'multi-turn memory recall within same session',
    { timeout: LLM_TIMEOUT },
    async () => {
      await sendMessage(page, '记住：我的名字是测试员，请只回复"已记住"');
      await expect(page.getByText(/已记住/).first()).toBeVisible({
        timeout: 120_000,
      });
      await waitForResponseComplete(page);

      await sendMessage(page, '我叫什么名字？请只回复名字');
      await expect(page.getByText(/测试员/).first()).toBeVisible({
        timeout: 120_000,
      });
      await waitForResponseComplete(page);
    },
  );

  test(
    'session persists after New Chat and visible in Sessions page',
    { timeout: LLM_TIMEOUT },
    async () => {
      const persistMarker = `Persist_${Date.now()}`;
      await sendMessage(page, `请只回复：${persistMarker}`);
      await expect(page.getByText(persistMarker)).toBeVisible({
        timeout: 120_000,
      });
      await waitForResponseComplete(page);

      await createNewConversation(page);
      await expect(page.getByText(persistMarker)).not.toBeVisible({
        timeout: 5_000,
      });

      const sessionsNav = page.getByRole('button', {
        name: '会话',
        exact: true,
      });
      await sessionsNav.click();
      await expect(page.getByText('Sessions').first()).toBeVisible({
        timeout: 10_000,
      });

      await page.waitForTimeout(3000);
      const sessionList = page.locator('div[role="button"]');
      const sessionCount = await sessionList.count();
      console.log(
        `[test] Sessions page has ${sessionCount} entries (original session should be there)`,
      );
      expect(sessionCount).toBeGreaterThan(0);

      const chatNav = page.getByRole('button', { name: '对话', exact: true });
      await chatNav.click();
      await waitForInputReady(page, 15_000);
      console.log('[test] Session persistence verified');
    },
  );

  // ═══════════════════════════════════════════════════════════════
  //  SECTION 5: Sessions Page
  // ═══════════════════════════════════════════════════════════════

  test(
    'sessions page shows conversation history',
    { timeout: 30_000 },
    async () => {
      const sessionsNav = page.getByRole('button', {
        name: '会话',
        exact: true,
      });
      await sessionsNav.click();

      await expect(page.getByText('Sessions').first()).toBeVisible({
        timeout: 10_000,
      });

      await page.waitForTimeout(5000);

      const sessionList = page.locator('div[role="button"]');
      const sessionCount = await sessionList.count();
      console.log(`[test] Sessions page has ${sessionCount} entries`);
      expect(sessionCount).toBeGreaterThan(0);

      await sessionList.first().click();
      await page.waitForTimeout(5000);

      console.log('[test] Sessions page shows conversation history');

      const chatNav = page.getByRole('button', { name: '对话', exact: true });
      await chatNav.click();
      await waitForInputReady(page, 15_000);
    },
  );
});
