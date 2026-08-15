/**
 * Confirm Card E2E (issue #646) — ask_user_confirm_card 全链路。
 *
 * 用本地 mock OpenAI 服务器（scripts/mock_openai.py，确定性状态机）驱动，
 * 验证完整链路：
 *   1. 模型调用 ask_user_confirm_card → 桌面端消息流内弹确认卡（阻塞回合）
 *   2. 用户点击「确认执行」→ 选择以 tool result 回传 → 回合继续
 *      （mock 随后调用真实 web_search / write_file 工具）
 *   3. 第二张卡（是否上传到 Qraft？）→ 用户点击「确认上传」
 *   4. 回合完成，最终回复渲染；两张卡均留下「已选择」决议记录
 *
 * 不依赖真实 LLM 行为：mock 按工具调用序列推进，网络工具即使失败
 * （如 CI 无外网）也不会阻断状态机——只统计调用次数。
 *
 * Run: cd apps/desktop && npx playwright test \
 *      --config=playwright.config.ts --project=electron -g "confirm card"
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
  APPS_DESKTOP,
} from './helpers/electron-setup';

const REPO_ROOT = join(APPS_DESKTOP, '..', '..');

/**
 * Start scripts/mock_openai.py on an ephemeral port and wait for its
 * startup line (the server prints the ACTUAL bound port after bind).
 *
 * No HTTP readiness probe: undici fetch against 127.0.0.1 fails on some
 * CI runners (macos-e2e) even with the server listening, and an ephemeral
 * port makes parallel workers / retries immune to 8899 collisions.
 */
async function startMockOpenAI(): Promise<{ proc: ChildProcess; mockUrl: string }> {
  const python = process.env.MIQI_PYTHON_PATH || 'python';
  // High ephemeral range: avoids the app's own ports and 8899 legacy uses.
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
      throw new Error(
        `mock OpenAI server exited early (code ${proc.exitCode}): ${stderrTail}`,
      );
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  if (!readyUrl) {
    proc.kill();
    throw new Error(`mock OpenAI server startup line not seen in 30s: ${stderrTail}`);
  }
  console.log(`[test] mock OpenAI server ready at ${readyUrl}`);
  return { proc, mockUrl: readyUrl };
}

test.describe('Confirm Card (ask_user_confirm_card)', () => {
  // macOS CI cannot run this spec: the runner's undici fetch fails against
  // a local 127.0.0.1 listener and the spawned mock's stdout pipe never
  // delivers (both observed in macos-e2e). The Linux electron-e2e job runs
  // the full suite and covers this spec — same trimming strategy as #710.
  test.skip(
    process.platform === 'darwin' && !!process.env.CI,
    'macOS CI cannot reach the local mock server',
  );

  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;
  let mockServer: ChildProcess;

  test.beforeAll(async () => {
    const mock = await startMockOpenAI();
    mockServer = mock.proc;
    // Point EVERY configured provider at the mock — provider resolution
    // depends on the model in agents.defaults (CI uses siliconflow), so
    // patching a single provider would leak real API calls in CI. The mock
    // ignores model names and API keys.
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
  }, 180_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
    mockServer?.kill();
  });

  test(
    'mock 模型弹两张确认卡 — 用户点击后 tool result 回传、回合继续并完成',
    { timeout: LLM_TIMEOUT },
    async () => {
      const cardArea = page.getByTestId('confirm-card-area');
      const resolvedArea = page.getByTestId('confirm-card-resolved');

      // ── 发送任务 → 模型第一轮即调用 ask_user_confirm_card ──
      await sendMessage(page, '帮我生成 MOF-5 市场合成价格报告并确认执行');

      await expect(cardArea).toBeVisible({ timeout: 60_000 });
      await expect(cardArea.getByText('确认执行方案？')).toBeVisible();
      await expect(cardArea.getByText('搜索并下载相关论文')).toBeVisible(); // steps 渲染
      await expect(cardArea.getByRole('button', { name: '确认执行' })).toBeVisible();
      await expect(cardArea.getByRole('button', { name: '调整方案' })).toBeVisible();
      await expect(cardArea.getByRole('button', { name: '取消' })).toBeVisible();

      await page.screenshot({
        path: `test-results/${test.info().title.replace(/\s+/g, '-')}-card1.png`,
      });

      // ── 点击「确认执行」→ 决议回传 → mock 推进到 web_search/write_file ──
      await cardArea.getByRole('button', { name: '确认执行' }).click();
      await expect(resolvedArea.getByText('已选择「确认执行」')).toBeVisible({
        timeout: 30_000,
      });

      // ── 第二张卡：上传确认（web_search 走真实网络，CI 无外网时工具报错
      //    不影响状态机推进，但给足超时）──
      await expect(cardArea.getByText('方案已完成，是否上传到 Qraft？')).toBeVisible({
        timeout: 180_000,
      });
      await expect(cardArea.getByRole('button', { name: '确认上传' })).toBeVisible();

      await page.screenshot({
        path: `test-results/${test.info().title.replace(/\s+/g, '-')}-card2.png`,
      });

      await cardArea.getByRole('button', { name: '确认上传' }).click();
      await expect(resolvedArea.getByText('已选择「确认上传」')).toBeVisible({
        timeout: 30_000,
      });

      // ── 回合完成：最终回复渲染 ──
      await waitForResponseComplete(page, LLM_TIMEOUT);
      await expect(page.locator('main')).toContainText(
        '项目入口：forge.miqroera.com/projects/mof-price-report',
        { timeout: 30_000 },
      );
      await expect(page.locator('main')).toContainText('mof-price-report.workflow.json');

      // ── 两张卡均留下决议记录（v5 语义：决议是流程痕迹，不消失）──
      await expect(resolvedArea.getByText('确认执行方案？')).toBeVisible();
      await expect(resolvedArea.getByText('方案已完成，是否上传到 Qraft？')).toBeVisible();

      await page.screenshot({
        path: `test-results/${test.info().title.replace(/\s+/g, '-')}-final.png`,
        fullPage: true,
      });
    },
  );
});
