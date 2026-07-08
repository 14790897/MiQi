/**
 * E2E: Approval Persistence (永久允许 → next call auto-approves)
 *
 * Validates that after a user clicks "永久允许" for a tool operation,
 * subsequent identical operations are automatically approved without
 * showing the approval dialog again.
 *
 * KEY: write_file approval is path-specific, not tool-wide.  The
 * permanent allowlist pattern is "write_file:<path>".  To test
 * persistence, both calls MUST target the same file path.
 *
 * Run: cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron approval-persistence.spec.ts
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

async function createNewConversation(page: Page): Promise<string> {
  const sidebarPlusBtn = page.locator('button[title="New Session"]');
  await expect(sidebarPlusBtn).toBeVisible();
  await sidebarPlusBtn.click();
  await waitForInputReady(page, 15_000);
  await page.waitForTimeout(1500);
  const titleEl = page.locator('h2.font-semibold.truncate').first();
  return (await titleEl.textContent()) || '';
}

// ─── Test Suite ───────────────────────────────────────────────────

test.describe('Approval Persistence E2E', () => {
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

    try {
      await page.getByText('MiQi Workbench').waitFor({ timeout: 30_000 });
    } catch {
      console.log('[test] App UI may still be loading — continuing');
    }

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
    if (!bridgeReady) console.log('[test] Warning: bridge did not reach running state');

    console.log('[test] Ready');
  }, 120_000);

  test.afterAll(async () => {
    await electronApp?.close().catch(() => {});
  });

  // ═══════════════════════════════════════════════════════════════
  //  Test 1: 永久允许 persists for same file path
  // ═══════════════════════════════════════════════════════════════

  test(
    '永久允许: same file path twice, second call auto-approves',
    { timeout: LLM_TIMEOUT * 3 },
    async () => {
      // Ensure bridge ready, clear existing approvals
      await page.evaluate(async () => {
        for (let i = 0; i < 30; i++) {
          try {
            const s = await (window as any).miqi.runtime.status();
            if (s?.state === 'running' && s?.initialized) return;
          } catch { /* */ }
          await new Promise((r) => setTimeout(r, 1000));
        }
      });
      try {
        await page.evaluate(() =>
          (window as any).miqi.approvals.clearPermanent(),
        );
      } catch { /* fine */ }

      await createNewConversation(page);

      // Use the SAME file path for both calls so permanent allowlist matches
      const filepath = `e2e_persist_${Date.now()}.txt`;

      // ── First call: same file path → shows approval dialog ──
      await sendMessage(
        page,
        `Use write_file to create ${filepath} with content "first write"`,
      );

      await expect(page.getByText('文件操作审批')).toBeVisible({
        timeout: 60_000,
      });
      console.log('[test] ✅ First call: approval dialog appeared');

      await page.getByRole('button', { name: '永久允许' }).click();
      console.log('[test] Clicked 永久允许');

      await waitForResponseComplete(page, 240_000);
      await expect(
        page.locator('main').getByText(filepath, { exact: false }).first(),
      ).toBeVisible({ timeout: 15_000 });
      console.log(`[test] ✅ First file created: ${filepath}`);

      // ── Second call: SAME file path → should auto-approve ──
      await sendMessage(
        page,
        `Use write_file to overwrite ${filepath} with content "second write — auto-approved"`,
      );

      await waitForResponseComplete(page, 240_000);

      // Must NOT show approval dialog again
      await expect(page.getByText('文件操作审批')).not.toBeVisible({
        timeout: 5_000,
      });
      console.log('[test] ✅ Second call: no approval dialog (auto-approved)');

      await expect(
        page.locator('main').getByText(filepath, { exact: false }).first(),
      ).toBeVisible({ timeout: 15_000 });
      console.log(`[test] ✅ Second write auto-approved: ${filepath}`);
    },
  );

  // ═══════════════════════════════════════════════════════════════
  //  Test 2: Cross-session auto-approval
  // ═══════════════════════════════════════════════════════════════

  test(
    '永久允许: persists across new conversations (same path)',
    { timeout: LLM_TIMEOUT * 3 },
    async () => {
      try {
        await page.evaluate(() =>
          (window as any).miqi.approvals.clearPermanent(),
        );
      } catch { /* ok */ }

      await createNewConversation(page);
      const filepath = `e2e_cross_${Date.now()}.txt`;

      // ── Conv 1: approve permanently ──
      await sendMessage(
        page,
        `Use write_file to create ${filepath} with content "cross-session test"`,
      );
      await expect(page.getByText('文件操作审批')).toBeVisible({ timeout: 60_000 });
      await page.getByRole('button', { name: '永久允许' }).click();
      await waitForResponseComplete(page, 240_000);
      console.log(`[test] ✅ Conv 1: approved permanently for ${filepath}`);

      // ── Conv 2: new session, same path → auto-approve ──
      await createNewConversation(page);
      await sendMessage(
        page,
        `Use write_file to overwrite ${filepath} with content "cross-session overwrite"`,
      );
      await waitForResponseComplete(page, 240_000);

      await expect(page.getByText('文件操作审批')).not.toBeVisible({ timeout: 5_000 });
      console.log('[test] ✅ Conv 2: no approval dialog (cross-session permanent allowlist)');
    },
  );

});
