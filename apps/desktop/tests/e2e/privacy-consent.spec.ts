/**
 * Privacy consent gate E2E (issue #837) — 首次启动隐私协议确认门。
 *
 * 覆盖四条路径（全部禁用 MIQI_E2E 绕过，走真实确认门）：
 *  1. 拒绝并退出：首次启动展示协议 → 点「拒绝并退出」→ 应用退出；
 *  2. 同意进入：重启（同一 MIQI_HOME，同意未持久化）→ 门再次出现 →
 *     点「同意并继续」→ 主界面加载；
 *  3. 同意持久化：再次重启 → 门不再出现，直接进入主界面；
 *  4. 应用内入口：设置 → 隐私协议 页可随时查阅协议文本。
 *
 * serial 模式：测试共享同一个 MIQI_HOME 的同意状态，必须按序执行
 * （playwright.config.ts 全局 fullyParallel）。
 *
 * Run: cd apps/desktop && npx playwright test \
 *      --config=playwright.config.ts --project=electron -g "Privacy consent"
 */

import { test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import { launchElectronApp, relaunchElectronApp, closeElectronApp } from './helpers/electron-setup';

test.describe.serial('Privacy consent gate (#837)', () => {
  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
  });

  test('拒绝并退出：应用直接退出', { timeout: 180_000 }, async () => {
    const isMac = process.platform === 'darwin';
    // 不设 MIQI_E2E → 主进程不下发 --miqi-e2e → 渲染层展示真实确认门
    const fixture = await launchElectronApp(undefined, { noConsentBypass: true });
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;

    // dev 模式下 userData 按 checkout 共享（main 的 ws-<hash> setPath 覆盖了
    // --user-data-dir），本 checkout 此前运行留下的同意状态会让门被跳过。
    // 先清掉同意记录，必要时重启一次，确保验证的是真实确认门而非缓存。
    await page.evaluate(() => {
      try {
        localStorage.removeItem('miqi:privacyConsentVersion');
      } catch {
        /* ignore */
      }
    });
    if ((await page.getByTestId('privacy-consent-gate').count()) === 0) {
      // 本次启动直接进了主界面（旧同意生效）→ 重启让门按清理后的状态出现
      await closeElectronApp(electronApp, miqiHome, true);
      const fresh = await relaunchElectronApp(miqiHome, { noConsentBypass: true });
      electronApp = fresh.electronApp;
      page = fresh.page;
    }

    await expect(page.getByTestId('privacy-consent-gate')).toBeVisible({ timeout: 30_000 });
    // 协议文本含版本号（中英文均显示 1.0）
    await expect(page.getByTestId('privacy-consent-text')).toContainText('1.0');

    const closed = electronApp.waitForEvent('close', { timeout: 20_000 }).catch(() => null);
    await page.getByTestId('privacy-consent-decline').click();

    if (isMac) {
      // macOS 的 window-all-closed 不退出应用 — 直接关闭实例收尾，
      // 保留 MIQI_HOME 供后续测试重启（后续测试在 macOS 上仍验证同意/持久化路径）。
      await electronApp.close().catch(() => {});
      return;
    }

    // window.close() → window-all-closed → app.quit()
    expect(await closed).not.toBeNull();
  });

  test('同意并继续：主界面加载', { timeout: 180_000 }, async () => {
    // 上一测试未同意（拒绝了 / macOS 直接关闭）→ 门再次出现
    const fixture = await relaunchElectronApp(miqiHome, { noConsentBypass: true });
    electronApp = fixture.electronApp;
    page = fixture.page;

    await expect(page.getByTestId('privacy-consent-gate')).toBeVisible({ timeout: 30_000 });

    // 确认门本身的截图（点同意前）
    await page.screenshot({
      path: `test-results/${test.info().title.replace(/\s+/g, '-')}-consent-gate.png`,
      fullPage: true,
    });

    await page.getByTestId('privacy-consent-agree').click();

    await expect(page.getByTestId('app-title')).toBeVisible({ timeout: 60_000 });
    await expect(page.getByTestId('privacy-consent-gate')).toHaveCount(0);

    // 关掉实例（保留 MIQI_HOME），让下一测试干净重启
    await closeElectronApp(electronApp, miqiHome, true);
  });

  test('同意持久化：重启后不再展示确认门', { timeout: 180_000 }, async () => {
    // 同意状态写入同一 userData 的 localStorage → 重启后直接进主界面
    const fixture = await relaunchElectronApp(miqiHome, { noConsentBypass: true });
    electronApp = fixture.electronApp;
    page = fixture.page;

    await expect(page.getByTestId('app-title')).toBeVisible({ timeout: 60_000 });
    await expect(page.getByTestId('privacy-consent-gate')).toHaveCount(0);
  });

  test('设置页可随时查阅隐私协议', { timeout: 60_000 }, async () => {
    // 沿用上一测试的主界面实例
    await page.getByTestId('nav-system-settings').click();
    await expect(page.getByText('设置', { exact: true }).first()).toBeVisible({
      timeout: 30_000,
    });

    await page.getByRole('tab', { name: /隐私协议/ }).click();
    await expect(page.getByTestId('settings-privacy-page')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId('settings-privacy-text')).toContainText('1.0');
    await expect(page.getByTestId('settings-privacy-text')).toContainText('隐私协议');

    await page.screenshot({
      path: `test-results/${test.info().title.replace(/\s+/g, '-')}-settings-privacy.png`,
      fullPage: true,
    });
  });
});
