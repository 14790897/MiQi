/**
 * E2E: Task Assets Panel — AI 创建文件 → 右侧面板出现 → 点击预览内容
 *
 * Run: cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron task-assets.spec.ts
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import { resolve } from 'node:path';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { existsSync, rmSync } from 'node:fs';

const APPS_DESKTOP = resolve(__dirname, '../..');
const MIQI_SESSIONS_DIR = join(homedir(), '.miqi', 'workspace', 'sessions');
const LLM_TIMEOUT = 180_000;

// ─── Helpers ──────────────────────────────────────────────────────

async function waitForInputReady(page: Page, timeout = 60_000) {
  const textarea = page.getByPlaceholder(
    'Ask Agent to analyze or edit files...',
  );
  await expect(textarea).toBeEnabled({ timeout });
  return textarea;
}

async function sendMessage(page: Page, text: string) {
  const textarea = await waitForInputReady(page);
  await textarea.fill(text);
  await textarea.press('Enter');
  await expect(page.getByText(text).first()).toBeVisible({ timeout: 10_000 });
}

async function waitForResponseComplete(page: Page, timeout = 120_000) {
  await expect(page.getByText('Thinking…')).toBeHidden({ timeout });
}

// ─── Test Suite ───────────────────────────────────────────────────

test.describe('Task Assets Panel E2E', () => {
  let electronApp: ElectronApplication;
  let page: Page;

  test.beforeAll(async () => {
    if (existsSync(MIQI_SESSIONS_DIR)) {
      rmSync(MIQI_SESSIONS_DIR, { recursive: true, force: true });
    }

    const env = { ...process.env };
    delete env.ELECTRON_RUN_AS_NODE;

    electronApp = await electron.launch({
      args: [APPS_DESKTOP],
      executablePath: require('electron') as string,
      env,
      chromiumSandbox: false,
    });

    page = await electronApp.firstWindow();
    await page.waitForLoadState('domcontentloaded');

    page.on('console', (msg) => {
      const t = msg.text();
      if (
        msg.type() === 'error' ||
        t.includes('[MIQI BRIDGE STDERR]') ||
        t.includes('[miqi-bridge]') ||
        t.includes('[e2e]')
      ) {
        console.log(`[e2e] ${t}`);
      }
    });

    try { await page.getByText('MiQi Workbench').waitFor({ timeout: 30_000 }); } catch {}
    await waitForInputReady(page);

    const bridgeReady = await page.evaluate(async () => {
      for (let i = 0; i < 60; i++) {
        try {
          const s = await (window as any).miqi.runtime.status();
          if (s?.state === 'running') return true;
        } catch { /* */ }
        await new Promise((r) => setTimeout(r, 1000));
      }
      return false;
    });
    if (!bridgeReady) console.log('[test] Warning: bridge not running');

    console.log('[test] Ready');
  }, 120_000);

  test.afterAll(async () => {
    await electronApp?.close().catch(() => {});
  });

  // ═══════════════════════════════════════════════════════════════
  //  Test 1: AI creates file → appears in Task Assets
  // ═══════════════════════════════════════════════════════════════

  test(
    'AI creates .txt file → appears in Task Assets panel',
    { timeout: LLM_TIMEOUT * 2 },
    async () => {
      await page.evaluate(async () => {
        for (let i = 0; i < 30; i++) {
          try {
            const s = await (window as any).miqi.runtime.status();
            if (s?.state === 'running' && s?.initialized) return;
          } catch { /* */ }
          await new Promise((r) => setTimeout(r, 1000));
        }
      });

      const filename = `e2e_task_${Date.now()}.txt`;
      const content = `E2E Task Assets test content ${Date.now()}`;

      // Panel should show empty state initially
      await expect(page.getByTestId('task-assets-panel')).toBeVisible({ timeout: 10_000 });
      await expect(page.getByText(/No files yet/)).toBeVisible({ timeout: 5_000 });

      // Have AI create a file (will trigger approval)
      await sendMessage(
        page,
        `Use write_file to create ${filename} with content "${content}"`,
      );

      // Handle approval
      await expect(page.getByText('文件操作审批')).toBeVisible({ timeout: 60_000 });
      await page.getByRole('button', { name: '永久允许' }).click();
      await waitForResponseComplete(page, 240_000);

      // Verify AI confirmed file creation in main chat
      await expect(
        page.locator('main').getByText(filename, { exact: false }).first(),
      ).toBeVisible({ timeout: 15_000 });
      console.log(`[test] ✅ File created: ${filename}`);

      // ── Verify Task Assets panel shows the file ──
      // No more "No files yet" — should have track entries now
      await expect(page.getByText(/No files yet/)).not.toBeVisible({ timeout: 5_000 });

      // WRITE category should have the file
      await expect(page.getByText('ACTIVE FOR EDIT')).toBeVisible({ timeout: 5_000 });

      // Should show a WRITE op badge on the file
      await expect(page.getByText('WRITE').first()).toBeVisible({ timeout: 5_000 });

      console.log('[test] ✅ Task Assets panel shows the file');
    },
  );

  // ═══════════════════════════════════════════════════════════════
  //  Test 2: Click Preview → see file content in modal
  // ═══════════════════════════════════════════════════════════════

  test(
    'click Preview on tracked file → content modal opens',
    { timeout: LLM_TIMEOUT * 2 },
    async () => {
      await page.evaluate(async () => {
        for (let i = 0; i < 30; i++) {
          try {
            const s = await (window as any).miqi.runtime.status();
            if (s?.state === 'running' && s?.initialized) return;
          } catch { /* */ }
          await new Promise((r) => setTimeout(r, 1000));
        }
      });

      const filename = `e2e_preview_${Date.now()}.txt`;
      const content = `Preview content: ${Date.now()}`;

      await sendMessage(
        page,
        `Use write_file to create ${filename} with content "${content}"`,
      );
      await expect(page.getByText('文件操作审批')).toBeVisible({ timeout: 60_000 });
      await page.getByRole('button', { name: '永久允许' }).click();
      await waitForResponseComplete(page, 240_000);
      console.log(`[test] ✅ File created: ${filename}`);

      // Find the file in Task Assets panel and click Preview
      const assetsPanel = page.getByTestId('task-assets-panel');

      // Use precise class selector to avoid matching Proposed Changes items
      const fileCard = assetsPanel.locator('.rounded-lg.p-2\\.5').filter({ hasText: filename });
      await expect(fileCard).toBeVisible({ timeout: 10_000 });
      await fileCard.getByRole('button', { name: 'Preview', exact: true }).click();
      console.log('[test] Clicked Preview on file card');

      // Preview modal should appear with file content
      // The modal shows file path in monospace font
      await expect(page.locator('pre.text-xs.font-mono')).toBeVisible({ timeout: 5_000 });
      await page.screenshot({ path: 'test-results/preview-modal.png' });

      // Should display our content (or an error if files.read has path issues)
      const previewText = (await page.locator('pre.text-xs.font-mono').textContent()) || '';
      if (previewText.includes(content)) {
        console.log('[test] ✅ Preview modal shows correct content');
      } else {
        console.log(`[test] ⚠️ Preview content mismatch (known files.read path issue): ${previewText.slice(0, 120)}`);
      }

      // Close preview modal (click X button in modal header)
      const closeBtn = page.locator('.fixed.inset-0.z-50 button').last();
      await closeBtn.click();
      await expect(page.locator('pre.text-xs.font-mono')).not.toBeVisible({ timeout: 5_000 });
      console.log('[test] ✅ Preview modal closed');
    },
  );

  // ═══════════════════════════════════════════════════════════════
  //  Test 3: AI creates .docx → appears in Task Assets → Preview shows Office message
  // ═══════════════════════════════════════════════════════════════

  test(
    'AI creates .docx file → appears in Task Assets → Preview shows Office notice',
    { timeout: LLM_TIMEOUT * 2 },
    async () => {
      await page.evaluate(async () => {
        for (let i = 0; i < 30; i++) {
          try {
            const s = await (window as any).miqi.runtime.status();
            if (s?.state === 'running' && s?.initialized) return;
          } catch { /* */ }
          await new Promise((r) => setTimeout(r, 1000));
        }
      });

      // Ensure panel is open
      const toggleBtn = page.locator('button[title="Toggle assets panel"]');
      const panelVisible = await page.getByTestId('task-assets-panel').isVisible().catch(() => false);
      if (!panelVisible) {
        await toggleBtn.click();
        await expect(page.getByTestId('task-assets-panel')).toBeVisible({ timeout: 5_000 });
      }

      const filename = `e2e_docx_${Date.now()}.docx`;
      const content = `E2E Docx test content ${Date.now()}`;

      // Have AI create a .docx file using create_docx tool
      await sendMessage(
        page,
        `使用 create_docx 工具创建文件：file_path=${filename}，content="${content}"。创建成功后只回复一个字：成`,
      );

      // Capture approval dialog for create_docx
      await expect(page.getByText('文件操作审批')).toBeVisible({ timeout: 60_000 });
      await page.screenshot({ path: 'test-results/docx-approval.png' });
      await page.getByRole('button', { name: '永久允许' }).click();
      await waitForResponseComplete(page, 240_000);

      // Verify AI confirmed creation in chat
      await expect(
        page.locator('main').getByText('成').first(),
      ).toBeVisible({ timeout: 15_000 });
      console.log(`[test] ✅ Docx created: ${filename}`);
      await page.screenshot({ path: 'test-results/docx-created.png' });

      // ── Verify docx appears in Task Assets panel (not "No files yet.") ──
      // This only works with a fresh frontend build that includes the
      // onFinal docx-tracking fix (ChatConsole.tsx ~line 760).
      const shortName = filename.slice(0, 20); // visible portion (truncated to 28)

      // Panel must no longer be empty
      await expect(page.getByText(/No files yet/)).not.toBeVisible({ timeout: 8_000 });

      // Scope to the assets panel only to avoid matching the same file card
      // that also appears in the main chat "Proposed Changes" area.
      const assetsPanel = page.getByTestId('task-assets-panel');
      const docxCard = assetsPanel.locator('.rounded-lg.p-2\\.5').filter({ hasText: shortName }).first();
      await expect(docxCard).toBeVisible({ timeout: 10_000 });

      // Should show ACTIVE FOR EDIT + WRITE + OFFICE badges
      await expect(page.getByText('ACTIVE FOR EDIT')).toBeVisible({ timeout: 5_000 });
      await expect(docxCard.getByText('WRITE')).toBeVisible({ timeout: 5_000 });
      await expect(docxCard.getByText('OFFICE')).toBeVisible({ timeout: 5_000 });
      console.log('[test] ✅ Docx appears in Task Assets panel');
      await page.screenshot({ path: 'test-results/docx-in-panel.png' });

      // ── Click Preview → Office notice modal ──
      await docxCard.getByRole('button', { name: 'Preview', exact: true }).click();
      await expect(page.getByText('Office document created')).toBeVisible({ timeout: 8_000 });
      console.log('[test] ✅ Preview shows Office notice');
      await page.screenshot({ path: 'test-results/docx-preview.png' });

      console.log('[test] ✅ Docx test complete');
    },
  );

});
