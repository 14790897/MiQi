/**
 * No-Sandbox Host Exec E2E
 *
 * Regression coverage for #792 (PR #793): with the sandbox disabled,
 * the legacy orchestrator path (chat.send → TaskRunner →
 * SandboxPolicyEngine) used to select RESTRICTED + BLOCK_ALL network
 * policy for exec, so EVERY command was rejected with
 * "RESTRICTED 沙箱无法强制网络隔离…命令未执行" — blocking tasks that
 * needed network (e.g. the Qraft upload script hitting
 * test.forge.miqroera.com).
 *
 * After the fix, exec with no sandbox available selects NONE and runs
 * directly on the host without restrictions (network, cwd and path
 * checks all bypassed — the user runs without isolation by choice).
 *
 * The spec drives the real chat flow with the sandbox disabled via
 * patchConfig, asks the agent to run a marker command, and asserts the
 * user-visible outcome: the marker appears in the reply and the old
 * fail-closed block message does not.
 *
 * Run:
 *   cd apps/desktop
 *   npx playwright test --config=playwright.config.ts --project=electron no-sandbox-exec.spec.ts
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  LLM_TIMEOUT,
  waitForBridgeInitialized,
  sendMessage,
  waitForResponseComplete,
  approveLoop,
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';

test.describe('No-Sandbox Host Exec E2E', () => {
  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp((config) => {
      // Deterministic no-sandbox path: exec resolves to RESTRICTED host
      // execution through SandboxPolicyEngine (bwrap_available=False).
      config.tools = {
        ...config.tools,
        sandbox: { ...config.tools?.sandbox, enabled: false },
      };
    });
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;

    await waitForBridgeInitialized(page);
  }, 180_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
  });

  test(
    'exec runs on host when sandbox is disabled (no RESTRICTED network block)',
    { timeout: LLM_TIMEOUT },
    async () => {
      const marker = `NO_SANDBOX_EXEC_OK_${Date.now()}`;

      // Marker echo proves the command actually started; the networked
      // curl mirrors the original #792 scenario (upload scripts need
      // network).  Pre-fix the whole line was rejected before running.
      const prompt =
        `必须使用 exec 工具执行下面这条命令，然后只回复命令的完整输出，` +
        `不要解释、不要改写：` +
        `echo ${marker} && curl -sI --max-time 10 example.com`;

      await sendMessage(page, prompt);
      await approveLoop(page, LLM_TIMEOUT);
      await waitForResponseComplete(page, LLM_TIMEOUT);

      const text = (await page.locator('main').textContent()) ?? '';

      // User-visible outcome: the command actually ran on the host.
      expect(text).toContain(marker);
      // The old fail-closed block must not appear in the reply.
      expect(text).not.toContain('无法强制网络隔离');
      expect(text).not.toContain('命令未执行');

      await page.screenshot({
        path: `test-results/${test.info().title.replace(/\s+/g, '-')}.png`,
        fullPage: true,
      });
    },
  );
});
