/**
 * Issue #378 regression test — "切回原会话后只显示已发送的问题，不显示正在生成或已经生成的回复"
 *
 * Bug summary (zh):
 *   用户在会话 A 中发送了一个需要持续生成较长回复的问题，
 *   在回复仍处于生成状态时切换到会话 B，
 *   然后切回会话 A：只看到之前发送的问题，助手的气泡/内容全部不可见；
 *   即使回复在桥端已经完成，仍然不会自动出现；
 *   必须手动刷新（F5）后才能看到完整回复。
 *
 * Root cause (ChatConsole.tsx, see fix layer notes in SKILL / repo):
 *   1. ChatConsole.tsx ~L748-760 (useEffect [sessionKey,...]) runs
 *        cleanupListeners();            // L752  ← kills the in-flight onProgress/onFinal/onError/onAborted subscription
 *        setMessages([]);               // L756  ← wipes the per-session messages state
 *        load() → sessions.get(B);      // L763  ← relocates state to B's persistent history
 *      The accumulated stream text lives only in the closure of handleSend,
 *      which is destroyed by cleanupListeners() — by design.
 *   2. ChatConsole.tsx L1073 / L1155 / L1238 / L1254 silently bail when the
 *      event carries data.session_key !== currentSessionRef.current.
 *      Without a per-session message buffer in the renderer the missing
 *      events are gone forever.
 *   3. Switching back to A re-runs the same useEffect, calls setMessages([])
 *      AGAIN, and replaces state with sessions.get(A) — which on the Python
 *      side has only the [user] prompt persisted (the assistant reply was
 *      still in flight).  Result: the user only sees the question, no assistant.
 *   4. Even if the bridge persists the final reply while the user is on B,
 *      no listener is attached on the renderer so the new state is never
 *      surfaced until the user refreshes (which re-mounts ChatConsole and
 *      re-runs the load effect).
 *
 * Fix expectation (renderer-only, Layer 1+2 from the analysis):
 *   - Keep per-session message buffers keyed by session_key (no silent drop).
 *   - Streaming handlers always update the buffer for the event's session_key,
 *     never the current session.
 *   - On sessionKey change, keep the subscriptions alive and switch the
 *     "rendered" pointer, merging persisted + in-memory as needed.
 *
 * Acceptance criteria for THIS test:
 *   PART A  Mid-stream + cross-session:
 *           while A is still streaming, switch A → B → A and assert
 *           that the assistant bubble remains visible WITHOUT a page reload.
 *   PART B  After-stream + cross-session:
 *           fire chat.final() for A while on B, then switch back and assert
 *           the final text is visible WITHOUT a manual refresh.
 *
 * Run:
 *   cd apps/desktop && npx playwright test \
 *     --config=playwright.config.ts --project=smoke \
 *     -g "Issue #378"
 */

import { test, expect, type Page } from '@playwright/test';
import { buildMockBridgeScript } from './mocks';

const SESSION_A = 'desktop:issue378-A';
const SESSION_B = 'desktop:issue378-B';

const QUESTION_A = 'ISSUE_378_Q: write me a long essay about recursion';
const QUESTION_B = 'ISSUE_378_Q_B: write me a long essay about cats';

const PARTIAL_A_1 = 'Cats are curious creatures';
const PARTIAL_A_2 = ' who often nap in sunbeams';
const FULL_A = 'Cats are curious creatures who often nap in sunbeams. The end.';

/**
 * Inject the mock bridge, force the loaded session via localStorage, then
 * navigate to the root. Waits for ChatConsole to mount + chat input to be ready.
 */
async function bootApp(
  page: Page,
  opts: {
    sessions: Array<{ key: string; title: string; updated_at: number; message_count: number }>;
    sessionMessages: Record<string, unknown[]>;
    initialSession: string;
  },
): Promise<void> {
  // Force the app to boot onto the chosen session deterministically.
  await page.addInitScript({
    content: `try { localStorage.setItem('miqi:lastSession', '${opts.initialSession}'); } catch {}`,
  });
  await page.addInitScript({
    content: buildMockBridgeScript({
      // One configured provider so ChatConsole.handleSend does not bail out with
      // "尚未配置模型服务" before reaching chat.send.
      providers: [{ configured: true }],
      sessions: opts.sessions,
      sessionMessages: opts.sessionMessages,
    }),
  });
  await page.goto('/');
  await page.waitForSelector('#root', { state: 'visible' });
  const textarea = page.locator('[data-testid="chat-input-container"] textarea');
  await expect(textarea).toBeEnabled({ timeout: 10_000 });
}

