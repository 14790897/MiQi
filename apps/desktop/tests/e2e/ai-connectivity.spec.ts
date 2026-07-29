/**
 * AI Connectivity E2E Test
 *
 * Verifies that the MiQi Desktop app, when launched with a valid provider
 * configuration, can reach the configured AI model and produce a response.
 * If the AI is unreachable (no API key, wrong base URL, network failure,
 * provider down, etc.) this test FAILS — which causes the desktop-ci to
 * fail immediately, surfacing the configuration problem before any other
 * E2E steps run.
 *
 * Strategy: use the provider-level connectivity probe
 * (`window.miqi.providers.list` + `window.miqi.providers.test`) instead
 * of driving the chat UI.  This keeps the test fast and unambiguous —
 * it's not testing the chat flow, it's testing "can the app reach AI".
 *
 * Run: cd apps/desktop && npx playwright test \
 *   --config=playwright.config.ts --project=electron \
 *   -g "AI connectivity"
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  LLM_TIMEOUT,
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';

// Conservative timeout for the network round-trip — provider.test typically
// returns within a few seconds when credentials are valid, but can hang
// slightly longer on slow networks.  Two minutes is plenty.
const PROBE_TIMEOUT_MS = 120_000;

test.describe('AI Connectivity', () => {
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
    'AI provider is reachable — desktop CI fails if disconnected',
    { timeout: LLM_TIMEOUT },
    async () => {
      // Read the active provider from the bridge so we don't hard-code
      // assumptions about which provider CI uses.
      const probeResult = await page.evaluate(async () => {
        const timeoutMs = 120_000;
        const probe = async <T,>(fn: () => Promise<T>): Promise<T> => {
          return await Promise.race([
            fn(),
            new Promise<T>((_, reject) =>
              setTimeout(
                () => reject(new Error(`Bridge probe timed out after ${timeoutMs}ms`)),
                timeoutMs,
              ),
            ),
          ]);
        };

        try {
          const status = await probe(() => (window as any).miqi.runtime.status());
          const listed = await probe(() => (window as any).miqi.providers.list());

          const providers = (listed?.providers ?? []) as Array<{
            name: string;
            configured: boolean;
            configured_model?: string;
            api_base?: string | null;
            verification_status?: string;
            verification_message?: string | null;
          }>;

          const configured = providers.filter((p) => p.configured);
          if (configured.length === 0) {
            return {
              ok: false,
              stage: 'list',
              error: 'No configured providers found in ~/.miqi/config.json',
              runtimeState: status?.state ?? null,
              runtimeInitialized: !!status?.initialized,
              activeProvider: listed?.active_provider ?? null,
              activeModel: listed?.active_model ?? null,
              providers,
            };
          }

          const target =
            configured.find((p) => p.name === listed?.active_provider) ?? configured[0];
          const model = target.configured_model ?? listed?.active_model;

          const probeResp = await probe(() =>
            (window as any).miqi.providers.test(target.name, undefined, undefined, model),
          );

          return {
            ok: !!probeResp?.ok,
            stage: 'test',
            runtimeState: status?.state ?? null,
            runtimeInitialized: !!status?.initialized,
            activeProvider: target.name,
            activeModel: probeResp?.model ?? model ?? null,
            providers,
            probeResponse: probeResp,
          };
        } catch (e: any) {
          return {
            ok: false,
            stage: 'exception',
            error: e?.message ?? String(e),
            runtimeState: null,
            runtimeInitialized: false,
            activeProvider: null,
            activeModel: null,
            providers: [] as any[],
          };
        }
      });

      console.log('[ai-connectivity] probe result:', JSON.stringify(probeResult, null, 2));

      if (!probeResult.ok) {
        const where = probeResult.stage ?? 'unknown';
        const detail =
          probeResult.error ??
          probeResult.probeResponse?.error ??
          `provider="${probeResult.activeProvider}", model="${probeResult.activeModel}"`;
        throw new Error(
          `AI connectivity check failed (stage=${where}): ${detail}. ` +
            `Check DEEEPSEEK_API_KEY / DEEEPSEEK_API_BASE / BRAVE_API_KEY ` +
            `secrets and that providers.list returns configured providers.`,
        );
      }

      expect(probeResult.activeProvider).toBeTruthy();
      expect(probeResult.activeModel).toBeTruthy();
      // Trust the bridge verdict over a UI selector — providers.test returns
      // ok:false for any failure mode (auth, network, model not found, ...).
      expect(probeResult.probeResponse?.ok).toBe(true);
      console.log(
        `[ai-connectivity] ✅ ${probeResult.activeProvider} / ${probeResult.activeModel} reachable in ${PROBE_TIMEOUT_MS}ms budget`,
      );
    },
  );
});
