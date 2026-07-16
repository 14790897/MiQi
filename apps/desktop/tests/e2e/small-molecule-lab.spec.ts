/**
 * Small Molecule Lab Skill E2E Test
 *
 * Tests the small-molecule-lab skill end-to-end: AI runs a PySCF
 * calculation for H2O potential energy surface in fast mode and
 * produces result.json + PNG visualizations.
 *
 * Run: cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron -g "small-molecule-lab"
 */
import { test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  createNewConversation,
  sendMessage,
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';

test.describe('Small Molecule Lab E2E', () => {
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
    'small-molecule-lab calculates H2O potential energy surface in fast mode',
    { timeout: 600_000 },
    async () => {
      let _fn = 0;
      const shot = () =>
        page
          .screenshot({
            path: `test-results/videos/sml_f${String(++_fn).padStart(4, '0')}.png`,
            timeout: 5000,
          })
          .catch(() => {});

      await createNewConversation(page);
      await shot();

      await sendMessage(
        page,
        '使用 small-molecule-lab，帮我看看水分子的势能面，用快速模式。',
      );

      // Pre-approve ALL tools (skill runs scripts that need exec permission)
      await page.evaluate(() =>
        (window as any).miqi.approvals.addPermanent('*:*', 'always'),
      );
      await shot();

      // Wait for AI to finish — capture screenshots every 3s for smoother video
      const deadline = Date.now() + 300_000;
      while (Date.now() < deadline) {
        const thinking = await page
          .getByTestId('thinking-indicator')
          .isVisible()
          .catch(() => false);
        if (!thinking) break;
        await page.waitForTimeout(3000);
        await shot();
      }
      await expect(page.getByTestId('thinking-indicator')).toBeHidden({
        timeout: 300_000,
      });
      await shot();
      await page.waitForTimeout(3000);

      // Merge sandbox files back to host workspace (WSL sandbox mode).
      // The merge button may take a moment to appear after completion.
      const mergeBtn = page
        .locator('button, [role="button"]')
        .filter({ hasText: 'MERGE ALL CHANGES' })
        .or(
          page
            .locator('button, [role="button"]')
            .filter({ hasText: '合并所有更改' }),
        );
      if (await mergeBtn.isVisible({ timeout: 10_000 }).catch(() => false)) {
        console.log('[test] Merging sandbox files to host workspace…');
        await mergeBtn.click();
        // Wait longer for merge to complete — WSL rsync over many files
        await page.waitForTimeout(15_000);
        console.log('[test] Merge complete');
      } else {
        console.log('[test] No merge button visible — files may already be on host');
      }

      // ── Verification: check page content for expected outputs ──────────
      // The AI assistant should have produced visible results in the chat
      const mainText = await page.locator('main').textContent().catch(() => '');
      console.log('[test] main textContent (last 500 chars):', (mainText || '').slice(-500));

      const checks: { label: string; pass: boolean; detail: string }[] = [];

      // Check 1: AI produced output mentioning water molecule or PES
      const mentionsWater =
        (mainText || '').includes('水') ||
        (mainText || '').includes('H2O') ||
        (mainText || '').includes('H₂O');
      checks.push({
        label: 'Mentions water molecule',
        pass: mentionsWater,
        detail: mentionsWater ? 'found' : 'not found in main text',
      });

      // Check 2: Energy data present (eV, Hartree, or kcal/mol)
      const mentionsEnergy =
        (mainText || '').includes('eV') ||
        (mainText || '').includes('能量') ||
        (mainText || '').includes('E=') ||
        (mainText || '').includes('Hartree');
      checks.push({
        label: 'Shows energy data',
        pass: mentionsEnergy,
        detail: mentionsEnergy ? 'found' : 'not found in main text',
      });

      // Check 3: Output files mentioned (JSON, PNG, CSV, or HTML)
      const mentionsOutput =
        (mainText || '').includes('.json') ||
        (mainText || '').includes('.png') ||
        (mainText || '').includes('.html') ||
        (mainText || '').includes('.csv') ||
        (mainText || '').includes('PES') ||
        (mainText || '').includes('势能');
      checks.push({
        label: 'Output artifacts referenced',
        pass: mentionsOutput,
        detail: mentionsOutput ? 'found' : 'not found in main text',
      });

      // Check 4: No timeout or bridge error visible
      const hasBridgeError =
        (mainText || '').includes('运行时未启动') ||
        (mainText || '').includes('timed out') ||
        (mainText || '').includes('Bridge not running');
      checks.push({
        label: 'No bridge error in output',
        pass: !hasBridgeError,
        detail: hasBridgeError
          ? `Bridge error found: ${(mainText || '').slice(0, 200)}`
          : 'clean — no bridge errors',
      });

      // Also check workspace for generated files (sandbox may have merged)
      const { readdirSync, statSync } = require('node:fs');
      const { join } = require('node:path');
      const allFiles: string[] = [];
      function walk(dir: string, maxDepth = 5) {
        if (maxDepth <= 0) return;
        try {
          for (const entry of readdirSync(dir, { withFileTypes: true })) {
            const full = join(dir, entry.name);
            if (entry.isDirectory() && !entry.name.startsWith('.') && entry.name !== 'node_modules') {
              walk(full, maxDepth - 1);
            } else if (entry.isFile()) {
              allFiles.push(full.replace(/\\/g, '/'));
            }
          }
        } catch { /* skip inaccessible dirs */ }
      }
      walk(miqiHome);

      const pngFiles = allFiles.filter(f => f.endsWith('.png'));
      const jsonFiles = allFiles.filter(f => f.endsWith('.json'));
      const csvFiles = allFiles.filter(f => f.endsWith('.csv'));
      const htmlFiles = allFiles.filter(f => f.endsWith('.html'));
      const pyFiles = allFiles.filter(f => f.endsWith('.py'));
      console.log(
        `[test] Workspace files: ${pngFiles.length} PNG, ${jsonFiles.length} JSON, ` +
        `${csvFiles.length} CSV, ${htmlFiles.length} HTML, ${pyFiles.length} PY`,
      );

      const hasArtifacts =
        pngFiles.length > 0 || jsonFiles.length > 0 || csvFiles.length > 0 || htmlFiles.length > 0;
      checks.push({
        label: 'Workspace has generated artifacts',
        pass: hasArtifacts,
        detail: hasArtifacts
          ? `${pngFiles.length} PNG, ${jsonFiles.length} JSON, ${csvFiles.length} CSV, ${htmlFiles.length} HTML`
          : 'no artifacts found',
      });

      console.log('[test] Small Molecule Lab checks:', JSON.stringify(checks));
      const failed = checks.filter(c => !c.pass);
      if (failed.length > 0) {
        throw new Error(
          `Small Molecule Lab checks failed: ${failed.map(c => c.label).join(', ')}\n` +
          `Details: ${JSON.stringify(failed, null, 2)}`,
        );
      }
      console.log('[test] ✅ All Small Molecule Lab output checks passed');
    },
  );
});