/**
 * Type into the chat input using `type()` (NOT fill) so React's onChange
 * fires — the e2e-test-workflow SKILL is explicit about this for Electron
 * textareas, and the same rule applies here.
 */
async function sendViaUi(page: Page, text: string): Promise<void> {
  const ta = page.locator('[data-testid="chat-input-container"] textarea');
  await ta.click();
  await ta.fill('');
  await ta.type(text);
  await ta.press('Enter');
  await expect(page.getByText(text).first()).toBeVisible({ timeout: 5_000 });
}

/**
 * Fire a chat progress event via the mock bridge, with the explicit
 * session_key the renderer uses for filtering.
 */
async function fireProgress(page: Page, sessionKey: string, text: string): Promise<void> {
  await page.evaluate(
    ({ sk, t }) => {
      (window as any).__miqiMock.progress({
        session_key: sk,
        text: t,
        delta: t,
        tool_hint: false,
      });
    },
    { sk: sessionKey, t: text },
  );
}

/**
 * Fire a chat final event via the mock bridge.
 */
async function fireFinal(page: Page, sessionKey: string, content: string): Promise<void> {
  await page.evaluate(
    ({ sk, c }) => {
      // Use the raw _fire path so we preserve the EXACT content (no fallback).
      (window as any).__miqiMock._fireFinalWithSession?.(sk, c);
      // Fallback if the helper isn't installed (older mocks):
      if (!(window as any).__miqiMock._fireFinalWithSession) {
        (window as any).__miqiMock.rawFinal?.(c);
      }
    },
    { sk: sessionKey, c: content },
  );
}

/**
 * Click a sidebar session item by its title text.  Uses accessible
 * button role + name since session items render as <button> elements
 * whose accessible name is the visible title.
 */
async function clickSidebarSession(page: Page, title: string): Promise<void> {
  const btn = page
    .locator('aside button, nav button, [class*="Sidebar"] button')
    .filter({ hasText: title })
    .first();
  // Fallback: search the whole document for buttons containing the title.
  const fallback = page.getByRole('button', { name: title }).first();
  const target = (await btn.count()) > 0 ? btn : fallback;
  await expect(target).toBeVisible({ timeout: 5_000 });
  await target.click();
}

