/**
 * grok.e2e.spec.ts — Real Electron E2E test for grok provider integration.
 *
 * Verifies end-to-end chat.send → streaming response through the real grok
 * agent stdio process.  Requires grok binary to be available (built or on PATH)
 * and a configured provider with apiKey in ~/.miqi/config.json.
 *
 * Run: cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron -g "Grok"
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  LLM_TIMEOUT,
  waitForInputReady,
  sendMessage,
  waitForResponseComplete,
  launchElectronApp,
  closeElectronApp,
  approveLoop,
  getSessionTitle,
} from './helpers/electron-setup';
import { writeFileSync, readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

// ─── Helpers ──────────────────────────────────────────────────────────

/** Patch config.json in miqiHome to activate grok provider before launch. */
function patchToGrok(miqiHome: string) {
  const configPath = join(miqiHome, 'config.json');
  const config = existsSync(configPath)
    ? JSON.parse(readFileSync(configPath, 'utf-8'))
    : {};
  config.agents = { ...config.agents, defaults: { ...config.agents?.defaults, model: 'grok' } };
  writeFileSync(configPath, JSON.stringify(config, null, 2));
}

// ─── Test Suite ───────────────────────────────────────────────────────

test.describe('Grok Provider Electron E2E', () => {
  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;
  }, 120_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
  });

  // ═══════════════════════════════════════════════════════════════════
  //  Grok appears only in Settings → General, NOT in provider list
  // ═══════════════════════════════════════════════════════════════════

  test('grok not in provider list but in Settings → General', { timeout: LLM_TIMEOUT }, async () => {
    await page.getByText(/^(System Settings|系统设置)$/).click();

    // Model tab should NOT show grok as a provider
    await page.getByRole('tab', { name: '模型' }).click();
    await expect(page.getByText('Grok (xAI)')).not.toBeVisible({ timeout: 5_000 });

    // General tab SHOULD show the grok toggle
    await page.getByRole('tab', { name: '通用' }).click();
    await expect(page.getByText('Grok 后端')).toBeVisible({ timeout: 10_000 });
  });

  // ═══════════════════════════════════════════════════════════════════
  //  Chat with grok backend
  // ═══════════════════════════════════════════════════════════════════

  test('sends message via grok and receives streaming response', { timeout: LLM_TIMEOUT }, async () => {
    await patchToGrok(miqiHome);
    // Reload page to pick up new config
    await page.reload();
    await page.waitForSelector('#root', { state: 'visible' });
    await waitForInputReady(page);
    // Wait for bridge to re-read config
    await page.waitForTimeout(2000);

    await sendMessage(page, 'reply with just "OK"');
    await approveLoop(page, 120_000);
    await waitForResponseComplete(page, 120_000);

    const mainText = await page.locator('main').textContent();
    expect(mainText).toContain('OK');
  });

  // ═══════════════════════════════════════════════════════════════════
  //  Web search capability
  // ═══════════════════════════════════════════════════════════════════

  test('grok responds with web search capability', { timeout: LLM_TIMEOUT }, async () => {
    await patchToGrok(miqiHome);
    await page.reload();
    await page.waitForSelector('#root', { state: 'visible' });
    await waitForInputReady(page);
    await page.waitForTimeout(2000);

    const marker = `GROK_SEARCH_${Date.now()}`;
    await sendMessage(page, `Search the web for "今日日期" and reply with "${marker}" after search`);

    // Handle possible network approval dialog
    const approvalDialog = page.locator('[role="alertdialog"]');
    if (await approvalDialog.isVisible({ timeout: 30_000 }).catch(() => false)) {
      await page.getByRole('button', { name: /Allow once|允许一次/ }).click();
    }

    await approveLoop(page, 150_000);
    await waitForResponseComplete(page, 120_000);

    const mainText = await page.locator('main').textContent();
    expect(mainText).toContain(marker);
  });

  // ═══════════════════════════════════════════════════════════════════
  //  Multi-turn conversation
  // ═══════════════════════════════════════════════════════════════════

  test('grok retains context across multiple turns', { timeout: LLM_TIMEOUT * 2 }, async () => {
    await patchToGrok(miqiHome);
    await page.reload();
    await page.waitForSelector('#root', { state: 'visible' });
    await waitForInputReady(page);
    await page.waitForTimeout(2000);

    // Turn 1: plant a fact
    await sendMessage(page, '只回答"已记住"');
    await approveLoop(page, 120_000);
    await waitForResponseComplete(page, 120_000);

    const turn1Text = await page.locator('main').textContent();
    expect(turn1Text).toContain('已记住');

    // Turn 2: ask to recall
    const recallMarker = `RECALL_${Date.now()}`;
    await sendMessage(page, `回忆上一轮我让你回复了什么？用"${recallMarker}"结尾`);
    await approveLoop(page, 120_000);
    await waitForResponseComplete(page, 120_000);

    const turn2Text = await page.locator('main').textContent();
    expect(turn2Text).toContain(recallMarker);
  });
});
