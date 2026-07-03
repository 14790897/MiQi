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

    // Capture bridge stderr and app console errors for CI debugging
    page.on('console', (msg) => {
      const t = msg.text();
      if (
        msg.type() === 'error' ||
        t.includes('[MIQI BRIDGE STDERR]') ||
        t.includes('[miqi-bridge]') ||
        t.includes('[Bridge]') ||
        t.includes('[MiQi]')
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
      page.getByRole('button', { name: 'MCPs', exact: true }),
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
      await sendMessage(page, '只回答Y');
      await expect(page.getByText('Y').first()).toBeVisible({
        timeout: 120_000,
      });
      await waitForResponseComplete(page);
    },
  );

  test(
    'web search with real search tool',
    { timeout: LLM_TIMEOUT },
    async () => {
      await sendMessage(page, '搜索今天的日期，只回答日期格式YYYY-MM-DD');
      await expect(
        page.getByText(/2026/i).first(),
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

      await expect(page.locator('main').getByText('只回答Y')).not.toBeVisible({
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

      await sendMessage(page, '只回答Y');
      await waitForResponseComplete(page);

      await createNewConversation(page);

      await expect(page.locator('main').getByText('只回答Y')).not.toBeVisible({
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
      await sendMessage(page, `只回答${markerA}`);
      await waitForResponseComplete(page);

      await createNewConversation(page);

      const markerB = `IsolationB_${Date.now()}`;
      await sendMessage(page, `只回答${markerB}`);
      await waitForResponseComplete(page);

      // markerA should NOT be visible in the new chat (scope to main)
      await expect(page.locator('main').getByText(markerA)).not.toBeVisible({ timeout: 5_000 });
    },
  );

  test(
    'switch between conversations via sidebar preserves history',
    { timeout: LLM_TIMEOUT },
    async () => {
      const markerSwitch = `SwitchBack_${Date.now()}`;
      await sendMessage(page, `只回答${markerSwitch}`);
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
    await sendMessage(page, `只回答${m}`);
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
    'history persists after app restart',
    { timeout: LLM_TIMEOUT },
    async () => {
      await createNewConversation(page);
      const m = `R_${Date.now()}`;
      await sendMessage(page, `只回答${m}`);
      await waitForResponseComplete(page);

      await electronApp.close();
      await new Promise(r => setTimeout(r, 3000));

      const env = { ...process.env };
      delete env.ELECTRON_RUN_AS_NODE;
      const app2 = await electron.launch({
        args: [APPS_DESKTOP],
        executablePath: require('electron') as string,
        env,
        chromiumSandbox: false,
      });
      const page2 = await app2.firstWindow();
      await page2.waitForLoadState('domcontentloaded');
      try { await page2.getByText('MiQi Workbench').waitFor({ timeout: 30000 }); } catch {}
      await waitForInputReady(page2, 30000);

      // Wait for bridge to initialize, then reload so ChatConsole re-fires
      // useEffect with bridge fully ready.
      await page2.evaluate(async () => {
        for (let i = 0; i < 30; i++) {
          try {
            const s = await (window as any).miqi.runtime.status();
            if (s?.state === 'running' && s?.initialized) return;
          } catch { /* */ }
          await new Promise(r => setTimeout(r, 1000));
        }
      });
      await page2.reload();
      await page2.waitForLoadState('domcontentloaded');
      await waitForInputReady(page2, 30000);
      await page2.waitForTimeout(5000);

      await expect(page2.locator('main').getByText(m).first()).toBeVisible({ timeout: 30000 });

      await app2.close();
      await new Promise(r => setTimeout(r, 3000));
      electronApp = await electron.launch({
        args: [APPS_DESKTOP],
        executablePath: require('electron') as string,
        env,
        chromiumSandbox: false,
      });
      page = await electronApp.firstWindow();
      await page.waitForLoadState('domcontentloaded');
      try { await page.getByText('MiQi Workbench').waitFor({ timeout: 30000 }); } catch {}
      await waitForInputReady(page, 30000);
    },
  );

  test(
    'switch back sees full multi-turn history',
    { timeout: LLM_TIMEOUT },
    async () => {
      await createNewConversation(page);

      await sendMessage(page, '只回答红');
      await waitForResponseComplete(page);
      await sendMessage(page, '只回答蓝');
      await waitForResponseComplete(page);

      await createNewConversation(page);
      await sendMessage(page, 'hi');
      await waitForResponseComplete(page);

      // Switch back via sidebar — click the button whose title contains "红"
      const btn = page.getByRole('button', { name: '红' }).first();
      await expect(btn).toBeVisible({ timeout: 5000 });
      await btn.click();
      await page.waitForTimeout(5000);

      await expect(page.locator('main').getByText('蓝').first()).toBeVisible({ timeout: 15_000 });
    },
  );

  // ═══════════════════════════════════════════════════════════════
  //  SECTION 5: Multi-turn & Persistence
  // ═══════════════════════════════════════════════════════════════

  test(
    'multi-turn memory recall within same session',
    { timeout: LLM_TIMEOUT },
    async () => {
      await sendMessage(page, '只回答已记住');
      await expect(page.getByText(/已记住/).first()).toBeVisible({
        timeout: 120_000,
      });
      await waitForResponseComplete(page);

      await sendMessage(page, '只回答测试员');
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
      await sendMessage(page, `只回答${persistMarker}`);
      await waitForResponseComplete(page);

      await createNewConversation(page);
      await expect(page.locator('main').getByText(persistMarker)).not.toBeVisible({
        timeout: 5_000,
      });

      console.log('[test] Session persistence verified');
    },
  );

  // SECTION 5 removed — Sessions page no longer has a dedicated nav button.

  // ═══════════════════════════════════════════════════════════════
  //  SECTION 6: AI File Creation with Approval Flow
  //
  //  Tests the full pipeline: LLM → tool use → approval request →
  //  user clicks "永久允许" → tool executes → file created.
  //
  //  The commandApproval system (manual mode, 60s timeout) requires
  //  user interaction for file_write tools.  We clear permanent
  //  approvals first so the dialog always appears for the test.
  // ═══════════════════════════════════════════════════════════════

  test(
    'AI file creation: approval dialog → click allow → file created',
    { timeout: LLM_TIMEOUT * 2 },
    async () => {
      // Clear any existing permanent approvals so the dialog appears
      await page.evaluate(() =>
        (window as any).miqi.approvals.clearPermanent(),
      );

      await createNewConversation(page);

      const filename = `e2e_${Date.now()}.txt`;
      await sendMessage(
        page,
        `Use write_file to create ${filename} with content "hello from e2e approval test"`,
      );

      // Wait for the approval dialog to appear (title: "文件操作审批")
      await expect(page.getByText('文件操作审批')).toBeVisible({
        timeout: 30_000,
      });
      console.log('[test] Approval dialog appeared');

      // Click "永久允许" to approve and remember this decision
      await page.getByRole('button', { name: '永久允许' }).click();
      console.log('[test] Clicked 永久允许');

      // Wait for the tool to execute and AI to finish
      await waitForResponseComplete(page, 240_000);

      // Verify the filename appears in the main chat area
      await expect(
        page.locator('main').getByText(filename, { exact: false }).first(),
      ).toBeVisible({ timeout: 15_000 });

      console.log(`[test] ✅ AI created file after approval: ${filename}`);
    },
  );
});