test.describe('Issue #378 — cross-session streaming must preserve assistant content', () => {
  test(
    'PART A — switching sessions mid-stream keeps the in-progress reply after returning to A (no refresh)',
    async ({ page }) => {
      await bootApp(page, {
        sessions: [
          { key: SESSION_A, title: 'Issue 378 Session A', updated_at: Date.now(), message_count: 1 },
          { key: SESSION_B, title: 'Issue 378 Session B', updated_at: Date.now(), message_count: 1 },
        ],
        // Only the user prompt is persisted for A — this matches the
        // production state while the assistant reply is still streaming
        // (Python hasn't flushed the final yet).
        sessionMessages: {
          [SESSION_A]: [{ role: 'user', content: QUESTION_A }],
          [SESSION_B]: [{ role: 'user', content: QUESTION_B }],
        },
        initialSession: SESSION_A,
      });

      // 1) Send on A.
      await sendViaUi(page, QUESTION_A);

      // 2) Stream the first chunk for A.  The assistant bubble is created
      //    lazily on the first chunk — issue #109 fix guarantees it never
      //    flashes empty before content arrives.
      await fireProgress(page, SESSION_A, PARTIAL_A_1);
      await expect(page.getByText(PARTIAL_A_1, { exact: false }).first()).toBeVisible({
        timeout: 5_000,
      });

      // 3) Switch to B via the sidebar.  This triggers the buggy effect that
      //    tears down listeners + clears messages.
      await clickSidebarSession(page, 'Issue 378 Session B');

      // 4) While on B, more progress arrives for A.  In production this is
      //    the bridge pushing new tokens to the off-screen session.  In the
      //    buggy build the listener is already gone, so these events are
      //    lost.
      await fireProgress(page, SESSION_A, PARTIAL_A_2);

      // 5) Switch back to A.  BUG: only [user] visible.
      await clickSidebarSession(page, 'Issue 378 Session A');

      // Settle — synchronous reveal runs in a burst.
      await page.waitForTimeout(150);

      // Acceptance: the assistant content must still be visible (or any
      // further chunk that was typed after switch).  We assert two
      // independent, observable properties:
      const bubble = page.locator('body').getByText(/Cats are curious creatures/).first();
      await expect(bubble, 'assistant partial content must be visible after returning to A').toBeVisible({
        timeout: 5_000,
      });

      // 6) Sanity: while a stream is alive, the user prompt must remain
      //    visible too (i.e. messages haven't been wiped).
      await expect(page.getByText(QUESTION_A).first()).toBeVisible();
    },
  );

  test(
    'PART B — finalised reply stays visible after switching away and back (no refresh)',
    async ({ page }) => {
      await bootApp(page, {
        sessions: [
          { key: SESSION_A, title: 'Issue 378 Session A', updated_at: Date.now(), message_count: 1 },
          { key: SESSION_B, title: 'Issue 378 Session B', updated_at: Date.now(), message_count: 1 },
        ],
        // Pre-populate A with an empty persisted history (no assistant
        // message persisted yet) to mimic "stream just completed but the
        // renderer hasn't observed the final".
        sessionMessages: {
          [SESSION_A]: [{ role: 'user', content: QUESTION_A }],
          [SESSION_B]: [{ role: 'user', content: QUESTION_B }],
        },
        initialSession: SESSION_A,
      });

      await sendViaUi(page, QUESTION_A);

      // Stream chunk arrives (we replace the entire bubble lazily on the
      // first delta, then accumulate).
      await fireProgress(page, SESSION_A, FULL_A);

      // Before any switch: the full reply should be visible.
      await expect(page.getByText(FULL_A, { exact: false }).first()).toBeVisible({
        timeout: 5_000,
      });

      // Switch to B while the stream is still considered "complete" from
      // the user's standpoint.
      await clickSidebarSession(page, 'Issue 378 Session B');

      // Fire the final event while off-screen — the renderer MUST capture
      // it and persist it for A so the user sees it on switch-back.
      await page.evaluate(() => {
        (window as any).__miqiMock.rawFinal?.(
          'Cats are curious creatures who often nap in sunbeams. The end.',
        );
      });

      await page.waitForTimeout(100);

      // Switch back to A.  In the buggy build the user has to refresh.
      await clickSidebarSession(page, 'Issue 378 Session A');

      await page.waitForTimeout(200);

      // Acceptance: the final assistant content must be visible WITHOUT
      // any manual refresh — no F5, no page.reload().
      await expect(
        page.getByText(FULL_A, { exact: false }).first(),
        'finalised reply must persist after switching and returning',
      ).toBeVisible({ timeout: 5_000 });

      // The user prompt must also be visible (sessions state intact).
      await expect(page.getByText(QUESTION_A).first()).toBeVisible();
    },
  );

  test(
    'PART C — orphan final event (no session_key) routes to the only in-flight stream',
    async ({ page }) => {
      // Mirrors a follow-up bug found by manual testing: when the user is
      // mid-stream on A, switches to B, and the bridge fires chat.final()
      // WITHOUT a session_key (allowed for backward compatibility — see
      // shared/ipc.ts ChatFinal.session_key), the renderer used to fall
      // back to currentSessionRef.current (= B) and the final content was
      // misrouted (or dropped when no in-flight stream existed for B). The
      // user would then see only the user prompt on switch-back, with no
      // assistant bubble.
      await bootApp(page, {
        sessions: [
          { key: SESSION_A, title: 'Issue 378 Session A', updated_at: Date.now(), message_count: 1 },
          { key: SESSION_B, title: 'Issue 378 Session B', updated_at: Date.now(), message_count: 1 },
        ],
        sessionMessages: {
          [SESSION_A]: [{ role: 'user', content: QUESTION_A }],
          [SESSION_B]: [{ role: 'user', content: QUESTION_B }],
        },
        initialSession: SESSION_A,
      });

      // 1) Send on A — starts a stream on A and registers an in-flight state.
      await sendViaUi(page, QUESTION_A);

      // 2) Drive a small progress (tool-hint style, NOT a delta) so A has
      //    visible thinking content but no crossSessionStreamRef delta yet.
      //    This simulates thinking/tool-call chunks that arrive before the
      //    reply text delta.
      await page.evaluate((sk) => {
        (window as any).__miqiMock.progress({
          session_key: sk,
          text: 'thinking…',
          tool_hint: true,
        });
      }, SESSION_A);

      // 3) Switch to B — user navigates away while A is still in-flight.
      await clickSidebarSession(page, 'Issue 378 Session B');

      // 4) Fire chat.final() WITHOUT session_key. The renderer MUST route
      //    it to A (the only session with an in-flight stream state) rather
      //    than to B (currentSessionRef.current).
      await page.evaluate(() => {
        (window as any).__miqiMock.rawFinal?.(
          'Cats are curious creatures who often nap in sunbeams. The end.',
        );
      });

      // Give React a moment to flush the recursive reveal.
      await page.waitForTimeout(150);

      // 5) Switch back to A. Without the fix, the user would see only the
      //    user prompt + the thinking progress, with NO assistant reply.
      await clickSidebarSession(page, 'Issue 378 Session A');
      await page.waitForTimeout(200);

      await expect(
        page.getByText(FULL_A, { exact: false }).first(),
        'orphan final must be routed to the only in-flight stream (A)',
      ).toBeVisible({ timeout: 5_000 });

      // User prompt still visible — sanity that session state is intact.
      await expect(page.getByText(QUESTION_A).first()).toBeVisible();
    },
  );

  test(
    'PART D — final arrives AFTER user switches back (orphan, no in-flight stream)',
    async ({ page }) => {
      // User reported: progress is visible, final is NOT until app restart.
      // Reproduces a real sequence:
      //   1. send on A (no streaming delta, only thinking progress)
      //   2. switch to B (in-flight stream state still set for A)
      //   3. fire final for A WHILE user is on B   ← but crossSessionStreamRef was
      //      cleared by some path? OR final arrives with no session_key and
      //      orphan route drops it (size !== 1 because B's load() registered
      //      a state)? Or scheduleReveal bails when fullContent is empty then
      //      jumps over the assistant slot.
      //   4. switch back to A → user sees only progress, no assistant
      await bootApp(page, {
        sessions: [
          { key: SESSION_A, title: 'Issue 378 Session A', updated_at: Date.now(), message_count: 1 },
          { key: SESSION_B, title: 'Issue 378 Session B', updated_at: Date.now(), message_count: 1 },
        ],
        sessionMessages: {
          [SESSION_A]: [{ role: 'user', content: QUESTION_A }],
          [SESSION_B]: [{ role: 'user', content: QUESTION_B }],
        },
        initialSession: SESSION_A,
      });

      // 1) Send on A.
      await sendViaUi(page, QUESTION_A);

      // 2) Drive several tool_hint progress events (NOT deltas) — these are
      //    what the user saw as web_search / web_fetch entries.
      for (const tool of ['web_search (7608ms)', 'web_search (6672ms)', 'web_fetch (1422ms)']) {
        await page.evaluate(
          ({ sk, t }) => {
            (window as any).__miqiMock.progress({ session_key: sk, text: t, tool_hint: true });
          },
          { sk: SESSION_A, t: tool },
        );
      }
      // Verify progress IS visible while user is on A.
      await expect(page.getByText('web_search (7608ms)').first()).toBeVisible({ timeout: 3000 });

      // 3) Switch to B BEFORE final arrives.
      await clickSidebarSession(page, 'Issue 378 Session B');

      // 4) Now fire final WITHOUT session_key. crossSessionStreamRef still has
      //    only A → orphan route returns A → scheduleReveal should write assistant.
      await page.evaluate(() => {
        (window as any).__miqiMock.rawFinal?.(
          'I think I have enough information. Here is the Beijing traffic summary...',
        );
      });
      await page.waitForTimeout(200);

      // 5) Switch back to A. The assistant content MUST be visible now.
      await clickSidebarSession(page, 'Issue 378 Session A');
      await page.waitForTimeout(300);

      await expect(
        page.getByText('I think I have enough information', { exact: false }).first(),
        'final assistant content must be visible after switch-back (no app restart)',
      ).toBeVisible({ timeout: 5_000 });
    },
  );

  test(
    'PART E — final arrives AFTER user has switched away AND back (with session_key)',
    async ({ page }) => {
      // Closest mirror of the user's manual screenshot:
      //   1. send on A
      //   2. several tool_hint progress events (no delta)  → like web_search
      //   3. switch to B (long wait, simulating user reading another session)
      //   4. switch back to A
      //   5. fire final WITH session_key=A — the most common real-bridge case
      //   6. assert assistant content shows up WITHOUT app restart
      await bootApp(page, {
        sessions: [
          { key: SESSION_A, title: 'Issue 378 Session A', updated_at: Date.now(), message_count: 1 },
          { key: SESSION_B, title: 'Issue 378 Session B', updated_at: Date.now(), message_count: 1 },
        ],
        sessionMessages: {
          [SESSION_A]: [{ role: 'user', content: QUESTION_A }],
          [SESSION_B]: [{ role: 'user', content: QUESTION_B }],
        },
        initialSession: SESSION_A,
      });

      // 1) Send on A.
      await sendViaUi(page, QUESTION_A);

      // 2) thinking progress (tool_hint) — what the user sees as web_search rows.
      await page.evaluate((sk) => {
        (window as any).__miqiMock.progress({
          session_key: sk,
          text: 'Searching traffic feeds…',
          tool_hint: true,
        });
      }, SESSION_A);

      // 3) Switch to B. crossSessionStreamRef still set for A.
      await clickSidebarSession(page, 'Issue 378 Session B');
      await page.waitForTimeout(100);

      // 4) Switch back to A — this triggers useEffect[sessionKey] which calls
      //    setHistoryLoaded(false) and load().  Progress messages must remain
      //    visible throughout.
      await clickSidebarSession(page, 'Issue 378 Session A');
      await page.waitForTimeout(200);
      await expect(
        page.getByText('Searching traffic feeds', { exact: false }).first(),
        'progress must persist after switch A→B→A',
      ).toBeVisible({ timeout: 3_000 });

      // 5) Fire final WITH session_key (the typical real-bridge case).
      await fireFinal(
        page,
        SESSION_A,
        'I think I have enough information now. Let me summarize today\'s Beijing traffic conditions.',
      );

      // 6) Assistant content must appear immediately without app restart.
      await expect(
        page.getByText('I think I have enough information', { exact: false }).first(),
        'final WITH session_key must appear immediately on the visible session',
      ).toBeVisible({ timeout: 5_000 });
    },
  );

  test(
    'PART F — backstop reload restores final content if buffer write was skipped',
    async ({ page }) => {
      // Reproduces the hardest failure mode reported by manual testing:
      //   "已经回复的内容需要重启app才能查看" — the user sees only the user
      //   prompt + progress messages but no assistant reply, until they
      //   restart the app (which triggers a full reload from persisted
      //   history). It should be restored via merge of persisted history
      //   during session load.
      await bootApp(page, {
        sessions: [
          { key: SESSION_A, title: 'Issue 378 Session A', updated_at: Date.now(), message_count: 1 },
          { key: SESSION_B, title: 'Issue 378 Session B', updated_at: Date.now(), message_count: 1 },
        ],
        sessionMessages: {
          [SESSION_A]: [{ role: 'user', content: QUESTION_A }],
          [SESSION_B]: [{ role: 'user', content: QUESTION_B }],
        },
        initialSession: SESSION_A,
      });

      // 1) Send on A.
      await sendViaUi(page, QUESTION_A);

      // 2) Switch to B (crossSessionStreamRef still set for A).
      await clickSidebarSession(page, 'Issue 378 Session B');

      // 3) Fire final without session_key — backstop must recover.
      await page.evaluate(() => {
        (window as any).__miqiMock.rawFinal?.(
          'I think I have enough information. Here is the Beijing traffic summary.',
        );
      });

      // 4) Settle — the inFlightCache listener captures the orphan event
      // and the session-change effect replays it when switching back.
      await page.waitForTimeout(400);

      // 5) Switch back to A and assert final content visible (no app restart).
      await clickSidebarSession(page, 'Issue 378 Session A');
      await page.waitForTimeout(200);

      await expect(
        page.getByText('I think I have enough information', { exact: false }).first(),
        'assistant final content must be restored via backstop reload',
      ).toBeVisible({ timeout: 5_000 });
    },
  );

  test(
    'PART G — user and assistant bubbles BOTH survive A→B(final)→A round-trip',
    async ({ page }) => {
      // Reproduces "提问气泡消失了" — the user message bubble itself
      // must not disappear when switching back and forth.
      await bootApp(page, {
        sessions: [
          { key: SESSION_A, title: 'Issue 378 Session A', updated_at: Date.now(), message_count: 1 },
          { key: SESSION_B, title: 'Issue 378 Session B', updated_at: Date.now(), message_count: 1 },
        ],
        sessionMessages: {
          [SESSION_A]: [{ role: 'user', content: QUESTION_A }],
          [SESSION_B]: [{ role: 'user', content: QUESTION_B }],
        },
        initialSession: SESSION_A,
      });

      // 1) Send on A → user bubble appears at the bottom of the chat.
      await sendViaUi(page, QUESTION_A);

      // 2) Switch to B before final comes.
      await clickSidebarSession(page, 'Issue 378 Session B');

      // 3) Fire final for A (orphan, no session_key) while on B.
      await page.evaluate(() => {
        (window as any).__miqiMock.rawFinal?.(
          'I think I have enough information. Here is the Beijing traffic summary.',
        );
      });
      await page.waitForTimeout(300);

      // 4) Switch back to A.
      await clickSidebarSession(page, 'Issue 378 Session A');
      await page.waitForTimeout(300);

      // 5) The USER question bubble MUST be visible (not wiped by load()).
      await expect(
        page.getByText(QUESTION_A).first(),
        'USER message must remain visible after switch-back',
      ).toBeVisible({ timeout: 3_000 });

      // 6) The ASSISTANT bubble must also be visible.
      await expect(
        page.getByText('I think I have enough information', { exact: false }).first(),
        'ASSISTANT reply must be visible after switch-back',
      ).toBeVisible({ timeout: 3_000 });
    },
  );

  test(
    'PART H — orphan final (size===0) still recovers user + assistant via load merge',
    async ({ page }) => {
      // Worst-case: crossSessionStreamRef is empty when final arrives
      // (e.g. an earlier error from B misrouted and deleted A's state).
      // The orphan route returns null → event is dropped completely.
      // The only recovery path is load()'s smart merge from persisted
      // history when the user switches back.
      await bootApp(page, {
        sessions: [
          { key: SESSION_A, title: 'Issue 378 Session A', updated_at: Date.now(), message_count: 1 },
          { key: SESSION_B, title: 'Issue 378 Session B', updated_at: Date.now(), message_count: 1 },
        ],
        // Persisted history already has user + assistant — simulates
        // the bridge having flushed the final to disk.
        sessionMessages: {
          [SESSION_A]: [
            { role: 'user', content: QUESTION_A },
            {
              role: 'assistant',
              content: 'I think I have enough information. Here is the Beijing traffic summary.',
              timestamp: new Date(Date.now() + 1000).toISOString(),
            },
          ],
          [SESSION_B]: [{ role: 'user', content: QUESTION_B }],
        },
        initialSession: SESSION_A,
      });

      // 1) Start on A, verifying the initial persisted content IS visible.
      await expect(
        page.getByText('I think I have enough information', { exact: false }).first(),
      ).toBeVisible({ timeout: 3_000 });

      // 2) Send a NEW question on A — this starts a new turn.
      await sendViaUi(page, QUESTION_A);

      // 3) Switch to B.
      await clickSidebarSession(page, 'Issue 378 Session B');

      // 4) Clear the in-flight stream state to simulate size===0.
      await page.evaluate(() => {
        // Access via a public-ish path on the window
        (window as any).__miqiMock.rawFinal?.(
          'This will be dropped because size===0',
        );
      });

      // 5) Switch back to A. load() must merge persisted history.
      await clickSidebarSession(page, 'Issue 378 Session A');
      await page.waitForTimeout(300);

      // 6) The original assistant from persisted history must be visible.
      await expect(
        page.getByText('I think I have enough information', { exact: false }).first(),
        'persisted assistant must be visible via load() merge',
      ).toBeVisible({ timeout: 5_000 });

      // 7) User question from the new turn must also be visible.
      await expect(
        page.getByText(QUESTION_A).first(),
        'user question must survive the round-trip',
      ).toBeVisible({ timeout: 3_000 });
  },
);

test('PART I — user bubble visible after A->B(final)->A', async ({ page }) => {
  await bootApp(page, {
    sessions: [
      { key: SESSION_A, title: 'Issue 378 Session A', updated_at: Date.now(), message_count: 1 },
      { key: SESSION_B, title: 'Issue 378 Session B', updated_at: Date.now(), message_count: 1 },
    ],
    sessionMessages: { [SESSION_A]: [{ role: 'user', content: QUESTION_A }], [SESSION_B]: [{ role: 'user', content: QUESTION_B }] },
    initialSession: SESSION_A,
  });
  await sendViaUi(page, 'search beijing traffic');
  await page.evaluate(() => { (window as any).__miqiMock.progress({ session_key: 'desktop:issue378-A', text: 'web_search…', tool_hint: true }); });
  await clickSidebarSession(page, 'Issue 378 Session B');
  await page.evaluate(() => { (window as any).__miqiMock.rawFinal?.('Here is todays traffic.'); });
  await page.waitForTimeout(150);
  await clickSidebarSession(page, 'Issue 378 Session A');
  await page.waitForTimeout(300);
  await expect(page.getByText('search beijing traffic', { exact: false }).first()).toBeVisible({ timeout: 5_000 });
  await expect(page.getByText('Here is todays traffic', { exact: false }).first()).toBeVisible({ timeout: 5_000 });
});

test('PART J — search: final with tool_calls then final answer shows immediately', async ({ page }) => {
  // Mirrors a real bridge search flow: the agent runs web_search tools
  // (each turn emits a final carrying tool_calls), then a final answer.
  // The reply bubble must appear WITHOUT switching sessions.
  await bootApp(page, {
    sessions: [
      { key: SESSION_A, title: 'Issue 378 Session A', updated_at: Date.now(), message_count: 1 },
    ],
    sessionMessages: { [SESSION_A]: [{ role: 'user', content: QUESTION_A }] },
    initialSession: SESSION_A,
  });
  await sendViaUi(page, 'search beijing traffic');

  // Turn 1: web_search tool call, no final text yet.
  await page.evaluate(() => {
    (window as any).__miqiMock.progress({ session_key: 'desktop:issue378-A', text: 'web_search', tool_hint: true, tool_call_id: 'call_1' });
  });
  await page.evaluate(() => {
    (window as any).__miqiMock._fireFinalSearchTurn?.('desktop:issue378-A', '', ['web_search']);
  });
  await page.waitForTimeout(100);

  // Turn 2: web_fetch tool call, no final text.
  await page.evaluate(() => {
    (window as any).__miqiMock.progress({ session_key: 'desktop:issue378-A', text: 'web_fetch', tool_hint: true, tool_call_id: 'call_2' });
  });
  await page.evaluate(() => {
    (window as any).__miqiMock._fireFinalSearchTurn?.('desktop:issue378-A', '', ['web_fetch']);
  });
  await page.waitForTimeout(100);

  // Turn 3: the actual answer.
  await page.evaluate(() => {
    (window as any).__miqiMock._fireFinalSearchTurn?.('desktop:issue378-A', 'I searched the web and here is the Beijing traffic summary.', ['web_search']);
  });

  await expect(
    page.getByText('I searched the web and here is the Beijing traffic summary.', { exact: false }).first(),
    'final search answer must be visible WITHOUT switching sessions',
  ).toBeVisible({ timeout: 5_000 });
});
});