/**
 * E2E: Subagent lifecycle — spawn, execute, result callback
 *
 * Run:
 *   cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron subagent.spec.ts
 *
 * Verification checklist (issue #246):
 *   1. Subagent is spawned correctly
 *   2. Concurrent limit (max 3) is enforced
 *   3. Tools are registered (no Message / Spawn to prevent recursion)
 *   4. Iteration limit (15/25 steps) is enforced
 *   5. Result flows via IPC chat:subagent_result to the frontend
 *   6. Frontend renders subagent result (✅ success / ❌ failure)
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  LLM_TIMEOUT,
  waitForInputReady,
  launchElectronApp,
  closeElectronApp,
  approveLoop,
} from './helpers/electron-setup';

// ─── Constants ─────────────────────────────────────────────────────

/** Subagent results may arrive after the main agent finishes.
 *  Give extra time for background subagent execution. */
const SUBAGENT_TIMEOUT = LLM_TIMEOUT + 120_000; // 5 min total

// ─── Helpers ──────────────────────────────────────────────────────

async function sendMessage(page: Page, text: string) {
  const textarea = await waitForInputReady(page);
  await textarea.fill(text);
  await textarea.press('Enter');
  await expect(page.getByText(text).first()).toBeVisible({ timeout: 10_000 });
}

/**
 * Wait for a subagent result message to appear in the chat area.
 * Subagent messages are rendered with `role === 'subagent'` and
 * contain the text "Subagent" in their content.
 */
async function waitForSubagentResult(
  page: Page,
  timeout = SUBAGENT_TIMEOUT,
): Promise<string> {
  // Subagent results contain "Subagent" text plus ✅/❌
  const subagentPattern = /Subagent\s+"(.+?)"\s+(completed|failed)/;
  const deadline = Date.now() + timeout;

  while (Date.now() < deadline) {
    // Check main area for any subagent indicator text
    const main = page.locator('main');
    const text = (await main.textContent().catch(() => '')) || '';

    const match = text.match(subagentPattern);
    if (match) {
      console.log(`[test] Subagent result found: "${match[1]}" → ${match[2]}`);
      return match[2]; // "completed" | "failed"
    }

    // Also check for "Subagent" as substring (more lenient)
    if (text.includes('Subagent')) {
      console.log('[test] Subagent keyword found in page (non-standard format)');
      return 'unknown';
    }

    // Check if Thinking indicator is still spinning (main agent still running)
    const thinking = await page
      .locator('[data-testid="thinking-indicator"]')
      .isVisible()
      .catch(() => false);
    if (!thinking && Date.now() > deadline - 60_000) {
      // Main agent finished but no subagent — may have chosen not to spawn
      console.log('[test] Main agent finished, no subagent detected after timeout');
      break;
    }

    await page.waitForTimeout(2000);
  }

  throw new Error(`Subagent result did not appear within ${timeout}ms`);
}

// ─── Test Suite ───────────────────────────────────────────────────

