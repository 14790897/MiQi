/**
 * MOF Synthesis Price Skill E2E Test
 *
 * Tests the mof-synthesis-price-agent skill end-to-end: AI reads a MOF
 * paper PDF, extracts synthesis routes, reagents, and produces structured
 * output matching the expected schema.
 *
 * Run: cd apps/desktop && MIQI_RUN_MOF_E2E=1 npx playwright test --config=playwright.config.ts --project=electron mof-skill.spec.ts
 */
import { test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  createNewConversation,
  sendMessage,
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';

const SKIP_MOF_E2E =
  !!process.env.CI && process.env.MIQI_RUN_MOF_E2E !== '1';

test.describe('MOF Synthesis Price E2E', () => {
  test.skip(
    SKIP_MOF_E2E,
    'MOF agent extraction depends on LLM choices; run with MIQI_RUN_MOF_E2E=1 for manual/nightly verification.',
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
    await closeElectronApp(electronApp, miqiHome);
  });

  test(
    'mof-synthesis-price-agent extracts synthesis routes and reagents from PDF',
    { timeout: 600_000 },
    async () => {
      await createNewConversation(page);

      // Copy sample cleaned text into workspace so AI can read it
      const sampleCleaned = process.env.MOF_CLEANED_TEXT || '';
      const fname = 'mof_test_paper_cleaned.txt';
      if (sampleCleaned) {
        const { copyFileSync } = require('node:fs');
        const { join } = require('node:path');
        const ws = join(miqiHome, 'workspace');
        copyFileSync(sampleCleaned, join(ws, fname));
        console.log(`[test] Copied cleaned text: ${sampleCleaned} → ${join(ws, fname)}`);
      }

      const inputHint = sampleCleaned
        ? `已清洗文本文件: ${fname}`
        : '使用 DOI: 10.ki/2024.082';

      await sendMessage(
        page,
        `使用 /mof-synthesis-price-agent 技能处理这篇 MOF 论文。${inputHint}。只做 agent extraction 阶段：读取清洗后的论文文本（${fname}），从文本中提取合成路线（synthesis_routes）、试剂清单（reagents）和合成摘要（synthesis_summary），输出 agent_extraction.json 到 workspace。不要跑定价和报告阶段。`,
      );

      // Pre-approve ALL tools
      await page.evaluate(() =>
        (window as any).miqi.approvals.addPermanent('*:*', 'always'),
      );

      // Wait for AI to finish
      const _deadline = Date.now() + 300_000;
      while (Date.now() < _deadline) {
        const thinking = await page.getByText('Thinking…').isVisible().catch(() => false);
        if (!thinking) break;
        await page.waitForTimeout(8000);
      }
      await expect(page.getByText('Thinking…')).toBeHidden({ timeout: 300_000 });
      await page.waitForTimeout(3000);

      // Merge sandbox files back to host workspace (WSL sandbox mode)
      const mergeBtn = page.locator('button, [role="button"]').filter({ hasText: 'MERGE ALL CHANGES' });
      if (await mergeBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
        console.log('[test] Merging sandbox files to host workspace…');
        await mergeBtn.click();
        await page.waitForTimeout(5000);
        console.log('[test] Merge complete');
      }

      // Verify output
      const { execFileSync } = require('node:child_process');
      const { join, resolve } = require('node:path');
      const ws = join(miqiHome, 'workspace');
      const verifier = join(__dirname, 'helpers', 'verify-mof-output.py');
      const repoRoot = resolve(__dirname, '..', '..', '..', '..');

      // Use python from PATH (MiQi bundled or system)
      const python = process.platform === 'win32' ? 'python' : 'python3';
      const env = { ...process.env, PYTHONIOENCODING: 'utf-8' };

      let result: any;
      try {
        const vout = execFileSync(python, [verifier, ws], {
          cwd: repoRoot,
          encoding: 'utf8',
          timeout: 30000,
          env,
        });
        result = JSON.parse(vout);
      } catch (e: any) {
        const raw = e.stdout || e.stderr || '';
        console.log('[test] verify-mof-output raw output:', raw.slice(0, 500));
        try { result = JSON.parse(raw); } catch {
          result = { pass: false, checks: [{ label: 'json parse error', pass: false, detail: raw.slice(0, 200) }] };
        }
      }

      console.log('[test] MOF checks:', JSON.stringify(result.checks));
      if (!result.pass) {
        const failed = result.checks.filter((c: any) => !c.pass).map((c: any) => c.label);
        throw new Error(`MOF checks failed: ${failed.join(', ')}`);
      }
      console.log('[test] ✅ All MOF output checks passed');
    },
  );
});
