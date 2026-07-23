/**
 * grok.e2e.spec.ts — Real Electron E2E test for grok provider integration.
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  LLM_TIMEOUT, waitForInputReady, sendMessage, waitForResponseComplete,
  launchElectronApp, closeElectronApp, approveLoop,
} from './helpers/electron-setup';
import { writeFileSync, readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const RUNTIME_ERROR_SIGNATURES = [
  'Bridge not running', 'No configured provider found', 'Grok process exited',
  'Grok did not produce', 'Failed to start grok', '运行时未启动', 'Still waiting for backend',
];

function patchToGrok(miqiHome: string) {
  const configPath = join(miqiHome, 'config.json');
  if (!existsSync(configPath)) return;
  const config = JSON.parse(readFileSync(configPath, 'utf-8'));
  config.desktop = { ...config.desktop, useGrokBackend: true };
  writeFileSync(configPath, JSON.stringify(config, null, 2));
}

function ensureProviderModel(miqiHome: string, modelId: string) {
  const configPath = join(miqiHome, 'config.json');
  if (!existsSync(configPath)) return;
  const config = JSON.parse(readFileSync(configPath, 'utf-8'));
  for (const [_name, entry] of Object.entries(config.providers ?? {})) {
    const e = entry as Record<string, unknown>;
    if (e['apiKey']) { e['model'] = e['model'] || modelId; break; }
  }
  writeFileSync(configPath, JSON.stringify(config, null, 2));
}

async function expectGrokBackendActive(page: Page) {
  const config = await page.evaluate(() => (window as any).miqi.config.get());
  expect(config?.desktop?.useGrokBackend).toBe(true);
}

async function waitForGrokReady(page: Page, timeoutMs = 60_000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const status = await page.evaluate(async () => {
        // @ts-ignore
        return await window.miqi.runtime.grokStatus();
      }) as any;
      if (status?.state === 'running') {
        console.log('[test] grok status:', JSON.stringify(status));
        return true;
      }
      await page.waitForTimeout(500);
    } catch { await page.waitForTimeout(500); }
  }
  // Dump final state on failure
  try {
    const status = await page.evaluate(async () => {
      // @ts-ignore
      return await window.miqi.runtime.grokStatus();
    }) as any;
    console.log('[test] grok FAILED state:', JSON.stringify(status));
  } catch {}
  return false;
}

async function expectNoRuntimeError(page: Page, description: string) {
  const mainText = (await page.locator('main').textContent()) ?? '';
  for (const sig of RUNTIME_ERROR_SIGNATURES) {
    if (mainText.includes(sig)) throw new Error(`[${description}] Runtime error: "${sig}"`);
  }
}

async function relaunchWithGrok(app: ElectronApplication, miqiHome: string) {
  await closeElectronApp(app);
  const fixture = await launchElectronApp({ desktop: { useGrokBackend: true }, providers: { deepseek: { model: 'deepseek-v4-pro' }, siliconflow: { model: 'deepseek-v4-pro' } } });

  await fixture.page.reload();
  await fixture.page.waitForSelector('#root', { state: 'visible', timeout: 30_000 });
  await waitForInputReady(fixture.page);
  await fixture.page.waitForTimeout(5000);
  return fixture;
}

test.describe('Grok Provider Electron E2E', () => {
  let electronApp: ElectronApplication, page: Page, miqiHome: string;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp({ desktop: { useGrokBackend: true } });
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;
  }, 120_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
  });

  test('grok NOT in provider list, only in Settings → General', { timeout: LLM_TIMEOUT }, async () => {
    await page.getByText(/^(System Settings|系统设置)$/).click();
    await page.getByRole('tab', { name: '模型' }).click();
    await expect(page.getByText('Grok (xAI)')).not.toBeVisible({ timeout: 5_000 });
    await page.getByRole('tab', { name: '通用' }).click();
    await expect(page.getByText('Grok 后端')).toBeVisible({ timeout: 10_000 });
  });

  test('simple streaming response', { timeout: LLM_TIMEOUT }, async () => {
    const r = await relaunchWithGrok(electronApp, miqiHome);
    electronApp = r.electronApp;
    page = r.page;
    miqiHome = r.miqiHome;

    await page.evaluate(() => (window as any).miqi.approvals.addPermanent('*:*', 'always'));

    // Verify grok responds to a simple message (no runtime error)
    const marker = 'testing-grok-streaming';
    await sendMessage(page, `say hello in one word, then put "${marker}" on the last line`);
    await approveLoop(page, 120_000);
    await waitForResponseComplete(page, 120_000);
    await expectNoRuntimeError(page, 'streaming');
    const mt = await page.locator('main').textContent();
    expect(mt).toContain(marker);
  });

  test('web search capability', { timeout: LLM_TIMEOUT }, async () => {
    const r = await relaunchWithGrok(electronApp, miqiHome);
    electronApp = r.electronApp;
    page = r.page;
    miqiHome = r.miqiHome;
    await expectGrokBackendActive(page);
    const marker = 'GROK_SEARCH_' + Date.now();
    await sendMessage(page, 'Search the web for "今日日期" and reply with "' + marker + '" after search');
    await approveLoop(page, 150_000);
    await waitForResponseComplete(page, 120_000);
    await expectNoRuntimeError(page, 'web search');
    const mt = await page.locator('main').textContent();
    expect(mt).toContain(marker);
  });
});
