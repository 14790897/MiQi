/**
 * Issue #109 regression: "每次AI回复前会出现一个空白的对话框"
 *
 * Root cause: ChatConsole.onFinal pushed an empty assistant bubble
 * (content: '') before the typewriter animation's first rAF frame, so a
 * blank message box flashed between the user's turn and the streamed reply.
 *
 * To observe the otherwise-one-frame flash, a MutationObserver records
 * whether the cursor-only bubble (`span.w-2.h-4.animate-pulse`, rendered only
 * when an assistant message has content === '') is ever added to the DOM.
 * With the bug, it appears (then gets filled in). With the fix, the bubble is
 * created only once it has real text, so the cursor never appears.
 */

import { test, expect } from '@playwright/test';
import { buildMockBridgeScript } from './mocks';

async function injectMockAndGoto(page: import('@playwright/test').Page) {
  await page.addInitScript({
    content: `
      (function () {
        window.__blankBubbleSeen = false;
        const mo = new MutationObserver(function (muts) {
          for (const m of muts) {
            for (const n of m.addedNodes) {
              if (n.nodeType === 1) {
                const match =
                  (n.matches && n.matches('span.inline-block.w-2.h-4.animate-pulse')) ||
                  (n.querySelector && n.querySelector('span.inline-block.w-2.h-4.animate-pulse'));
                if (match) window.__blankBubbleSeen = true;
              }
            }
          }
        });
        function start() {
          if (!document.getElementById('root')) {
            return setTimeout(start, 20);
          }
          mo.observe(document.getElementById('root'), { childList: true, subtree: true });
        }
        start();
      })();
    `,
  });
  await page.addInitScript({ content: buildMockBridgeScript() });
  await page.goto('/');
  await page.waitForSelector('#root', { state: 'visible' });
}

test.describe('Issue #109 — no blank bubble before AI reply', () => {
  test('never renders a cursor-only (empty) assistant bubble during a turn', async ({ page }) => {
    await injectMockAndGoto(page);

    const textarea = page.getByPlaceholder('Ask Agent to analyze or edit files...');
    await expect(textarea).toBeVisible({ timeout: 5000 });

    await textarea.fill('hello');
    await textarea.press('Enter');

    const reply = 'Hello from the mock agent!';
    await page.evaluate((c) => (window as any).__miqiMock.final(c), reply);

    // Reply text must render in an assistant bubble.
    await expect(page.getByText('Hello from the mock agent!')).toBeVisible({ timeout: 5000 });

    // Settle any remaining rAF frames so the typewriter finishes and React
    // is no longer mutating the bubble.
    await page.waitForTimeout(300);

    const sawBlank = await page.evaluate(() => (window as any).__blankBubbleSeen);
    expect(sawBlank, 'an empty (cursor-only) assistant bubble flashed before the reply').toBe(false);
  });

  test('does not leave an empty assistant bubble when the reply text is empty', async ({ page }) => {
    await injectMockAndGoto(page);

    const textarea = page.getByPlaceholder('Ask Agent to analyze or edit files...');
    await expect(textarea).toBeVisible({ timeout: 5000 });

    await textarea.fill('hi');
    await textarea.press('Enter');

    // Fire the final reply with an EMPTY content directly via the mock's
    // internal _fire. We can't use __miqiMock.final('') because that helper
    // does `content || 'default response'`, swallowing the empty string.
    await page.evaluate(() => (window as any).__miqiMock._fireFinal(''));
    // NOTE: __miqiMock._fireFinal must preserve an explicit '' (no fallback).

    await page.waitForTimeout(500);

    const sawBlank = await page.evaluate(() => (window as any).__blankBubbleSeen);
    expect(sawBlank, 'an empty reply left a cursor-only assistant bubble').toBe(false);
    // And no lingering cursor element either.
    await expect(page.locator('span.inline-block.w-2.h-4.animate-pulse')).toHaveCount(0);
  });
});
