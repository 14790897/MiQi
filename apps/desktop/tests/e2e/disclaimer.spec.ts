/**
 * E2E: 常驻免责声明 — issue #836
 *
 * Validates:
 * 1. The persistent disclaimer renders BELOW the composer (消息流底部/输入框下方),
 *    with the localized copy (zh/en) from the shared constants module
 * 2. It stays visible while typing — 常驻 (the old in-composer hint faded out;
 *    this one must never hide)
 * 3. It survives a conversation switch (every conversation shows it)
 *
 * Pure UI test — no LLM round-trips needed.
 *
 * Run: cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron disclaimer.spec.ts --workers=1
 */

import { test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  launchElectronApp,
  closeElectronApp,
  waitForBridgeInitialized,
  waitForInputReady,
} from './helpers/electron-setup';
import { DISCLAIMER_TEXTS } from '../../src/renderer/lib/disclaimer';

const DISCLAIMER = '[data-testid="chat-disclaimer"]';
const COMPOSER = '[data-testid="chat-input-container"]';

test.describe('常驻免责声明 E2E', () => {
  let electronApp: ElectronApplication;
  let page: Page;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
    await waitForBridgeInitialized(page);
    await waitForInputReady(page);
  }, 60_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp);
  });

  test('渲染在输入框下方，文案匹配当前语言', async () => {
    const disclaimer = page.locator(DISCLAIMER);
    await expect(disclaimer).toBeVisible({ timeout: 15_000 });

    // 位置：composer（输入框）下方
    const composerBox = await page.locator(COMPOSER).boundingBox();
    const box = await disclaimer.boundingBox();
    expect(composerBox).not.toBeNull();
    expect(box).not.toBeNull();
    expect(box!.y).toBeGreaterThanOrEqual(composerBox!.y + composerBox!.height - 2);

    // 文案：与 lib/disclaimer.ts 常量一致（跟随 navigator.language）
    const lang = await page.evaluate(() => navigator.language);
    const expected =
      DISCLAIMER_TEXTS[lang.toLowerCase().split('-')[0]] ?? DISCLAIMER_TEXTS.zh;
    await expect(disclaimer).toHaveText(expected);
  });

  test('输入时不淡出（常驻，替代旧版渐隐声明）', async () => {
    const disclaimer = page.locator(DISCLAIMER);
    await expect(disclaimer).toBeVisible({ timeout: 10_000 });

    const input = page.locator(`${COMPOSER} textarea`);
    await input.fill('测试输入内容——免责声明不应淡出');

    // 旧实现输入时 opacity:0；新实现无淡出逻辑，恒为 1
    const opacity = await disclaimer.evaluate((el) => getComputedStyle(el).opacity);
    expect(parseFloat(opacity)).toBeGreaterThan(0.99);
    await expect(disclaimer).toBeVisible();

    // 清空输入，避免影响后续用例
    await input.fill('');
  });

  test('切换会话后仍常驻（每个会话底部都显示）', async () => {
    const disclaimer = page.locator(DISCLAIMER);
    await expect(disclaimer).toBeVisible({ timeout: 10_000 });

    const newSessionBtn = page.locator('[data-testid="nav-new-session"]');
    await expect(newSessionBtn).toBeVisible({ timeout: 5_000 });
    await newSessionBtn.click();

    // 新会话（ChatConsole 重新挂载/复用）后声明仍在底部
    await expect(disclaimer).toBeVisible({ timeout: 15_000 });
    await expect(disclaimer).toHaveText(
      DISCLAIMER_TEXTS[
        (await page.evaluate(() => navigator.language)).toLowerCase().split('-')[0]
      ] ?? DISCLAIMER_TEXTS.zh
    );
  });
});
