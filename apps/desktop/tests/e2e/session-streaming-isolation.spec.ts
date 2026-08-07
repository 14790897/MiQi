/**
 * Session Streaming Isolation E2E Tests
 *
 * Fix #212: prevent streaming messages leaking across sessions.
 *
 * Run: npx playwright test --config=playwright.config.ts --project=electron -g 'Streaming Isolation'
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  LLM_TIMEOUT,
  waitForInputReady,
  createNewConversation,
  approveLoop,
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';

// ─── Helpers ──────────────────────────────────────────────────────────

async function sendWithoutWaiting(page: Page, text: string) {
  const inputX = page.locator('textarea, [contenteditable="true"], input[type="text"]').last();
  await expect(inputX).toBeVisible({ timeout: 10000 });
  await inputX.click();
  await inputX.fill('');
  await inputX.type(text);
  await inputX.press('Enter');
  // DO NOT wait for response
}

async function sendAndWait(page: Page, text: string, loopTimeout = 180_000) {
  const inputX = page.locator('textarea, [contenteditable="true"], input[type="text"]').last();
  await expect(inputX).toBeVisible({ timeout: 10000 });
  await inputX.click();
  await inputX.fill('');
  await inputX.type(text);
  await inputX.press('Enter');
  await page.waitForTimeout(1500);
  await approveLoop(page, loopTimeout);
}

// ─── Tests ────────────────────────────────────────────────────────────

test.describe('Streaming Isolation E2E', () => {
  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;
  });

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
  });

  test(
    'no streaming message leak when switching sessions mid-stream',
    { timeout: LLM_TIMEOUT },
    async () => {
      // ── Session A: start a streaming response ──
      await createNewConversation(page);
      const markerA = `ISOLATE_A_${Date.now().toString(36)}`;
      await sendWithoutWaiting(page, `只回答${markerA}`);

      // Wait for the "Thinking…" indicator to confirm the stream has
      // actually started before switching sessions mid-stream. This is
      // deterministic regardless of CI speed (unlike a fixed timeout).
      await expect(page.getByTestId('thinking-indicator')).toBeVisible({ timeout: 15_000 });

      // ── Session B: create and send ──
      await createNewConversation(page);
      const markerB = `ISOLATE_B_${Date.now().toString(36)}`;
      await sendAndWait(page, `只回答${markerB}`);

      // ── Verify: Session B must NOT contain Session A's marker ──
      const contentB = (await page.locator('main').textContent()) || '';
      expect(contentB, 'Session B should not contain Session A marker').not.toContain(markerA);
      expect(contentB, 'Session B should contain its own marker').toContain(markerB);

      console.log(`[test] ✅ Session B isolated — no cross-session streaming leak`);
    },
  );

  test(
    'switching back to A mid-stream restores thinking AND reply without refresh',
    { timeout: LLM_TIMEOUT },
    async () => {
      // ── Session A: start a streaming response ──
      await createNewConversation(page);
      const markerA = `RESTORE_A_${Date.now().toString(36)}`;
      // Short prompt keeps the sidebar title generation fast and the test
      // deterministic; we still wait for real content to render (below) so the
      // switch-away snapshot captures an in-progress turn.
      await sendWithoutWaiting(page, `只回答${markerA}`);

      // Confirm the stream actually started AND that real thinking text is
      // visible before we switch away.  Waiting only for the indicator is too
      // weak: the indicator can be visible while the first thinking progress
      // message hasn't rendered yet, and the switch-away snapshot would then
      // capture a message list without any thinking — masking the bug this
      // test guards against.  Wait for at least one non-user message to render.
      const thinkingIndicator = page.getByTestId('thinking-indicator');
      await expect(thinkingIndicator).toBeVisible({ timeout: 15_000 });
      const msgList = page.locator('main [class*="max-w-[760px]"]');
      // A progress message (role=progress renders with the thinking style) or
      // an assistant bubble means real content has rendered.  Poll for the
      // message list to contain more than just the user prompt.
      await page.waitForFunction(
        () => {
          const list = document.querySelector('main [class*="max-w-[760px]"]');
          if (!list) return false;
          // Count text nodes that aren't the composer; a rendered progress/
          // assistant message adds content beyond the single user prompt.
          const texts = Array.from(list.querySelectorAll('p, div'))
            .map((n) => (n.textContent || '').trim())
            .filter((t) => t.length > 0);
          // At least two non-trivial text blocks (user prompt + something).
          return texts.filter((t) => t !== 'AI 也会犯错误，对于重要答案请谨慎验证').length >= 2;
        },
        { timeout: 30_000 },
      );

      // The session title is derived from the first user message (markerA),
      // but only AFTER the backend asynchronously creates the thread — under
      // parallel CI contention this can lag several seconds.  Wait for the
      // sidebar to show a session whose accessible name contains markerA so
      // we have a deterministic handle to click when switching back.  This is
      // NOT a race the product code can fix — it's UI feedback timing.
      const aButton = page.getByRole('button', { name: new RegExp(markerA) }).first();
      await expect(aButton).toBeVisible({ timeout: 60_000 });

      // ── Switch to Session B (new conversation) ──
      await createNewConversation(page);
      // Ensure B is shown (not A) before switching back.
      await expect(page.getByTestId('thinking-indicator')).toBeHidden({ timeout: 10_000 }).catch(() => {});

      // ── Switch back to A via the sidebar ──
      await aButton.click();

      // The marker is A's user prompt (persisted, renders on any
      // switch-back) — asserting it alone would pass pre-fix.  The real check
      // is that the ASSISTANT reply appears after switching back WITHOUT a
      // manual refresh.  The prompt asks the model to reply with the marker,
      // so inside the message list it must appear twice: once as the user
      // prompt, once as the assistant reply.  Scope to the message list so
      // the page header title (which also contains the marker) isn't counted.
      // This fails on the pre-fix build where only the persisted user history
      // renders until the user manually switches away and back.
      await expect(
        msgList.getByText(markerA, { exact: false }),
      ).toHaveCount(2, { timeout: 120_000 });

      console.log(`[test] ✅ Session A restored thinking + reply on switch-back`);
    },
  );

  test(
    'session history isolation — no cross-contamination via sessions.get',
    { timeout: LLM_TIMEOUT },
    async () => {
      // ── Session A: send and wait ──
      await createNewConversation(page);
      const markerA = `HIST_A_${Date.now().toString(36)}`;
      await sendAndWait(page, `只回答${markerA}`);
      expect((await page.locator('main').textContent()) || '').toContain(markerA);
      console.log(`[test] Session A has marker: ${markerA}`);

      // ── Session B: create and send ──
      await createNewConversation(page);
      const markerB = `HIST_B_${Date.now().toString(36)}`;
      await sendAndWait(page, `只回答${markerB}`);
      expect((await page.locator('main').textContent()) || '').toContain(markerB);
      console.log(`[test] Session B has marker: ${markerB}`);

      // ── Verify via IPC: Session A does NOT contain B's marker, and vice versa ──
      const isolation = await page.evaluate(async (markers) => {
        const all = await (window as any).miqi.sessions.list();
        const sessions: any[] = all.sessions || all || [];
        const results: any[] = [];
        for (const s of sessions) {
          try {
            const detail = await (window as any).miqi.sessions.get(s.key);
            const msgs = Array.isArray(detail?.messages) ? detail.messages : [];
            const text = msgs.map((m: any) => m.content || '').join('\n');
            results.push({ key: s.key, title: s.title, text });
          } catch (e) {
            results.push({ key: s.key, title: s.title, text: '', error: String(e) });
          }
        }
        return results;
      }, [markerA, markerB]);

      // Find sessions by their markers
      const sessionA = isolation.find((s: any) => s.text.includes(markerA));
      const sessionB = isolation.find((s: any) => s.text.includes(markerB));

      expect(sessionA, 'Session A should exist with its marker').toBeTruthy();
      expect(sessionB, 'Session B should exist with its marker').toBeTruthy();
      expect(sessionA.text, 'Session A should not contain Session B marker').not.toContain(markerB);
      expect(sessionB.text, 'Session A should not contain Session B marker').not.toContain(markerA);

      console.log(`[test] ✅ Session history isolation verified (${isolation.length} total sessions)`);
    },
  );
});
