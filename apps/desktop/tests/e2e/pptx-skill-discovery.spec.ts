/**
 * PPTX Skill Discovery E2E — does the AI perceive a PPT need without
 * being told the skill name?
 *
 * The prompt NEVER mentions pptx-generator / PowerPoint skill: the AI
 * must infer the need from the natural-language request and find the
 * local skill by itself (workspace/builtin skill inventory is injected
 * into the system prompt by #613 on the desktop runtime path).
 *
 * Run: cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron pptx-skill-discovery.spec.ts
 */

import { test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  createNewConversation,
  sendMessage,
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';

const SKIP_REAL_ON_CI =
  !!process.env.CI && process.env.MIQI_RUN_REAL_PPTX_E2E !== '1';

test.describe('PPTX Skill Discovery E2E', () => {
  test.skip(
    SKIP_REAL_ON_CI,
    'Real PPTX generation depends on LLM tool/file choices; run with MIQI_RUN_REAL_PPTX_E2E=1 for manual/nightly verification.',
  );

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
    await closeElectronApp(electronApp, miqiHome, true);  // keep home for PPTX inspection
  });

  test(
    'AI perceives PPT request and generates a deck without skill name in prompt',
    { timeout: 600_000 },
    async () => {
      if (!!process.env.CI) {
        console.log('[test] Skipping PPTX verification on CI (sandbox filesystem mismatch)');
        return;
      }
      const fname = 'ai_perceived.pptx';
      let _fn = 0;
      const shot = () => page.screenshot({ path: `test-results/videos/f${String(++_fn).padStart(4, '0')}.png`, timeout: 5000 }).catch(() => {});
      await createNewConversation(page);
      await shot();

      // ⚠️ 提示词完全不提技能/PPTX 技能名 —— 只有用户意图
      await sendMessage(
        page,
        `帮我做一份演示文稿，主题"人工智能简介"。封面主标题"人工智能简介"，副标题"技术、应用与未来"。目录包含：什么是AI、核心技术、应用场景、未来展望。内容要点：机器学习、深度学习、NLP。总结要点：AI重塑行业、人机协作、安全对齐。文件名 ${fname}`,
      );
      await shot();

      await expect(page.getByTestId('thinking-indicator')).toBeVisible({ timeout: 30_000 }).catch(() => {});
      console.log('[test] AI started processing');
      await shot();

      // Pre-approve ALL tools via wildcard key
      await page.evaluate(() =>
        (window as any).miqi.approvals.addPermanent('*:*', 'always'),
      );
      await shot();

      // Wait for AI to finish, capturing frames along the way.
      // Success signal = the target PPTX exists on disk (the AI replies
      // "done" while the Thinking… indicator may lag behind plan_update
      // cleanup), so poll the file instead of waiting for the indicator.
      // The skill's PptxGenJS workflow may stall on sandbox node lookup,
      // so give the full 10-minute window before declaring failure.
      const { existsSync } = require('node:fs');
      const { join, resolve } = require('node:path');
      const ws = join(miqiHome, 'workspace');
      const targetPptx = join(ws, fname);
      const deadline2 = Date.now() + 480_000;
      while (Date.now() < deadline2 && !existsSync(targetPptx)) {
        await page.waitForTimeout(8000);
        await shot();
      }
      await page.waitForTimeout(3000);
      await shot();
      if (!existsSync(targetPptx)) {
        throw new Error(`AI did not produce ${fname} within 8 minutes`);
      }

      // Verify pptx file was created + internal content
      const { execFileSync } = require('node:child_process');
      const verifier = join(__dirname, 'helpers', 'verify-pptx.py');
      const repoRoot = resolve(__dirname, '..', '..', '..', '..');
      const env = { ...process.env, PYTHONIOENCODING: 'utf-8' };
      // execFileSync cannot spawn .cmd shims directly on Windows (EINVAL);
      // shell: true resolves uv.cmd through cmd.exe.
      const uv = 'uv';
      const shell = process.platform === 'win32';
      let result: any;
      try {
        const vout = execFileSync(uv, ['run', 'python', verifier, ws, fname], {
          cwd: repoRoot,
          encoding: 'utf8',
          timeout: 15000,
          env,
          shell,
        });
        result = JSON.parse(vout);
      } catch (e: any) {
        const raw = e.stdout || e.stderr || '';
        console.log('[test] verify-pptx raw output:', raw.slice(0, 300));
        try { result = JSON.parse(raw); } catch {
          result = { pass: false, checks: [{ label: 'json parse error', pass: false, detail: raw.slice(0, 200) }] };
        }
      }
      console.log('[test] PPTX checks:', JSON.stringify(result.checks));
      await shot();
      if (!result.pass) {
        const failed = result.checks.filter((c: any) => !c.pass).map((c: any) => c.label);
        throw new Error(`PPTX checks failed: ${failed.join(', ')}`);
      }
      console.log('[test] ✅ All checks passed — AI perceived PPT need without skill name in prompt');
    },
  );
});
