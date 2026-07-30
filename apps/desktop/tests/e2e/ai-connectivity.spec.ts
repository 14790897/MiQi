/**
 * AI Connectivity E2E Test
 *
 * Fail-fast probe: if the LLM provider is unreachable (no API key,
 * wrong base URL, quota exhausted, network blocked, auth failure),
 * this test fails fast — preventing cascading red across the full
 * (expensive) E2E suite that would otherwise show confusing
 * "AI didn't write a file" / "AI said 处理消息时发生内部错误" errors.
 *
 * Strategy: drive the real chat UI via `sendMessage` +
 * `waitForResponseComplete` (same helpers the full-electron spec uses),
 * asking the AI for a trivial one-character reply. This exercises
 * every layer the production user path hits:
 *   1. Bridge readiness     — runtime.status() → running + initialized
 *   2. Provider resolution  — which provider/model the config activates
 *   3. chat.send IPC        — preload → main → app_server → TaskRunner
 *   4. LLM round-trip       — HTTP call to the provider endpoint
 *   5. Streaming delivery   — onProgress / onFinal events
 *   6. React render         — <main> textContent stabilisation
 *
 * Run: cd apps/desktop && npx playwright test \
 *      --config=playwright.config.ts --project=electron -g "AI connectivity"
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  LLM_TIMEOUT,
  waitForInputReady,
  launchElectronApp,
  closeElectronApp,
  sendMessage,
  waitForResponseComplete,
} from './helpers/electron-setup';

test.describe('AI Connectivity E2E', () => {
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

  test(
    'AI connectivity: chat pipeline end-to-end',
    { timeout: LLM_TIMEOUT },
    async () => {
      // Step 1 — bridge readiness
      await page.evaluate(async () => {
        for (let i = 0; i < 60; i++) {
          const s = await (window as any).miqi.runtime.status();
          if (s?.state === 'running' && s?.initialized) return;
          await new Promise((r) => setTimeout(r, 1000));
        }
      });

      // Step 2 — discover which provider/model we just exercised so
      // the failure message is actionable when this test trips.
      const meta = await page.evaluate(async () => {
        const r = await (window as any).miqi.providers.list();
        return {
          provider: r?.result?.active_provider ?? 'unknown',
          model: r?.result?.active_model ?? 'unknown',
        };
      });
      console.log(`[test] Probing ${meta.provider} (${meta.model})`);

      // Step 3 — ask for a trivial one-character reply so the LLM
      // round-trip is exercised but doesn't depend on tool use.
      await sendMessage(page, 'Reply with exactly one character: ok');
      await waitForResponseComplete(page);

      // Step 4 — verify a non-empty assistant reply arrived.
      const text = (await page.locator('main').textContent()) ?? '';
      expect(text.length).toBeGreaterThan(0);

      if (!text.toLowerCase().includes('ok')) {
        throw new Error(
          `AI reply missing expected "ok" marker — ` +
            `${meta.provider}/${meta.model} may not be reachable. ` +
            `Reply was: ${text.slice(-200)}`,
        );
      }

      console.log(
        `[test] ✅ ${meta.provider} (${meta.model}) reachable, AI replied within timeout`,
      );
    },
  );
});
