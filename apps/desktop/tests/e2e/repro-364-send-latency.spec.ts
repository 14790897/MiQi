/**
 * TEMP repro spec for issue #364 — [ChatConsole] send blocks on
 * `providers:list` before showing the optimistic user bubble.
 *
 * The bug: `handleSend` awaits `window.miqi.providers.list()` FIRST, and only
 * inserts the user message / clears the input AFTER that IPC round-trip
 * resolves.  On a cold start the bridge queues providers.list behind its
 * init (PyInstaller extract 5-15s + WSL deps + sandbox) — so the UI sits
 * silent for seconds after Enter, making the user press Enter again →
 * duplicate messages/tasks.
 *
 * Trigger: patch the main-process `providers:list` handler to DELAY 5s then
 * return a healthy configured provider.  Send a message and measure:
 *   - latency from Enter → user bubble appears  (should be ~0 with optimistic UI)
 *   - latency from Enter → input box clears     (should be ~0 with optimistic UI)
 *   - a second Enter lands as a SECOND bubble   (duplicate — what the bug causes)
 *
 * Run:
 *   cd apps/desktop
 *   npm run build
 *   PLAYWRIGHT_SKIP_WEB_SERVER=1 \
 *     npx playwright test --config=playwright.config.ts --project=electron \
 *       repro-364-send-latency --reporter=list
 */

import { test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';

const PROVIDERS_LIST = 'providers:list';
const PROVIDER_DELAY_MS = 5_000;

test.describe('Repro #364: send latency behind slow providers:list', () => {
  let electronApp: ElectronApplication;
  let page: Page;

  test.afterAll(async () => {
    await closeElectronApp(electronApp).catch(() => {});
  });

  test('user bubble + input clear are blocked until providers:list resolves', async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;

    // ── Slow the providers:list handler (main process) — simulate a cold
    //    bridge that queues this IPC behind its init work. ──
    await electronApp.evaluate(async ({ ipcMain: ipc }, args: any) => {
      ipc.removeHandler(args.channel);
      ipc.handle(args.channel, async () => {
        await new Promise((r) => setTimeout(r, args.delay));
        return {
          providers: [
            {
              name: 'openai',
              display_name: 'OpenAI',
              env_key: 'OPENAI_API_KEY',
              provider_type: 'openai',
              is_gateway: false,
              is_local: false,
              default_api_base: 'https://api.openai.com/v1',
              configured: true,
              api_base: null,
            },
          ],
        };
      });
    }, { channel: PROVIDERS_LIST, delay: PROVIDER_DELAY_MS });

    const textarea = page.locator('[data-testid="chat-input-container"] textarea');
    await textarea.fill('repro-364 消息');
    const t0 = Date.now();
    await textarea.press('Enter');

    // ── Second Enter while providers:list is STILL pending (the bug: the user
    //    thinks the message wasn't sent because the input never cleared). ──
    await page.waitForTimeout(300);
    await textarea.press('Enter');

    // Sample right after Enter — the input box and user bubble should NOT have
    // been touched yet while providers:list is still pending.
    await page.waitForTimeout(500);
    const inputVal = await textarea.inputValue();
    const bubbleVisibleEarly = await page
      .getByTestId('chat-message-user')
      .last()
      .isVisible()
      .catch(() => false);
    const tEarly = Date.now() - t0;
    const bubbleCountEarly = await page.getByTestId('chat-message-user').count();
    // The optimistic user bubble should show a pending spinner while the send
    // is still waiting on the slow provider check.
    const pendingSpinnerVisible = await page
      .locator('[data-testid="chat-message-user"] svg.animate-spin')
      .last()
      .isVisible()
      .catch(() => false);

    // Wait until the (eventually-appearing) user bubble shows, or timeout.
    let tBubble = -1;
    try {
      await page.getByTestId('chat-message-user').last().waitFor({
        state: 'visible',
        timeout: PROVIDER_DELAY_MS + 5_000,
      });
      tBubble = Date.now() - t0;
    } catch {
      tBubble = -1;
    }

    const stillFilled = inputVal.trim().length > 0;

    // After providers:list resolves, wait for the turns to settle (both
    // handleSend invocations each append their own user bubble), then count.
    await page.waitForTimeout(PROVIDER_DELAY_MS + 2_000);
    const bubbleCountFinal = await page.getByTestId('chat-message-user').count();

    console.log(
      `\n[repro-364] 500ms after Enter: input still filled=${stillFilled}, ` +
        `user bubble visible=${bubbleVisibleEarly} (t=${tEarly}ms), ` +
        `bubble count early=${bubbleCountEarly}, pending spinner=${pendingSpinnerVisible}`,
    );
    console.log(
      `[repro-364] user bubble appeared after ${tBubble}ms (providers:list delayed ${PROVIDER_DELAY_MS}ms)`,
    );
    console.log(
      `[repro-364] 2× Enter → final user bubble count = ${bubbleCountFinal} ` +
        `(duplicate if > 1)`,
    );

    // The bug: the bubble appears only AFTER providers:list resolves, and the
    // input box is NOT cleared until then either.
    expect(
      bubbleVisibleEarly,
      'user bubble should appear immediately on Enter (optimistic UI), ' +
        'not wait for providers:list',
    ).toBe(true);
    expect(
      stillFilled,
      'input box should clear immediately on Enter',
    ).toBe(false);
    expect(
      pendingSpinnerVisible,
      'optimistic user bubble should show a pending spinner while waiting',
    ).toBe(true);
    expect(
      tBubble,
      `user bubble appeared at ${tBubble}ms — should be ~0, not blocked by the ` +
        `${PROVIDER_DELAY_MS}ms providers:list delay`,
    ).toBeLessThan(PROVIDER_DELAY_MS);
  });
});
