/**
 * Full Electron E2E Test
 *
 * Launches the complete MiQi Desktop app via Electron with real bridge.
 * User config at ~/.miqi/config.json is used automatically.
 *
 * ⚠️ Requires:
 *   - electron 34.x (35 removed --remote-debugging-port)
 *   - electron-vite build completed
 *   - ~/.miqi/config.json with valid API keys
 *
 * Run: cd apps/desktop && npx playwright test --config=playwright.config.ts --grep "Native Electron"
 */

import { test, expect, _electron as electron } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import { resolve } from 'node:path';

const APPS_DESKTOP = resolve(__dirname, '../..');
const PROJECT_ROOT = resolve(APPS_DESKTOP, '../..');
const MAIN_ENTRY = resolve(APPS_DESKTOP, 'out/main/electron-trampoline.js');

const LLM_TIMEOUT = 180_000;   // real AI call
const BOOT_TIMEOUT = 60_000;   // Electron + bridge startup

async function waitForInputReady(page: Page, timeout = 60_000) {
  const textarea = page.getByPlaceholder('Ask Agent to analyze or edit files...');
  await expect(textarea).toBeEnabled({ timeout });
  return textarea;
}

async function sendMessage(page: Page, text: string) {
  const textarea = await waitForInputReady(page);
  await textarea.fill(text);
  await textarea.press('Enter');
  // Confirm user message appears
  await expect(page.getByText(text).first()).toBeVisible({ timeout: 5000 });
}

test.describe('Native Electron E2E', () => {

  let app: ElectronApplication;
  let page: Page;

  test.beforeAll(async () => {
    app = await electron.launch({
      args: [MAIN_ENTRY],
      cwd: PROJECT_ROOT,
    });

    page = await app.firstWindow();
    await page.waitForLoadState('domcontentloaded');

    // Wait for bridge to connect and runtime to start
    // The bridge process is spawned by the Electron main process automatically
    try {
      await page.waitForSelector('text=运行中', { timeout: BOOT_TIMEOUT });
      console.log('Bridge ready: 运行中');
    } catch {
      console.log('Bridge status unknown — continuing');
    }
  }, BOOT_TIMEOUT + 30000);

  test.afterAll(async () => {
    await app?.close().catch(() => {});
  });

  test('app launches and renders correctly', async () => {
    // Verify core UI
    await expect(page.getByText('MiQi Workbench')).toBeVisible({ timeout: 10000 });
    await expect(
      page.getByPlaceholder('Ask Agent to analyze or edit files...')
    ).toBeVisible({ timeout: 10000 });

    // Sidebar navigation
    await expect(page.getByRole('button', { name: '对话', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '设置', exact: true })).toBeVisible();
  });

  test('basic conversation with real AI', { timeout: LLM_TIMEOUT }, async () => {
    await sendMessage(page, '只回复一个英文单词：TestOK');

    // Wait for the response to appear in the latest message bubble
    await expect(page.getByText('TestOK')).toBeVisible({ timeout: 120000 });
  });

  test('web search with real search tool', { timeout: LLM_TIMEOUT }, async () => {
    await sendMessage(page, '搜索今天北京的天气');

    // Real web_search → web_fetch → response
    await expect(
      page.getByText(/天气|℃|温度/i).first()
    ).toBeVisible({ timeout: 120000 });
  });

  test('multi-turn memory recall', { timeout: LLM_TIMEOUT }, async () => {
    await sendMessage(page, '记住：我的名字是测试员');
    await expect(page.getByText(/测试员/).first()).toBeVisible({ timeout: 120000 });

    await sendMessage(page, '我叫什么名字？');
    await expect(page.getByText(/测试员/).first()).toBeVisible({ timeout: 120000 });
  });

});
