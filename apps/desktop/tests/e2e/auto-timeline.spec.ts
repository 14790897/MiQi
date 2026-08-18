/**
 * Auto Timeline E2E（#646-v2 GPT P0-3）— 必测 2 的 E2E 版。
 *
 * mock auto 分支（用户消息含"自动"）：web_search → write_file →
 * request_action_confirmation（ActionCard）→ 完成（不弹 PlanCard）。
 *
 * 断言：
 * 1. Auto 模式无 PlanCard（data-testid=plan-card 不出现）
 * 2. Timeline 出现（data-testid=timeline，非阻塞展示）
 * 3. 危险动作仍弹 ActionCard（确认）→ 完成后回合结束
 *
 * Run: cd apps/desktop && npx electron-vite build &&
 *      PLAYWRIGHT_SKIP_WEB_SERVER=1 npx playwright test \
 *      --config=playwright.config.ts --project=electron -g "auto timeline"
 */
import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import { spawn, type ChildProcess } from 'node:child_process';
import { join } from 'node:path';
import {
  LLM_TIMEOUT,
  sendMessage,
  waitForResponseComplete,
  launchElectronApp,
  closeElectronApp,
  createNewConversation,
  APPS_DESKTOP,
} from './helpers/electron-setup';

const REPO_ROOT = join(APPS_DESKTOP, '..', '..');

async function startMockOpenAI(): Promise<{ proc: ChildProcess; mockUrl: string }> {
  const python = process.env.MIQI_PYTHON_PATH || 'python';
  const port = 20000 + Math.floor(Math.random() * 20000);
  const proc = spawn(python, [join(REPO_ROOT, 'scripts', 'mock_openai.py'), String(port)], {
    cwd: REPO_ROOT,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
    windowsHide: true,
  });
  let readyUrl = '';
  let stderrTail = '';
  proc.stdout?.on('data', (d) => {
    const t = String(d);
    console.log(`[mock] ${t.trim()}`);
    const m = t.match(/http:\/\/127\.0\.0\.1:(\d+)\/v1/);
    if (m) readyUrl = `http://127.0.0.1:${m[1]}/v1`;
  });
  proc.stderr?.on('data', (d) => {
    stderrTail = (stderrTail + String(d)).slice(-2000);
    console.log(`[mock-err] ${String(d).trim()}`);
  });
  proc.on('exit', (code) => console.log(`[test] mock server exited: ${code}`));
  const deadline = Date.now() + 30_000;
  while (!readyUrl && Date.now() < deadline) {
    if (proc.exitCode !== null) {
      throw new Error(`mock OpenAI server exited early (code ${proc.exitCode}): ${stderrTail}`);
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  if (!readyUrl) {
    proc.kill();
    throw new Error(`mock OpenAI server startup line not seen in 30s: ${stderrTail}`);
  }
  return { proc, mockUrl: readyUrl };
}

test.describe('Auto Timeline (#646-v2)', () => {
  let electronApp: ElectronApplication;
  let page: Page;
  let mockServer: ChildProcess;
  let miqiHome: string;

  test.beforeAll(async () => {
    const mock = await startMockOpenAI();
    mockServer = mock.proc;
    const fixture = await launchElectronApp((config: any) => {
      const providers = config.providers ?? {};
      for (const [name, p] of Object.entries(providers)) {
        if (p && typeof p === 'object') {
          (p as any).apiBase = mock.mockUrl;
          if (!(p as any).apiKey) (p as any).apiKey = 'mock-key';
        }
      }
      config.providers = providers;
    });
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;
    page.on('pageerror', (err) => console.log(`[renderer-pageerror] ${String(err).slice(0, 300)}`));
    page.on('console', (msg) => {
      if (msg.type() === 'error') console.log(`[renderer-error] ${msg.text().slice(0, 300)}`);
    });
  }, 180_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
    mockServer?.kill();
  });

  test(
    'Auto 模式：无 PlanCard + Timeline 出现 + ActionCard 危险确认',
    { timeout: LLM_TIMEOUT },
    async () => {
      await createNewConversation(page);

      // ── 切模式到「自动」：点选项 → 二次确认弹窗 → 确认 ──
      const modeBtn = page.getByRole('button', { name: /允许编辑/ }).first();
      await modeBtn.click();
      const autoOpt = page.getByRole('button', { name: /自动.*完全自主执行/ }).first();
      await expect(autoOpt).toBeVisible({ timeout: 10_000 });
      await autoOpt.click();
      // 二次确认弹窗（auto 模式确认：Agent 将完全自主执行）
      const confirmBtn = page.getByRole('button', { name: /^确认$/ }).first();
      await expect(confirmBtn).toBeVisible({ timeout: 10_000 });
      await confirmBtn.click();
      await expect(page.getByText(/✓ 自主 已启用/)).toBeVisible({ timeout: 10_000 });
      await page.waitForTimeout(600);

      // ── 发任务（mock auto 分支）──
      await sendMessage(page, '自动：生成 MOF-5 实验报告并上传');

      // 自动批准审批弹窗（E2E 环境差异——真实用户模式不弹）
      const autoApprove = async () => {
        try {
          for (let i = 0; i < 60; i++) {
            const dialog = page.getByRole('alertdialog').first();
            if (await dialog.isVisible().catch(() => false)) {
              const allow = dialog.getByRole('button', { name: /允许一次|允许/ }).first();
              if (await allow.isVisible().catch(() => false)) {
                await allow.click();
                console.log('[test] 自动批准审批弹窗');
              }
            }
            await page.waitForTimeout(500);
          }
        } catch {
          // 页面已关闭——静默退出
        }
      };
      const approveTask = autoApprove();

      // Timeline 出现（非阻塞展示）
      const timeline = page.getByTestId('timeline').first();
      await expect(timeline).toBeVisible({ timeout: 60_000 });
      await expect(timeline.getByText('AI 正在执行任务')).toBeVisible();
      // 步骤为用户语言（list_dir→查看目录 / write_file→创建文档）
      await expect(timeline.getByText('查看目录')).toBeVisible();
      await expect(timeline.getByText('创建文档')).toBeVisible();

      // 无 PlanCard（确认卡不出现）
      const planCard = page.getByTestId('plan-card');
      await expect(planCard).toHaveCount(0);

      await page.screenshot({ path: 'test-results/auto-timeline-running.png' });

      // 危险动作仍弹 ActionCard（确认）——auto 不豁免安全
      const actionCard = page.getByTestId('action-card').first();
      await expect(actionCard).toBeVisible({ timeout: 60_000 });
      await expect(actionCard.getByText('即将上传数据')).toBeVisible();
      await actionCard.getByRole('button', { name: '确认上传' }).click();

      // 回合完成
      await waitForResponseComplete(page, LLM_TIMEOUT);
      await expect(page.getByText(/已完成：MOF-5 实验报告/)).toBeVisible({ timeout: 30_000 });
      await page.screenshot({ path: 'test-results/auto-timeline-done.png' });
    },
  );
});
