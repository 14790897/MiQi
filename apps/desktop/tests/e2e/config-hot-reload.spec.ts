/**
 * E2E: Config hot reload (issue #789)
 *
 * Validates the tier A/B/C behavior after a config save:
 *   1. Tier A save (temperature) → toast「配置已生效，无需重启」+ NO restart banner
 *   2. Tier C save (wsl_distro) → status bar「需要重启」+ reason text + warn toast
 *
 * The config saves go through the real bridge (config.update → hot_apply →
 * config_updated broadcast → renderer listener), so this covers the full
 * IPC chain: renderer → main → python bridge → event → renderer.
 *
 * Run: cd apps/desktop && npx electron-vite build &&
 *      PLAYWRIGHT_SKIP_WEB_SERVER=1 npx playwright test --project=electron config-hot-reload.spec.ts
 */

import { test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';

test.describe.serial('Config hot reload (#789)', () => {
  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;
    // Capture bridge stdout for the config.update timeline (diagnostics).
    const proc = electronApp.process();
    (proc.stdout as any)?.on('data', (d: unknown) => {
      const s = String(d ?? '');
      if (s.includes('config.update') || s.includes('hot-apply') || s.includes('config_updated')) {
        console.log('[bridge-out]', s.trim().slice(0, 200));
      }
    });
  }, 120_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
  });

  test('tier A save → toast「配置已生效」 and no restart banner', async () => {
    // Save a hot-applicable setting (temperature) through the real bridge.
    // Use a value unlikely to collide with the copied user config, otherwise
    // the diff is empty and no toast fires (test-harness collision).
    await page.evaluate(() =>
      window.miqi.config.update({ agents: { defaults: { temperature: 0.42 } } }),
    );

    await expect(page.getByTestId('config-updated-toast')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('config-updated-toast')).toContainText('配置已生效');
    // Tier A must NOT raise the restart banner.
    await expect(page.locator('body')).not.toContainText('需要重启');
  });

  test('tier C save → restart banner with reason + warn toast', async () => {
    // Save a process-level setting (wsl_distro) — tier C.
    await page.evaluate(() =>
      window.miqi.config.update({ tools: { sandbox: { wsl_distro: 'Ubuntu-E2E-Test' } } }),
    );

    // Status bar shows「需要重启」with the reason.
    await expect(page.locator('body')).toContainText('需要重启', { timeout: 15_000 });
    await expect(page.locator('body')).toContainText('WSL 发行版');
    await expect(page.locator('body')).toContainText('立即重启');

    // Warn toast mentions restart requirement.
    await expect(page.getByTestId('config-updated-toast')).toContainText('需要重启后生效');
  });
});
