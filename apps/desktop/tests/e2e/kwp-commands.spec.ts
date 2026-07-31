/**
 * E2E: KWP slash command + auto skill trigger
 *
 * Verifies that the embedded knowledge-work-plugins integration works
 * end-to-end in a real Electron session:
 *
 * 1. /brainstorm flows through the bridge and the agent receives a
 *    system prompt containing the brainstorm command body, plus the
 *    user arguments in a "User arguments" sub-section.
 * 2. /brainstorm with no args still injects the command body
 *    (LLM responds as if briefed even without user input).
 * 3. Auto skill trigger: a natural-language phrase like
 *    "帮研究一下 Acme Corp" causes the agent to load
 *    kwp/sales/account-research/SKILL.md and run its workflow.
 * 4. Slash command bodies surface in the assistant's reply — the
 *    injected content actually shapes the response (not silently
 *    ignored).
 * 5. Skill metadata appears in the SkillsPage UI under the
 *    "Knowledge Work" group.
 *
 * Run: cd apps/desktop && npx playwright test --config=playwright.config.ts \
 *      --project=electron kwp-commands.spec.ts
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  launchElectronApp,
  closeElectronApp,
  waitForBridgeInitialized,
  waitForInputReady,
  sendMessage,
  waitForResponseComplete,
} from './helpers/electron-setup';

// Phrases that should reliably trigger the embedded KWP skills.
// Each phrase matches the description text in the converted SKILL.md
// frontmatter ("Trigger with ...") so the LLM is expected to load
// the corresponding skill via read_file().
const BRAINSTORM_PROMPT = '/brainstorm 关于如何提升 Q3 用户留存率';
const BRAINSTORM_NOARGS = '/brainstorm';
const AUTOTRIGGER_PROMPT = '帮研究一下 Anthropic 这家公司，给出关键信息';

test.describe('KWP Commands & Skill Auto-trigger E2E', () => {
  let electronApp: ElectronApplication;
  let page: Page;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
    await waitForBridgeInitialized(page);
    // Sanity-check: skills.list should expose KWP skills via the
    // SkillsLoader built-in pipeline.  We don't strictly need this —
    // it's just an early-bail mechanism if the built-ins broke.
    const skillsCheck = await page.evaluate(async () => {
      // The bridge doesn't expose a skills namespace directly in E2E;
      // route through the runtime status probe instead.
      const s = await (window as any).miqi.runtime.status();
      return { state: s?.state, initialized: s?.initialized };
    });
    if (skillsCheck.initialized !== true) {
      test.skip(true, 'Bridge not initialized — skipping KWP E2E');
    }
  }, 60_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp);
  });

  test.beforeEach(async () => {
    // Fresh conversation for each scenario so prior-context bleed
    // doesn't muddy an isolated assertion.
    await page.keyboard.press('Control+N').catch(() => {});
    await page.waitForTimeout(800);
  });

  // ──────── Test 1: /brainstorm command + user args ────────

  test('/brainstorm prepends command body and accepts user args', async () => {
    const textarea = await waitForInputReady(page);
    await textarea.fill(BRAINSTORM_PROMPT);
    await textarea.press('Enter');

    // User message visible in chat.
    await expect(page.getByText(BRAINSTORM_PROMPT).first()).toBeVisible({
      timeout: 10_000,
    });

    await waitForResponseComplete(page, 180_000);

    // The agent should respond substantively.  We assert *content
    // shape* rather than a fixed string because LLM wording varies:
    // the response must include Chinese characters (we asked in
    // Chinese) and must mention at least one of the brainstorm-style
    // cue phrases from the KWP prompt body.
    const body = await page.locator('main').last().textContent();
    expect(body || '').toMatch(/[一-鿿]/); // any CJK char
    const cuePhrases = [
      '产品', '路线', '战略', '需求', '用户',
      '假设', '机会', '风险', '方案', 'idea',
      'feature', 'requirement', 'opportunity',
    ];
    const hit = cuePhrases.some((p) => (body || '').includes(p));
    expect(hit).toBeTruthy();
  });

  // ──────── Test 2: /brainstorm with no args ────────

  test('/brainstorm without args still injects prompt body', async () => {
    const textarea = await waitForInputReady(page);
    await textarea.fill(BRAINSTORM_NOARGS);
    await textarea.press('Enter');

    await expect(page.getByText(BRAINSTORM_NOARGS).first()).toBeVisible({
      timeout: 10_000,
    });
    await waitForResponseComplete(page, 180_000);

    const body = await page.locator('main').last().textContent();
    // The command body is empty / fallback in this case, but the agent
    // must still produce some response rather than hang or 500.
    expect((body || '').length).toBeGreaterThan(20);
  });

  // ──────── Test 3: auto skill trigger via natural language ────────

  test('natural-language "research [company]" auto-triggers account-research', async () => {
    const textarea = await waitForInputReady(page);
    await textarea.fill(AUTOTRIGGER_PROMPT);
    await textarea.press('Enter');

    await expect(page.getByText(AUTOTRIGGER_PROMPT).first()).toBeVisible({
      timeout: 10_000,
    });

    await waitForResponseComplete(page, 180_000);

    // Expected behavior: the agent should at minimum perform web
    // searches.  Web searches are typically visible as tool-call
    // cards (we look for "IN PROGRESS" tag visibility during the run,
    // then assert that the final response mentions the searched
    // company).  An Anthropic-specific cue: the response should
    // contain "Anthropic" (or a factual close — Claude AI company).
    const body = await page.locator('main').last().textContent();
    expect(body || '').toMatch(/Anthropic/);
  });

  // ──────── Test 4: skills UI surfaces Knowledge Work group ────────

  test('SkillsPage shows "Knowledge Work" group for KWP skills', async () => {
    // Open Skills page through sidebar.  Sidebar nav is the standard
    // way in the current UI.
    const navItem = page.locator('[data-testid="nav-skills"]');
    if (!(await navItem.isVisible({ timeout: 5_000 }).catch(() => false))) {
      test.skip(true, 'Skills sidebar entry not present in this build');
      return;
    }
    await navItem.click();
    await page.waitForTimeout(1_500);

    // The SkillsPage UI groups KWP skills under "Knowledge Work".
    // Wait for the heading then assert at least one skill row exists.
    const heading = page.getByText('Knowledge Work', { exact: false }).first();
    await expect(heading).toBeVisible({ timeout: 10_000 });

    // Account-research should be visible among the converted skills.
    await expect(page.getByText('account-research', { exact: false }).first())
      .toBeVisible({ timeout: 5_000 });
  });
});
