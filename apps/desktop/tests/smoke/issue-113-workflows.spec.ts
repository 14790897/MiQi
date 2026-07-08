/**
 * Issue #113 regression coverage: desktop workflows that previously required
 * manual UI checks. These tests run against the mock bridge so they are fast,
 * deterministic, and suitable for smoke regression runs.
 */

import { expect, test, type Page } from '@playwright/test';
import { buildMockBridgeScript } from './mocks';

const SETTINGS_TAB = {
  skills: 'settings-tab-skills',
  mcps: 'settings-tab-mcps',
  memory: 'settings-tab-memory',
} as const;

async function injectMockAndGoto(page: Page) {
  await page.addInitScript({ content: buildMockBridgeScript() });
  await page.route('https://skills.sixiangjia.de/index.json', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        skills: [
          {
            name: 'issue-113-skill',
            description: 'SkillHub install smoke fixture',
          },
        ],
      }),
    });
  });
  await page.route('https://skills.sixiangjia.de/issue-113-skill/SKILL.md', async (route) => {
    await route.fulfill({
      contentType: 'text/markdown',
      body: '# issue-113-skill\n\nInstalled by the issue 113 smoke test.',
    });
  });
  await page.goto('/');
  await page.waitForSelector('#root', { state: 'visible' });
}

async function openSettingsTab(page: Page, tab: keyof typeof SETTINGS_TAB) {
  await page.getByText('System Settings').click();
  const tabLocator = page.getByRole('tab', { name: SETTINGS_TAB[tab] });
  await expect(tabLocator).toBeVisible({ timeout: 5000 });
  await tabLocator.click();
}

