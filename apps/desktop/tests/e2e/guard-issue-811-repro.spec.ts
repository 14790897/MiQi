/**
 * E2E: Issue #811 沙箱护栏误拦截复现 — rm -rf / 复合命令 / sudo
 *
 * 用本地 mock OpenAI 服务器（scripts/mock_openai.py，确定性状态机）驱动，
 * mock 按「护栏811」触发词推进 exec 工具调用序列，验证 KUN runtime 的
 * ExecTool._guard_command 行为（approval 层在 E2E 中被 bypass_all 跳过，
 * 护栏是 exec 的最终防线——正是 #811 所报告的那一层）：
 *
 *   A. session 目录内的 rm -rf 清理 → 期望放行（目录真的被删掉）
 *   B. 越界删除（/etc）          → 期望结构化拒绝 + 安全替代指引
 *   C. 复合命令（echo && rm -rf）→ 期望逐子命令判定后整条放行
 *   D. sudo 提权                 → 期望结构化声明不可用 + 替代指引
 *
 * mock 会把 exec 工具结果折算成最终回复文本（REPRO_X_DONE OK/BLOCKED/GENERIC），
 * 如同真实 LLM 向用户报告工具结果——测试断言最终标记，是用户可感知的结果。
 *
 * 现状（修复前）：A/C/D 被 deny 模式一刀切拦截（"检测到危险模式"，无指引），
 * agent 只能换写法绕过（shutil.rmtree）——本 spec 断言期望行为，修复前运行
 * 失败（即复现 bug）。
 *
 * 不依赖 bwrap 沙箱：mock 全部使用相对路径（相对 exec cwd），且
 * patchConfig 显式关闭沙箱（Linux CI 的 bwrap 因受限 user namespaces
 * 无法运行）——本 spec 验证的是护栏层本身，护栏在沙箱创建之前执行，
 * 与沙箱无关。exec 在主机直执行（Windows Git Bash / Linux bash）。
 *
 * Run: cd apps/desktop && npx playwright test \
 *      --config=playwright.config.ts --project=electron -g "护栏811"
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import { spawn, type ChildProcess } from 'node:child_process';
import { join } from 'node:path';
import {
  LLM_TIMEOUT,
  sendMessage,
  launchElectronApp,
  closeElectronApp,
  createNewConversation,
  APPS_DESKTOP,
} from './helpers/electron-setup';

const REPO_ROOT = join(APPS_DESKTOP, '..', '..');

/** 等待 mock 的最终标记渲染（不能拿 main 文本静止当同步点——
 *  工具执行期间 UI 静止是正常状态，且首个 exec 在冷启动下约需 25s）。 */
async function waitForVerdict(page: Page, marker: string) {
  await expect(
    page.locator('main').getByText(marker, { exact: false }).first(),
  ).toBeVisible({ timeout: 180_000 });
}

/** 标题 → 合法文件名（去掉路径分隔符和冒号）。 */
function safeShotName(title: string): string {
  return title.replace(/[\s/:\\()（）]+/g, '-');
}

