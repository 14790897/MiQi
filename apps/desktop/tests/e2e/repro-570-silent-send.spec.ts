/**
 * Repro/regression test for issue #570 — [ChatConsole] new session + send →
 * UI completely silent.
 *
 * The bug (fixed in this change):
 *   `ChatConsole.load()` retries `sessions.get` 10× with exponential backoff
 *   (500ms → 10s).  When the bridge is not running, `sendSafe` (bridge.ts:763)
 *   returns null every time.  Pre-fix, the retry window showed only a bare
 *   `Loader2` spinner (historyLoaded stays false, ChatConsole.tsx:4552) with
 *   no "正在连接…" text, and after exhaustion (ChatConsole.tsx:2270) the code
 *   only `console.warn`ed + `setHistoryLoaded(true)`, swapping the spinner for
 *   the blank empty state — no error bubble, the user saw silence.
 *
 * The fix: a "正在连接…" hint during the retry window, and an explicit
 * "会话加载失败…" error message after the retries are exhausted.
 *
 * This is a REGRESSION test — it asserts the DESIRED behaviour (connecting
 * hint + explicit error), so it FAILED on pre-fix code and passes now.
 *
 * Trigger: set `MIQI_PYTHON_PATH` to a python that passes launchElectronApp's
 * `import sys` probe but cannot actually boot the bridge (system Python 3.14
 * without the venv deps — no httpx).  `findBridgeExecutable` (bridge.ts:113)
 * picks it first, the bridge dies at startup, `sessions.get` returns null,
 * and the 10× retry runs on every session open.
 *
 * Note on reload: `launchElectronApp` waits ~60s for the bridge, which already
 * consumes the initial session's ~57s retry window.  So the test reloads the
 * renderer to start a FRESH retry cycle under its control.
 *
 * Run:
 *   cd apps/desktop
 *   npm run build
 *   PLAYWRIGHT_SKIP_WEB_SERVER=1 \
 *     MIQI_PYTHON_PATH="C:\Users\Guo\AppData\Local\Python\pythoncore-3.14-64\python.exe" \
 *     npx playwright test --config=playwright.config.ts --project=electron \
 *       repro-570-silent-send --reporter=list
 */

import { test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';

// The full retry window: 500+1000+2000+4000+8000+10000*5 ≈ 57s.
const RETRY_WINDOW_MS = 57_000;

test.describe('Repro #570: silent UI on session open with no bridge', () => {
  let electronApp: ElectronApplication;
  let page: Page;

  test.afterAll(async () => {
    await closeElectronApp(electronApp).catch(() => {});
  });

  test('dead bridge → connecting hint during retry, explicit error after exhaustion', async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;

    // Capture renderer console so we can PROVE the retry loop ran — it only
    // ever surfaces in the console, never in the UI (that's the bug).
    const consoleLines: string[] = [];
    page.on('console', (msg) => consoleLines.push(msg.text()));

    // Reload the renderer so ChatConsole remounts and starts a FRESH 10×
    // retry under our control (launchElectronApp's ~60s bridge-wait already
    // consumed the initial session's retry window).
    await page.reload();
    await page.waitForLoadState('domcontentloaded');
    await page
      .locator('[data-testid="chat-input-container"]')
      .waitFor({ state: 'attached', timeout: 15_000 });

    // ── Desired #1: during the ~57s retry window the UI should show a
    //    connecting/loading hint ("正在连接…").  Sample across the window —
    //    pre-fix code showed only a bare spinner with zero explanation. ──
    const samples: string[] = [];
    for (let i = 0; i < 8; i++) {
      samples.push((await page.locator('main').textContent()) ?? '');
      await page.waitForTimeout(3000);
    }
    expect(
      samples.join('\n'),
      'during the 10× retry the UI should show a connecting/loading explanation',
    ).toMatch(/连接|加载|重试|connecting|loading/i);

    // ── Desired #2: after the retries are exhausted the user should get an
    //    explicit error message (pre-fix code swapped the spinner for the
    //    blank empty state with no error at all). ──
    await page.waitForTimeout(RETRY_WINDOW_MS);
    const afterText = (await page.locator('main').textContent()) ?? '';
    expect(
      afterText,
      'after 10 exhausted retries the UI should show an explicit error message',
    ).toMatch(/加载失败|连接失败|重试失败|会话加载失败|出错|失败|error/i);

    // ── Desired #3: the error bubble is not a dead end — its "重试" button
    //    must trigger a fresh load (a new "Load attempt 1/10" console log),
    //    so a user (or the #480 slow-start path) can recover once the bridge
    //    comes back. ──
    const attemptsBefore = consoleLines.filter((l) =>
      /Load attempt \d+\/10 returned null/.test(l),
    ).length;
    const retryBtn = page.getByRole('button', { name: '重试' });
    await retryBtn.click({ timeout: 5_000 });
    await page.waitForTimeout(1000);
    const attemptsAfter = consoleLines.filter((l) =>
      /Load attempt \d+\/10 returned null/.test(l),
    ).length;
    expect(
      attemptsAfter,
      'clicking 重试 on the error bubble should trigger a fresh load() attempt',
    ).toBeGreaterThan(attemptsBefore);

    // The retry loop DID run (proven via console) and, thanks to the #570
    // fix, the UI now surfaced a connecting hint during the window and an
    // explicit error after it exhausted.
    const loadAttemptLines = consoleLines.filter((l) =>
      /Load attempt \d+\/10 returned null/.test(l),
    );
    expect(
      loadAttemptLines.length,
      'ChatConsole.load() retry loop ran (proven via console logs)',
    ).toBeGreaterThan(0);
    console.log(
      `[e2e] Retry loop ran ${loadAttemptLines.length} attempts before exhaustion — ` +
        `UI showed connecting hint + error after fix, 重试 button re-triggered load. ` +
        `First: ${loadAttemptLines[0]}`,
    );
  });
});