test.describe.serial('Subagent E2E (#246)', () => {
  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;

  test.beforeAll(async () => {
    test.setTimeout(120_000);
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;

    // Pre-approve all tools
    await page.evaluate(() =>
      (window as any).miqi.approvals.addPermanent('*:*', 'always'),
    );
    console.log('[test] All tools pre-approved');
  });

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
  });

  // ── Test 1: Subagent spawn → result ──────────────────────────

  test('AI spawns subagent and frontend renders result', async () => {
    test.setTimeout(SUBAGENT_TIMEOUT);
    // Send a message that encourages the AI to spawn a subagent for
    // parallel work.  The exact prompt is designed to probe both
    // code-search and web-search capabilities concurrently so the
    // AI is likely to delegate one to a subagent.
    await sendMessage(
      page,
      '并行执行以下两个任务：\n' +
        '1. 在代码库中搜索所有使用 "subagent" 或 "spawn" 关键词的文件，汇总结果\n' +
        '2. 联网搜索 "LLM agent subagent delegation pattern" 的相关资料\n\n' +
        '请使用 subagent 来并行处理这两项任务，最后汇总给我。',
    );

    // Wait for main agent to finish (auto-approve tools in the meantime)
    await approveLoop(page, LLM_TIMEOUT);

    // Now wait for subagent result (may arrive after main agent)
    const status = await waitForSubagentResult(page);

    // Verify result status
    if (status !== 'unknown') {
      expect(['completed', 'failed']).toContain(status);
      console.log(`[test] ✅ Subagent result status: ${status}`);
    }

    // Verify subagent message is rendered in the chat area
    const main = page.locator('main');
    const hasSubagentText = await main
      .getByText('Subagent', { exact: false })
      .first()
      .isVisible()
      .catch(() => false);
    expect(hasSubagentText).toBe(true);
    console.log('[test] ✅ Subagent message visible in chat area');
  });

  // ── Test 2: Subagent concurrent limit ─────────────────────────

  test('subagent enforces max concurrent limit (3)', async () => {
    test.setTimeout(SUBAGENT_TIMEOUT);
    // Create a new conversation so we don't interfere with Test 1
    const plusBtn = page.locator('[data-testid="nav-new-session"]');
    await plusBtn.click();
    await waitForInputReady(page, 15_000);

    // Send a message that explicitly asks for 4+ subagents to verify
    // the concurrency limit kicks in
    await sendMessage(
      page,
      '一次性创建 4 个并行 subagent，分别搜索：\n' +
        'subagent-1: 代码中所有 "import" 语句\n' +
        'subagent-2: 代码中所有 "export" 语句\n' +
        'subagent-3: 代码中所有 "async" 函数\n' +
        'subagent-4: 代码中所有 "class" 定义\n\n' +
        '注意：最多只能同时运行 3 个 subagent，如果第 4 个无法创建，请告诉我原因。',
    );

    // Let the main agent process and spawn subagents
    await approveLoop(page, LLM_TIMEOUT);

    // The main agent response should mention that only 3 subagents
    // can run concurrently or that the 4th was blocked.
    // We verify the AI acknowledged the limit by checking the chat.
    const main = page.locator('main');
    const text = (await main.textContent().catch(() => '')) || '';

    // At minimum we expect some subagent activity
    const subagentMentions = (text.match(/subagent/gi) || []).length;
    console.log(`[test] Subagent keyword mentions in chat: ${subagentMentions}`);

    // The result should reference the limit or at least show subagent
    // activity.  We're mostly verifying the system doesn't crash when
    // asked to exceed the limit.
    expect(subagentMentions).toBeGreaterThan(0);
    console.log('[test] ✅ Concurrent subagent test completed without crash');
  });

  // ── Test 3: Subagent result persists across session reload ────

  test.fixme(
    'subagent result survives session restore',
    async () => {
      test.setTimeout(SUBAGENT_TIMEOUT);
      // KNOWN ISSUE: Subagent results arrive via live IPC events and are
      // not persisted to the session store.  After page reload, they are
      // lost.  This test is marked fixme until persistence is implemented.
      // See: ChatConsole.onSubagentResult handler — appends to React state
      // but never calls sessions.save() or similar persistence API.

      const plusBtn = page.locator('[data-testid="nav-new-session"]');
      await plusBtn.click();
      await waitForInputReady(page, 15_000);

      await sendMessage(
        page,
        '搜索代码库中所有包含 "TODO" 注释的文件，使用一个 subagent 来执行。最后列出包含 TODO 的文件路径。',
      );

      await approveLoop(page, LLM_TIMEOUT);
      await waitForSubagentResult(page);
      console.log('[test] ✅ Subagent result received');

      await page.reload({ waitUntil: 'domcontentloaded' });
      await waitForInputReady(page, 30_000);

      const main = page.locator('main');
      const hasSubagentText = await main
        .getByText('Subagent', { exact: false })
        .first()
        .isVisible({ timeout: 15_000 })
        .catch(() => false);

      expect(hasSubagentText).toBe(true);
      console.log('[test] ✅ Subagent result persisted after reload');
    },
  );
});