/**
 * Start scripts/mock_openai.py on an ephemeral port and wait for its
 * startup line (the server prints the ACTUAL bound port after bind).
 * Same pattern as confirm-card.spec.ts (#646).
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

test.describe('Issue #811 护栏误拦截复现', () => {
  // macOS CI cannot run this spec: the runner's undici fetch fails against
  // a local 127.0.0.1 listener and the spawned mock's stdout pipe never
  // delivers (both observed in macos-e2e).  Same trimming as #646/#710.
  test.skip(
    process.platform === 'darwin' && !!process.env.CI,
    'macOS CI cannot reach the local mock server',
  );

  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;
  let mockServer: ChildProcess;

  test.beforeAll(async () => {
    // Playwright hooks take no timeout argument — set it inside the hook.
    test.setTimeout(180_000);
    const mock = await startMockOpenAI();
    mockServer = mock.proc;
    // Point EVERY configured provider at the mock (same as #646).
    const fixture = await launchElectronApp((config: any) => {
      const providers = config.providers ?? {};
      for (const [name, p] of Object.entries(providers)) {
        if (p && typeof p === 'object') {
          (p as any).apiBase = mock.mockUrl;
          if (!(p as any).apiKey) (p as any).apiKey = 'mock-key';
        }
      }
      config.providers = providers;
      // Issue #811: the guard now lets real execs run.  Two environment
      // accommodations:
      // 1. Sandbox disabled — the Linux CI runner has bwrap installed
      //    (so BWRAP gets selected) but its user namespaces are
      //    restricted ("bwrap: loopback: Failed to mount"), which would
      //    fail every exec.  The guard runs BEFORE any sandbox and its
      //    semantics here are host-path based, so this spec verifies the
      //    guard layer itself on direct host execution.
      // 2. tools.exec.timeout raised to 120 — on Windows E2E the first
      //    Git Bash spawns take ~25-30 s (Defender/cold start), which
      //    races the SandboxSelection timeout (30 s engine default).
      config.tools = {
        ...config.tools,
        exec: { ...(config.tools?.exec ?? {}), timeout: 120 },
        sandbox: { ...(config.tools?.sandbox ?? {}), enabled: false },
      };
    });
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;
  });

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
    mockServer?.kill();
  });

  test(
    'A: session 目录内 rm -rf 清理应放行（修复前被一刀切拦截）',
    { timeout: LLM_TIMEOUT },
    async () => {
      await createNewConversation(page);
      await sendMessage(page, '护栏811a');
      // Wait for the FULL verdict text — matching a prefix would return
      // mid-stream while the rest of the message is still rendering.
      await waitForVerdict(page, 'REPRO_A_DONE OK: 目录已删除');

      const mainText = (await page.locator('main').textContent()) || '';
      console.log('[test] === 811a 最终回复 ===');
      console.log(mainText.slice(-800));
      console.log('[test] ===========================');

      // 期望行为：rm -rf 放行 → 目录被删除（mock 折算的最终标记为 OK）
      expect(mainText).toContain('REPRO_A_DONE OK: 目录已删除');
      await page.screenshot({
        path: `test-results/${safeShotName(test.info().title)}.png`,
        fullPage: true,
      });
      console.log('[test] ✅ 811a: session 内 rm -rf 放行');
    },
  );

  test(
    'B: 越界删除（/etc）应结构化拒绝并给出安全替代指引',
    { timeout: LLM_TIMEOUT },
    async () => {
      await createNewConversation(page);
      await sendMessage(page, '护栏811b');
      await waitForVerdict(page, 'REPRO_B_DONE OK: 结构化拒绝');

      const mainText = (await page.locator('main').textContent()) || '';
      console.log('[test] === 811b 最终回复 ===');
      console.log(mainText.slice(-600));
      console.log('[test] ===========================');

      // 期望行为：结构化拒绝 + 明确的安全替代指引
      expect(mainText).toContain('REPRO_B_DONE OK: 结构化拒绝');
      await page.screenshot({
        path: `test-results/${safeShotName(test.info().title)}.png`,
        fullPage: true,
      });
      console.log('[test] ✅ 811b: 越界删除结构化拒绝');
    },
  );

  test(
    'C: 复合命令（echo && rm -rf）应逐子命令判定后整条放行',
    { timeout: LLM_TIMEOUT },
    async () => {
      await createNewConversation(page);
      await sendMessage(page, '护栏811c');
      await waitForVerdict(page, 'REPRO_C_DONE OK: 复合命令放行且目录已删除');

      const mainText = (await page.locator('main').textContent()) || '';
      console.log('[test] === 811c 最终回复 ===');
      console.log(mainText.slice(-800));
      console.log('[test] ===========================');

      // 期望行为：复合命令整条放行 → rm 子命令执行 → 目录被删除
      expect(mainText).toContain('REPRO_C_DONE OK: 复合命令放行且目录已删除');
      await page.screenshot({
        path: `test-results/${safeShotName(test.info().title)}.png`,
        fullPage: true,
      });
      console.log('[test] ✅ 811c: 复合命令放行');
    },
  );

  test(
    'D: sudo 提权应结构化声明不可用并给出替代指引',
    { timeout: LLM_TIMEOUT },
    async () => {
      await createNewConversation(page);
      await sendMessage(page, '护栏811d');
      await waitForVerdict(page, 'REPRO_D_DONE OK: 结构化提权声明');

      const mainText = (await page.locator('main').textContent()) || '';
      console.log('[test] === 811d 最终回复 ===');
      console.log(mainText.slice(-600));
      console.log('[test] ===========================');

      // 期望行为：结构化声明提权不可用（带替代指引），而非一刀切拦截
      expect(mainText).toContain('REPRO_D_DONE OK: 结构化提权声明');
      await page.screenshot({
        path: `test-results/${safeShotName(test.info().title)}.png`,
        fullPage: true,
      });
      console.log('[test] ✅ 811d: sudo 结构化拒绝');
    },
  );
});