test.describe('Issue #113 desktop workflow smoke coverage', () => {
  test.beforeEach(async ({ page }) => {
    await injectMockAndGoto(page);
  });

  test('skills page can browse local skills, open details, and install from SkillHub', async ({
    page,
  }) => {
    await openSettingsTab(page, 'skills');

    await expect(page.getByText('code-reviewer').first()).toBeVisible({ timeout: 5000 });
    await page.getByText('code-reviewer').first().click();
    await expect(page.getByRole('heading', { name: 'code-reviewer', level: 2 })).toBeVisible();
    await expect(page.getByText('Review code for bugs and style issues').first()).toBeVisible();

    await page.getByRole('button', { name: 'SkillHub' }).click();
    await expect(page.getByRole('heading', { name: 'SkillHub' })).toBeVisible();
    await expect(page.getByText('issue-113-skill')).toBeVisible({ timeout: 5000 });
    await page.getByRole('button', { name: 'install-skill-issue-113-skill' }).click();
    await expect
      .poll(() =>
        page.evaluate(async () => {
          const result = await (window as any).miqi.skills.list();
          return result.skills.some((skill: { name: string }) => skill.name === 'issue-113-skill');
        }),
      )
      .toBe(true);
    await expect
      .poll(() =>
        page.evaluate(() =>
          (window as any).__miqiMock.calls.some(
            (call: { type: string; name: string }) =>
              call.type === 'skills.upload' && call.name === 'issue-113-skill',
          ),
        ),
      )
      .toBe(true);
  });

  test('MCP page lists configured servers and saves a new server', async ({ page }) => {
    await openSettingsTab(page, 'mcps');

    await expect(page.getByText('filesystem-demo')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Local filesystem tools')).toBeVisible();

    await page.getByRole('button', { name: 'mcp-add-server' }).click();
    await page.getByPlaceholder('my-mcp-server').fill('issue-113-mcp');
    await page.getByPlaceholder('npx').fill('node');
    await page.getByPlaceholder('-y, @modelcontextprotocol/server-filesystem').fill('server.js');
    await page.getByRole('button', { name: 'mcp-save-server' }).click();

    await expect(page.getByText('issue-113-mcp')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('node server.js')).toBeVisible();
    await expect
      .poll(() =>
        page.evaluate(() => {
          const call = (window as any).__miqiMock.calls.find(
            (entry: { type: string; name: string }) =>
              entry.type === 'mcps.upsert' && entry.name === 'issue-113-mcp',
          );
          return call?.config?.command === 'node' && call?.config?.args?.[0] === 'server.js';
        }),
      )
      .toBe(true);
  });

  test('memory page loads files, edits content, and refreshes lesson state', async ({ page }) => {
    await openSettingsTab(page, 'memory');

    await expect(page.getByText('README.md')).toBeVisible({ timeout: 5000 });
    await page.getByText('README.md').click();
    const editor = page.locator('main textarea:visible').last();
    await expect(editor).toHaveValue(/Remember smoke QA\./);

    await editor.fill('# Workspace notes\nRemember issue 113 coverage.');
    await page.getByRole('button', { name: 'memory-save-file' }).click();
    await page.getByRole('button', { name: 'memory-confirm-save' }).click();
    await expect(editor).toHaveValue(/Remember issue 113 coverage\./);
    await expect
      .poll(() =>
        page.evaluate(() =>
          (window as any).__miqiMock.calls.some(
            (call: { type: string; path: string; content: string }) =>
              call.type === 'memory.update' &&
              call.path === 'README.md' &&
              call.content.includes('Remember issue 113 coverage.'),
          ),
        ),
      )
      .toBe(true);

    await page.getByText('When adding Playwright tests').click();
    await expect(page.getByText('Assert bridge calls and visible UI state')).toBeVisible();
    await page.getByRole('button', { name: 'memory-unlearn-lesson-1' }).click();
    await expect(page.getByText('When adding Playwright tests')).toBeHidden({ timeout: 5000 });
    await expect
      .poll(() =>
        page.evaluate(() =>
          (window as any).__miqiMock.calls.some(
            (call: { type: string; id: string }) =>
              call.type === 'memory.lessonUnlearn' && call.id === 'lesson-1',
          ),
        ),
      )
      .toBe(true);
  });

  test('cron bridge workflow lists jobs, creates a job, and records a manual run', async ({
    page,
  }) => {
    const result = await page.evaluate(async () => {
      const miqi = (window as any).miqi;
      const before = await miqi.cron.list();
      const created = await miqi.cron.create({
        name: 'Issue 113 scheduled check',
        scheduleKind: 'every',
        everyMs: 60000,
        message: 'Run the regression smoke suite',
      });
      await miqi.cron.run(created.job.id);
      const after = await miqi.cron.list();
      const runs = await miqi.cron.runs();
      return {
        beforeCount: before.jobs.length,
        afterCount: after.jobs.length,
        createdName: created.job.name,
        latestRun: runs.runs[0],
      };
    });

    expect(result.beforeCount).toBeGreaterThan(0);
    expect(result.afterCount).toBe(result.beforeCount + 1);
    expect(result.createdName).toBe('Issue 113 scheduled check');
    expect(result.latestRun).toMatchObject({
      jobName: 'Issue 113 scheduled check',
      status: 'ok',
    });
    await expect
      .poll(() =>
        page.evaluate(() => {
          const calls = (window as any).__miqiMock.calls;
          return (
            calls.some((call: { type: string }) => call.type === 'cron.create') &&
            calls.some((call: { type: string }) => call.type === 'cron.run')
          );
        }),
      )
      .toBe(true);
  });

  test('cron update preserves schedule and run state on partial edits', async ({ page }) => {
    const result = await page.evaluate(async () => {
      const miqi = (window as any).miqi;
      const created = await miqi.cron.create({
        name: 'Issue 113 preserve state',
        scheduleKind: 'every',
        everyMs: 120000,
        message: 'original prompt',
      });
      await miqi.cron.run(created.job.id);
      const beforeUpdate = (await miqi.cron.list()).jobs.find(
        (job: { id: string }) => job.id === created.job.id,
      );
      const updated = await miqi.cron.update({
        jobId: created.job.id,
        name: 'Issue 113 renamed job',
      });
      return {
        beforeLastRunAtMs: beforeUpdate.state.lastRunAtMs,
        everyMs: updated.job.schedule.everyMs,
        lastRunAtMs: updated.job.state.lastRunAtMs,
        lastStatus: updated.job.state.lastStatus,
        message: updated.job.payload.message,
      };
    });

    expect(result.everyMs).toBe(120000);
    expect(result.lastRunAtMs).toBe(result.beforeLastRunAtMs);
    expect(result.lastStatus).toBe('ok');
    expect(result.message).toBe('original prompt');
  });
});
