/**
 * MOF-5 Qraft Upload E2E — real user scenario, sandbox OFF.
 *
 * Full acceptance test of the no-sandbox exec chain (#793 NONE policy,
 * #796 accurate environment description, #801 Git Bash exec): run the
 * real user task — 生成 MOF-5 市场合成价格报告并确认执行，使用
 * qraft-workflowspec-export 技能上传到 forge — with the sandbox
 * disabled, and assert the upload succeeds from the AI's user-visible
 * reply.
 *
 * The spec points the app at the user's REAL workspace
 * (C:\Users\Intership003\.miqi\workspace): the qraft token lives in
 * .qraft/token.json there, and the e2e temp home would have neither
 * token nor prior artifacts.  The qraft-workflowspec-export skill
 * itself ships with the app under miqi/skills/.
 *
 * Windows-only: the workspace path and Git Bash exec are Windows
 * specifics (CI electron-e2e/macos-e2e skip it, like bwrap-dependent
 * specs do).
 *
 * Prerequisites:
 *   - Windows with Git Bash installed (or Git for Windows)
 *   - A VALID Qraft login in the real workspace (`.qraft/token.json`) —
 *     an expired token fails the upload step with NOT_LOGGED_IN, which
 *     is the expected failure mode and surfaces in the AI reply (the
 *     exec chain itself is already proven by that point: report
 *     generation, skill loading, script execution all use Git Bash).
 *
 * Run:
 *   cd apps/desktop
 *   npx playwright test --config=playwright.config.ts --project=electron mof5-qraft-upload.spec.ts
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  LLM_TIMEOUT,
  sendMessage,
  waitForResponseComplete,
  launchElectronApp,
  closeElectronApp,
  createNewConversation,
} from './helpers/electron-setup';

const REAL_WORKSPACE = 'C:\\Users\\Intership003\\.miqi\\workspace';

test.describe('MOF-5 Qraft Upload E2E', () => {
  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;

  test.beforeAll(async () => {
    test.skip(process.platform !== 'win32', 'Windows-only real-scenario spec');

    const fixture = await launchElectronApp((config) => {
      // Sandbox OFF — this is the whole point of the regression suite.
      config.tools = {
        ...config.tools,
        sandbox: { ...config.tools?.sandbox, enabled: false },
      };
      // Real workspace: qraft token + existing MOF-5 session artifacts.
      config.agents = {
        ...config.agents,
        defaults: { ...config.agents?.defaults, workspace: REAL_WORKSPACE },
      };
    });
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;
  }, 180_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
  });

  test(
    'MOF-5 price report generation + qraft-workflowspec-export upload succeeds without sandbox',
    { timeout: 45 * 60_000 },
    async () => {
      test.setTimeout(45 * 60_000);

      await createNewConversation(page);

      const prompt =
        '帮我生成 MOF-5 市场合成价格报告并确认执行，' +
        '使用 qraft-workflowspec-export 技能上传到 forge';

      await sendMessage(page, prompt);

      // The skill flow requires user confirmations (方案清单、上传确认)
      // via ask_user_confirm_card — auto-confirm them while waiting for
      // the final user-visible outcome: a successful upload.  The deadline
      // is activity-driven: deep-thinking models can spend many minutes
      // reasoning before the first tool call, so keep extending it while
      // the UI keeps changing (streaming/tool results), capped at MAX_WAIT.
      const MAX_WAIT = 40 * 60_000;
      const IDLE_EXTEND = 40_000;
      let deadline = Date.now() + MAX_WAIT;
      let text = '';
      let lastText = '';
      let lastChange = Date.now();
      while (Date.now() < deadline) {
        for (const name of ['确认上传', '确认执行', '确认', '继续执行']) {
          const btn = page.getByRole('button', { name, exact: false });
          if (await btn.isVisible({ timeout: 300 }).catch(() => false)) {
            await btn.click();
            console.log(`[test] Auto-confirmed card: ${name}`);
            lastChange = Date.now();
            break;
          }
        }
        text = (await page.locator('main').textContent()) ?? '';
        if (/上传成功|HTTP\s*200/.test(text)) break;
        if (text !== lastText) {
          lastText = text;
          lastChange = Date.now();
        } else if (Date.now() - lastChange > IDLE_EXTEND) {
          // Quiet for a long stretch (long model thinking): extend the
          // deadline once so slow reasoning doesn't fail the run.
          deadline = Math.min(deadline + IDLE_EXTEND, Date.now() + MAX_WAIT);
          lastChange = Date.now();
        }
        await page.waitForTimeout(1500);
      }

      // User-visible outcome: the platform upload succeeded.
      expect(text).toMatch(/上传成功|HTTP\s*200/);

      await waitForResponseComplete(page, LLM_TIMEOUT);
      text = (await page.locator('main').textContent()) ?? '';
      expect(text).toMatch(/上传成功|HTTP\s*200/);

      await page.screenshot({
        path: `test-results/${test.info().title.replace(/\s+/g, '-')}.png`,
        fullPage: true,
      });
    },
  );
});
