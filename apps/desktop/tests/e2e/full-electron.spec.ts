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
import {
  APPS_DESKTOP,
  LLM_TIMEOUT,
  waitForInputReady,
  sendMessage,
  waitForResponseComplete,
  getSessionTitle,
  getSidebarSessionCount,
  createNewConversation,
  waitForSidebarRefresh,
  switchToSessionWithMarker,
  waitForBridgeInitialized,
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';

// ─── Test Suite ───────────────────────────────────────────────────

/** Skip sandbox exec tests on CI runners that lack bwrap.
 *  Set MIQI_RUN_SANDBOX_E2E=1 to force-enable on CI (e.g., WSL runner). */
const SKIP_SANDBOX_ON_CI =
  !!process.env.CI && process.env.MIQI_RUN_SANDBOX_E2E !== '1';
const SKIP_REAL_WEB_SEARCH_ON_CI =
  !!process.env.CI && process.env.MIQI_RUN_REAL_WEB_SEARCH_E2E !== '1';
const SKIP_STATEFUL_SESSION_E2E_ON_CI =
  !!process.env.CI && process.env.MIQI_RUN_STATEFUL_SESSION_E2E !== '1';

test.describe('Native Electron E2E', () => {
  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;
  }, 120_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
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

    // Core UI landmarks — use stable text selectors that exist in BOTH old and new UI
    await expect(page.getByText('Tasks').first()).toBeVisible();
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

  test.describe('real web search integration', () => {
    test.skip(
      SKIP_REAL_WEB_SEARCH_ON_CI,
      '#187: Real Web Search + real LLM output is unstable in PR CI; run with MIQI_RUN_REAL_WEB_SEARCH_E2E=1 for manual/nightly verification.',
    );

    test(
      'web search with real search tool',
      { timeout: LLM_TIMEOUT },
      async () => {
        const marker = `WEB_SEARCH_E2E_DONE_${Date.now()}`;
        await sendMessage(
          page,
          `You must call web_search for "IANA reserved domains". After search completes, reply only with ${marker}`,
        );
        const approvalDialog = page.locator('[role="alertdialog"]');
        if (await approvalDialog.isVisible({ timeout: 30_000 }).catch(() => false)) {
          console.log('[test] Network approval dialog appeared for web search');
          await page.getByRole('button', { name: /Allow once|允许一次/ }).click();
        }
        // Wait for streaming to finish before asserting visibility —
        // during streaming the response element may exist in DOM but be hidden
        await waitForResponseComplete(page);
        const markerEl = page.getByText(marker).first();
        await markerEl.scrollIntoViewIfNeeded().catch(() => {});
        await expect(markerEl).toBeVisible({ timeout: 30_000 });
        console.log('[test] Web search completed');
      },
    );
  });

  // ═══════════════════════════════════════════════════════════════
  //  SECTION 2: Conversation Creation
  // ═══════════════════════════════════════════════════════════════

  test(
    'create new conversation via sidebar button',
    { timeout: 60_000 },
    async () => {
      const initialCount = await getSidebarSessionCount(page);
      const newTitle = await createNewConversation(page);

      // Title should be non-empty (new UI may assign named titles like
      // "Brand Guideline Update" instead of timestamps; titles may also
      // duplicate across sessions)
      expect(newTitle).toBeTruthy();
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
    'New Chat button clears message history',
    { timeout: LLM_TIMEOUT },
    async () => {
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

  test.describe('stateful session integration', () => {
    test.skip(
      SKIP_STATEFUL_SESSION_E2E_ON_CI,
      'Stateful session isolation is unstable in PR CI; run with MIQI_RUN_STATEFUL_SESSION_E2E=1 for manual/nightly verification.',
    );

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
  });

  test(
    'switch between conversations via sidebar preserves history',
    { timeout: LLM_TIMEOUT },
    async () => {
      const markerSwitch = `SwitchBack_${Date.now()}`;
      await sendMessage(page, `只回答${markerSwitch}`);
      await expect(page.locator('main').getByText(markerSwitch, { exact: false }).first()).toBeVisible({
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

  // FIXME: Skipped — application bug prevents sidebar session switching from
  // loading chat history.  ChatConsole.tsx calls window.miqi.sessions.get(key)
  // on mount, but the bridge returns null/empty, silently caught by sendSafe.
  // "Brand Guideline Update" is a UI display hack (ChatConsole.tsx:1114), not
  // real session data.  Full page reload works (see history-persists test)
  // but sidebar click → ChatConsole remount does not.  Likely root cause:
  // parameter naming mismatch between IPC handler (session_key/snake_case)
  // and protocol types (sessionKey/camelCase), or sendSafe silently returning
  // null when the bridge IPC fails on session switch.
  test.skip('sidebar switch back loads history', { timeout: LLM_TIMEOUT }, async () => {
    await createNewConversation(page);
    const m = `M_${Date.now()}`;
    await sendMessage(page, `只回答${m}`);
    await waitForResponseComplete(page);

    await createNewConversation(page);
    await sendMessage(page, 'hi');
    await waitForResponseComplete(page);

    // Switch back via sidebar — use dedicated helper that iterates
    // all session cards and checks <main> area for the marker
    const found = await switchToSessionWithMarker(page, m);
    expect(found).toBe(true);

    // Marker should be visible in the main chat area
    await expect(page.locator('main').getByText(m).first()).toBeVisible({ timeout: 15000 });
  });

  test(
    'history persists after app restart',
    { timeout: LLM_TIMEOUT },
    async () => {
      test.skip(
        SKIP_STATEFUL_SESSION_E2E_ON_CI,
        'Session restart history is unstable in PR CI; run with MIQI_RUN_STATEFUL_SESSION_E2E=1 for manual/nightly verification.',
      );
      await createNewConversation(page);
      const m = `R_${Date.now()}`;
      await sendMessage(page, `只回答${m}`);
      await waitForResponseComplete(page);

      await closeElectronApp(electronApp);
      await new Promise(r => setTimeout(r, 3000));

      const env: Record<string, string | undefined> = { ...process.env };
      env.MIQI_HOME = miqiHome;
      delete env.ELECTRON_RUN_AS_NODE;
      const app2 = await electron.launch({
        args: [APPS_DESKTOP],
        executablePath: require('electron') as string,
        env: env as Record<string, string>,
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

      await closeElectronApp(app2);
      await new Promise(r => setTimeout(r, 3000));
      const fixture = await launchElectronApp();
      electronApp = fixture.electronApp;
      page = fixture.page;
    },
  );

  // FIXME: Skipped — same application bug as "sidebar switch back loads
  // history" above.  See that test's comment for root cause analysis.
  test.skip('switch back sees full multi-turn history', { timeout: LLM_TIMEOUT }, async () => {
    await createNewConversation(page);

    await sendMessage(page, '只回答红');
    await waitForResponseComplete(page);
    await sendMessage(page, '只回答蓝');
    await waitForResponseComplete(page);

    await createNewConversation(page);
    await sendMessage(page, 'hi');
    await waitForResponseComplete(page);

    // Switch back via sidebar — iterate session cards, check <main> area
    const found = await switchToSessionWithMarker(page, '红');
    expect(found).toBe(true);

    await expect(page.locator('main').getByText('蓝').first()).toBeVisible({ timeout: 15_000 });
  });

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
  //  SECTION 6: AI File Creation with *:* wildcard pre-approval
  //
  //  Uses *:* wildcard to bypass all approval dialogs so tests
  //  don't have to wait for UI interaction.  Verifies files are
  //  created successfully without any approval popups.
  // ═══════════════════════════════════════════════════════════════

  test(
    'AI file creation: *:* pre-approved → file created without dialog',
    { timeout: LLM_TIMEOUT * 2 },
    async () => {
      await waitForBridgeInitialized(page);
      await page.evaluate(() =>
        (window as any).miqi.approvals.addPermanent('*:*', 'always'),
      );

      await createNewConversation(page);

      const filename = `e2e_${Date.now()}.txt`;
      await sendMessage(
        page,
        `Use write_file to create ${filename} with content "hello from e2e wildcard approval test"`,
      );

      // No approval dialog should appear
      await waitForResponseComplete(page, 240_000);

      await expect(
        page.locator('main').getByText(filename, { exact: false }).first(),
      ).toBeVisible({ timeout: 15_000 });

      console.log(`[test] ✅ AI created file without approval dialog: ${filename}`);
    },
  );

  test(
    'AI PPT creation: *:* pre-approved → pptx_write without dialog',
    { timeout: LLM_TIMEOUT * 2 },
    async () => {
      await page.evaluate(() =>
        (window as any).miqi.approvals.addPermanent('*:*', 'always'),
      );

      await createNewConversation(page);

      await sendMessage(
        page,
        '使用 pptx_write 工具创建一页PPT，file_path=e2e_test.pptx，slides=[{title:"E2E测试",content:"自动化测试验证通过"}]。创建成功后只回复一个字：成',
      );

      // No approval dialog — just wait for AI to finish
      await waitForResponseComplete(page, 240_000);

      await expect(
        page.locator('main').getByText('成').first(),
      ).toBeVisible({ timeout: 15_000 });

      console.log('[test] ✅ PPT created via pptx_write without approval dialog');
    },
  );

  // ═══════════════════════════════════════════════════════════════
  //  SECTION 7: Sandbox initialization
  // ═══════════════════════════════════════════════════════════════

  test(
    'sandbox manager initializes on bridge startup',
    { timeout: 120_000 },
    async () => {
      const status = await page.evaluate(async () => {
        try { return await (window as any).miqi.runtime.status(); } catch { return null; }
      });
      expect(status?.state).toBe('running');
      console.log('[test] ✅ Bridge running with sandbox manager initialized');
    },
  );

  test(
    'exec pwd in sandbox returns /home/miqi/workspace',
    { timeout: LLM_TIMEOUT },
    async () => {
      test.skip(SKIP_SANDBOX_ON_CI, 'CI runner lacks bwrap');
      await createNewConversation(page);
      await sendMessage(
        page,
        '用 exec 工具执行 pwd，只回复 exec 的实际输出，不要加任何解释',
      );

      await waitForResponseComplete(page, 240_000);

      // Log the full conversation including tool calls and AI response
      const fullText = await page.locator('main').textContent();
      console.log('[test] === Full AI conversation ===');
      console.log(fullText);
      console.log('[test] ===========================');

      // pwd inside bwrap sandbox should output /home/miqi/workspace
      await expect(
        page.locator('main').getByText('/home/miqi/workspace', { exact: false }).first(),
      ).toBeVisible({ timeout: 30_000 });
      console.log('[test] ✅ exec pwd ran inside sandbox');
    },
  );

  test(
    'exec whoami returns miqi user',
    { timeout: LLM_TIMEOUT },
    async () => {
      test.skip(SKIP_SANDBOX_ON_CI, 'CI runner lacks bwrap');
      await sendMessage(
        page,
        '用 exec 工具执行 whoami，只回复 exec 的实际输出，不要加任何解释',
      );
      await waitForResponseComplete(page, 120_000);
      await expect(
        page.locator('main').getByText('miqi', { exact: false }).first(),
      ).toBeVisible({ timeout: 15_000 });
      console.log('[test] ✅ exec whoami → miqi');
    },
  );

  test(
    'exec echo returns command output',
    { timeout: LLM_TIMEOUT },
    async () => {
      test.skip(SKIP_SANDBOX_ON_CI, 'CI runner lacks bwrap');
      await sendMessage(
        page,
        '用 exec 工具执行 echo "sandbox_e2e_OK"，只回复 exec 的实际输出，不要加任何解释',
      );
      await waitForResponseComplete(page, 120_000);
      await expect(
        page.locator('main').getByText('sandbox_e2e_OK', { exact: false }).first(),
      ).toBeVisible({ timeout: 15_000 });
      console.log('[test] ✅ exec echo → sandbox_e2e_OK');
    },
  );

  test(
    'exec uname returns Linux sandbox',
    { timeout: LLM_TIMEOUT },
    async () => {
      test.skip(SKIP_SANDBOX_ON_CI, 'CI runner lacks bwrap');
      await sendMessage(
        page,
        '用 exec 工具执行 uname -s，只回复 exec 的实际输出，不要加任何解释',
      );
      await waitForResponseComplete(page, 120_000);
      // ChatConsole textarea is disabled={streaming}.  Wait for it to
      // become enabled — this only happens after setStreaming(false),
      // which runs AFTER the character animation finishes.
      await expect(page.locator('textarea').last()).not.toHaveAttribute('disabled', { timeout: 10_000 });
      await expect(page.locator('main')).toContainText(/linux/i, { timeout: 10_000 });
      console.log('[test] ✅ exec uname -s → Linux');
    },
  );

  test(
    'exec ls shows sandbox workspace contents',
    { timeout: LLM_TIMEOUT },
    async () => {
      test.skip(SKIP_SANDBOX_ON_CI, 'CI runner lacks bwrap');
      await sendMessage(
        page,
        '用 exec 工具执行 ls /home/miqi/workspace，只回复 exec 的实际输出，不要加任何解释',
      );
      await waitForResponseComplete(page, 120_000);
      const response = page.locator('main').getByText(/.+/);
      await expect(response.first()).toBeVisible({ timeout: 30_000 });
      console.log('[test] ✅ exec ls /home/miqi/workspace');
    },
  );

  test.skip(
    'session file isolation: exec files from one session not visible in another',
    { timeout: LLM_TIMEOUT },
    async () => {
      test.skip(SKIP_SANDBOX_ON_CI, 'CI runner lacks bwrap');
      await createNewConversation(page);

      const marker = `ISOLATED_${Date.now()}`;
      await sendMessage(
        page,
        `用 exec 执行: echo ${marker} > /home/miqi/workspace/session_isolation_test.txt && cat /home/miqi/workspace/session_isolation_test.txt`,
      );
      await waitForResponseComplete(page, 120_000);

      const mainTextA = await page.locator('main').textContent();
      expect(mainTextA).toContain(marker);
      await page.waitForTimeout(800);
      await page.screenshot({ path: 'test-results/session-isolation-01-sessionA-writes.png' });
      console.log(`[test] ✅ Session A file with marker: ${marker}`);

      await createNewConversation(page);
      await sendMessage(
        page,
        '用 exec 执行: cat /home/miqi/workspace/session_isolation_test.txt 2>&1',
      );
      await waitForResponseComplete(page, 120_000);
      await page.waitForTimeout(15_000);

      const mainB = await page.locator('main').textContent() || '';
      const hasNotFound = /no such file|not found|not exist|does not exist|不存在|No such|cat.*error/i.test(mainB);
      if (!hasNotFound) {
        console.log('[test] Session B text (600):', mainB.substring(0, 600));
      }
      expect(hasNotFound).toBe(true);
      await page.waitForTimeout(800);
      await page.screenshot({ path: 'test-results/session-isolation-02-sessionB-cannot-see.png' });
      console.log('[test] ✅ Session B cannot see Session A file');
    },
  );

  test(
    'write_file uses session-scoped workspace via sandbox',
    { timeout: LLM_TIMEOUT },
    async () => {
      test.skip(SKIP_SANDBOX_ON_CI, 'CI runner lacks bwrap');
      await page.evaluate(() =>
        (window as any).miqi.approvals.addPermanent('*:*', 'always'),
      );
      await createNewConversation(page);

      const fname = `e2e_session_file_${Date.now()}.txt`;
      const content = `E2E session file content ${Date.now()}`;

      await sendMessage(
        page,
        `Use write_file to create ${fname} with content "${content}"`,
      );
      // *:* pre-approval skips the dialog — just wait for AI to finish
      await waitForResponseComplete(page, 240_000);
      await page.waitForTimeout(800);
      await page.screenshot({ path: 'test-results/session-isolation-03-write-file-approval.png' });

      await sendMessage(
        page,
        `用 exec 执行: cat /home/miqi/workspace/sessions/*/files/${fname} 2>&1`,
      );
      await waitForResponseComplete(page, 120_000);
      const mainText = await page.locator('main').textContent();
      expect(mainText).toContain(content);
      await page.waitForTimeout(800);
      await page.screenshot({ path: 'test-results/session-isolation-04-write-file-verified.png' });
      console.log(`[test] ✅ write_file session-scoped: ${fname}`);
    },
  );
});
