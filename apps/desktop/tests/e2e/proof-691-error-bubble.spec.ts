/**
 * Proof spec for issue #691 — captures a screenshot of the localized
 * (Chinese) PermissionError bubble in the chat UI.
 *
 * The bug (#691): backend tool-layer PermissionErrors rendered their raw
 * English tech message ("Path 'C:...' resolves outside all legal roots
 * [...]. tools.extra_roots") in the chat bubble.  The fix attaches a
 * Chinese `user_message` to the exception; the orchestrator boundary
 * (_sanitize_exc_for_ui) prefers it, and the renderer shows it verbatim.
 *
 * This spec injects a ToolErrorEvent (exactly the shape the backend emits
 * on chat:progress) from the main process while a send is in flight, then
 * screenshots the red error bubble.
 *
 * Run (not part of CI):
 *   cd apps/desktop && npm run build
 *   PLAYWRIGHT_SKIP_WEB_SERVER=1 \
 *     npx playwright test --config=playwright.config.ts --project=electron \
 *       proof-691-error-bubble --reporter=line
 */
import { test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import {
  launchElectronApp,
  closeElectronApp,
  waitForInputReady,
} from './helpers/electron-setup';

const OUT_DIR = join(__dirname, '../../test-results/proof-691');

// Matches the backend's ToolPermissionError user_message for the
// "outside legal roots" case (filesystem.py / _canonicalize_wsl_mnt_path).
const CHINESE_MESSAGE =
  '文件访问被拒绝：该路径不在允许访问的目录范围内（C:\\Users\\demo\\test_bridge.txt）。' +
  '如需允许访问，请在设置中为该目录添加访问权限（tools.extra_roots）。';

test.describe('Proof #691 error bubble localization', () => {
  let electronApp: ElectronApplication;
  let page: Page;

  test.beforeAll(async () => {
    mkdirSync(OUT_DIR, { recursive: true });
  });

  test.afterAll(async () => {
    await closeElectronApp(electronApp).catch(() => {});
  });

  test('capture Chinese PermissionError bubble screenshot', async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;

    const textarea = await waitForInputReady(page);
    await textarea.fill('演示 #691：触发一次权限错误气泡');
    await textarea.press('Enter');

    // handleSend subscribes onProgress only AFTER `await providers.list()`
    // (ChatConsole.tsx ~3054) — an injection sent immediately after Enter can
    // land in that async gap and be dropped.  So retry-inject until the bubble
    // renders: check-first-then-inject guarantees exactly one bubble lands.
    const bubble = page.getByText(CHINESE_MESSAGE).last();
    const deadline = Date.now() + 20_000;
    while (Date.now() < deadline) {
      if (await bubble.isVisible().catch(() => false)) break;
      await electronApp.evaluate(({ BrowserWindow }, args) => {
        for (const win of BrowserWindow.getAllWindows()) {
          if (win.isDestroyed() || win.webContents.isDestroyed()) continue;
          win.webContents.send('chat:progress', {
            event: 'ToolErrorEvent',
            data: {
              // Mirrors the real bridge payload (bridge/loop.py) for a
              // ToolErrorEvent: asdict(event) carries type/recoverable.
              type: 'tool_error',
              message: args.message,
              turn_id: 'proof-691',
              tool_name: 'read_file',
              tool_call_id: 'proof-691',
              recoverable: true,
            },
          });
        }
      }, { message: CHINESE_MESSAGE });
      await page.waitForTimeout(300);
    }

    // The Chinese message must render as a standalone error bubble.
    await expect(bubble).toBeVisible({ timeout: 5_000 });

    // Assert the English tech details are NOT on screen.
    const bodyText = await page.textContent('body');
    expect(bodyText).not.toContain('outside all legal roots');

    const shot = join(OUT_DIR, 'proof-691-chinese-error-bubble.png');
    await page.screenshot({ path: shot, timeout: 5000 });
    console.log(`[proof-691] screenshot → ${shot}`);
  });
});
