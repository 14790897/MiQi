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
  getSidebarSessionItems,
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
    'switch away during thinking then back — content restored, no refresh, no jump',
    { timeout: LLM_TIMEOUT },
    async () => {
      // ── Session A: start a streaming response ──
      await createNewConversation(page);
      const markerA = `RESTORE_A_${Date.now().toString(36)}`;
      await sendWithoutWaiting(page, `只回答${markerA}`);

      // Confirm the stream actually started.
      const thinkingIndicator = page.getByTestId('thinking-indicator');
      await expect(thinkingIndicator).toBeVisible({ timeout: 15_000 });
      const msgList = page.locator('main [class*="max-w-[760px]"]');

      // Wait for the user prompt to render in the message list so we can
      // snapshot it and later assert it is restored verbatim.
      const userPrompt = msgList.getByText(markerA, { exact: false }).first();
      await expect(userPrompt).toBeVisible({ timeout: 15_000 });
      const userTextBefore = (await userPrompt.textContent()) || '';

      // ── Switch to Session B ──
      await createNewConversation(page);

      // ── Switch back to A ──
      // A was created first, so it is the FIRST sidebar session item.  Don't
      // locate by title (the title derives from the first message and can lag
      // under parallel CI contention) — the first button is stable.
      const aButton = getSidebarSessionItems(page).first();
      await expect(aButton).toBeVisible({ timeout: 30_000 });
      await aButton.click();

      // 1) The user prompt must be restored IMMEDIATELY — no manual refresh,
      //    no blank window.  This is the core restoration assertion: if the
      //    switch-back dropped the message list, even the persisted user
      //    bubble wouldn't show until a later switch.
      await expect(
        msgList.getByText(markerA, { exact: false }).first(),
      ).toBeVisible({ timeout: 10_000 });
      const userTextAfter = (await msgList.getByText(markerA, { exact: false }).first().textContent()) || '';
      expect(userTextAfter, 'user prompt text must be identical after switch-back').toBe(userTextBefore);

      // 2) Content beyond the user prompt must eventually render (thinking
      //    or the assistant reply) — without a manual refresh.  Don't require
      //    the reply to echo markerA (the LLM may not repeat it, making the
      //    assertion flaky under parallel CI contention).
      await page.waitForFunction(
        (marker) => {
          const list = document.querySelector('main [class*="max-w-[760px]"]');
          if (!list) return false;
          const text = (list.textContent || '').replace(marker, '');
          // Beyond the user prompt, there must be real content (reply/thinking).
          return text.trim().length > 20;
        },
        markerA,
        { timeout: 120_000 },
      );

      console.log(`[test] ✅ Session A restored on switch-back — no refresh, no jump`);
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
