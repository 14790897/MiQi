/**
 * Plan Card E2E（#646-v2）— ask_user_plan_confirm → ActionCard 全链路。
 *
 * mock 状态机（scripts/mock_openai.py plan 分支）：用户消息含"计划" →
 * ask_user_plan_confirm（PlanCard）→ web_search → write_file →
 * request_action_confirmation（ActionCard）→ 完成。
 *
 * Run: cd apps/desktop && npx electron-vite build &&
 *      PLAYWRIGHT_SKIP_WEB_SERVER=1 npx playwright test \
 *      --config=playwright.config.ts --project=electron -g "plan card"
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

test.describe('Plan Card (#646-v2)', () => {
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
    // 监听前端错误（PlanCard 渲染崩溃排查）
    page.on('console', (msg) => {
      if (msg.type() === 'error' || msg.type() === 'warning') {
        console.log(`[renderer-${msg.type()}] ${msg.text().slice(0, 300)}`);
      }
    });
    page.on('pageerror', (err) => console.log(`[renderer-pageerror] ${String(err).slice(0, 400)}`));
  }, 180_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
    mockServer?.kill();
  });

  test(
    '计划卡全链路：PlanCard → 开始执行 → ActionCard → 确认 → 完成',
    { timeout: LLM_TIMEOUT },
    async () => {
      await createNewConversation(page);
      await sendMessage(page, '计划：生成 MOF-5 实验报告并上传');

      // ── PlanCard 出现（步骤文字 + 权限 + 按钮）──
      const planCard = page.getByTestId('plan-card').first();
      await expect(planCard).toBeVisible({ timeout: 60_000 });
      await expect(planCard.getByText('生成 MOF-5 实验报告')).toBeVisible();
      // 步骤为用户语言（无工具名）
      await expect(planCard.getByText('搜集论文资料')).toBeVisible();
      await expect(planCard.getByText('上传到 Qraft').first()).toBeVisible();
      // 权限 pill
      await expect(planCard.getByText('网络访问')).toBeVisible();
      await expect(planCard.getByText('外部上传')).toBeVisible();

      await page.screenshot({ path: 'test-results/plan-card-waiting.png' });

      // ── 点「开始执行」→ 执行（期间审批弹窗自动允许——E2E 环境差异）──
      await planCard.getByRole('button', { name: '开始执行' }).click();

      // 自动批准审批弹窗（web_search 等在 E2E 环境触发——真实用户模式不弹）
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
          // 页面已关闭（测试结束）——静默退出
        }
      };
      const approveTask = autoApprove();

      // ── ActionCard 出现（危险动作确认）──
      const actionCard = page.getByTestId('action-card').first();
      await expect(actionCard).toBeVisible({ timeout: 60_000 });
      await expect(actionCard.getByText('即将上传数据')).toBeVisible();
      await expect(actionCard.getByText('Qraft').first()).toBeVisible();
      await expect(actionCard.getByText('mof-report.json').first()).toBeVisible();
      await expect(actionCard.getByText(/23\.0 KB/)).toBeVisible();

      await page.screenshot({ path: 'test-results/action-card-upload.png' });

      // ── 确认上传 → 回合完成 ──
      await actionCard.getByRole('button', { name: '确认上传' }).click();
      await waitForResponseComplete(page, LLM_TIMEOUT);
      await expect(page.getByText(/已完成：MOF-5 实验报告/)).toBeVisible({ timeout: 30_000 });
    },
  );
});
