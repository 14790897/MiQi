/**
 * Workspace-cleanup Skill Discovery E2E — does the AI perceive a cleanup
 * need and follow the skill's directory spec without being told the name?
 *
 * The prompt NEVER mentions workspace-cleanup / skill names. The skill's
 * value is its unique artifacts/... directory structure (artifacts/reports,
 * artifacts/scripts, archive/YYYY-MM) — the model could NOT know this
 * layout from training priors. If the AI moves files into that structure,
 * it must have discovered the skill via the injected inventory (#613)
 * and read its SKILL.md.
 *
 * Run: cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron workspace-cleanup-skill-discovery.spec.ts
 */

import { test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import { mkdirSync, writeFileSync, readdirSync, existsSync, statSync } from 'node:fs';
import { join } from 'node:path';
import {
  createNewConversation,
  sendMessage,
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';

const SKIP_REAL_ON_CI =
  !!process.env.CI && process.env.MIQI_RUN_REAL_PPTX_E2E !== '1';

test.describe('Workspace-cleanup Skill Discovery E2E', () => {
  test.skip(
    SKIP_REAL_ON_CI,
    'Real cleanup depends on LLM tool choices; run with MIQI_RUN_REAL_PPTX_E2E=1 for manual/nightly verification.',
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
    await closeElectronApp(electronApp, miqiHome, true);  // keep home for log inspection
  });

  test(
    'AI perceives cleanup need and follows the skill directory spec',
    { timeout: 600_000 },
    async () => {
      if (!!process.env.CI) {
        console.log('[test] Skipping workspace verification on CI (sandbox filesystem mismatch)');
        return;
      }
      const ws = join(miqiHome, 'workspace');
      let _fn = 0;
      const shot = () => page.screenshot({ path: `test-results/videos/f${String(++_fn).padStart(4, '0')}.png`, timeout: 5000 }).catch(() => {});

      // ── Seed loose files BEFORE launching the conversation ──────────
      // A .md report and a .py script in the workspace root. The skill's
      // spec moves .md -> artifacts/reports/ and .py -> artifacts/scripts/.
      writeFileSync(join(ws, 'report.md'), '# 月报\n本月总结。\n');
      writeFileSync(join(ws, 'helper.py'), '#!/usr/bin/env python\nprint("hello")\n');
      console.log('[test] seeded report.md + helper.py in workspace root');

      await createNewConversation(page);
      await shot();

      // ⚠️ 提示词完全不提技能名 —— 只有用户意图
      await sendMessage(
        page,
        `我工作目录里有点乱，帮我整理一下。有一个 report.md 和一个 helper.py 放乱了，帮我归类到合适的地方。`,
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

      // Wait for AI to finish, capturing frames along the way
      const deadline = Date.now() + 300_000;
      while (Date.now() < deadline) {
        const thinking = await page.getByTestId('thinking-indicator').isVisible().catch(() => false);
        if (!thinking) break;
        await page.waitForTimeout(8000);
        await shot();
      }
      await expect(page.getByTestId('thinking-indicator')).toBeHidden({ timeout: 300_000 });
      await shot();

      // ── Verify the skill's directory spec was followed ─────────────
      const failReasons: string[] = [];
      const hasArtifactsReports = existsSync(join(ws, 'artifacts', 'reports', 'report.md'));
      const hasArtifactsScripts = existsSync(join(ws, 'artifacts', 'scripts', 'helper.py'));
      const rootStillHas = existsSync(join(ws, 'report.md')) || existsSync(join(ws, 'helper.py'));
      console.log('[test] artifacts/reports/report.md:', hasArtifactsReports);
      console.log('[test] artifacts/scripts/helper.py:', hasArtifactsScripts);
      console.log('[test] loose files still in root:', rootStillHas);
      if (!hasArtifactsReports) failReasons.push('report.md NOT in artifacts/reports/');
      if (!hasArtifactsScripts) failReasons.push('helper.py NOT in artifacts/scripts/');
      if (rootStillHas) failReasons.push('loose files still in workspace root');
      // Also confirm the files were moved, not deleted
      const movedBoth = hasArtifactsReports && hasArtifactsScripts;
      if (movedBoth && rootStillHas) failReasons.push('files both in target AND root');

      const mainText = await page.locator('main').textContent();
      const aiMentionsArtifacts = (mainText || '').includes('artifacts');
      console.log('[test] AI reply mentions artifacts/:', aiMentionsArtifacts);
      console.log('[test] AI reply (last 500):', (mainText || '').slice(-500).replace(/\s+/g, ' '));
      await shot();

      if (failReasons.length > 0) {
        throw new Error('Skill discovery failed: ' + failReasons.join('; '));
      }
      console.log('[test] ✅ All checks passed — AI perceived cleanup need and followed the skill directory spec');
    },
  );
});
