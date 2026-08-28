/**
 * E2E — issue #864 写授权卡（真实 LLM 路径）。
 *
 * 与 write-authorization.spec.ts（mock 状态机）互补：本 spec 不 patch provider，
 * 用配置中的真实模型（本地 deepseek / CI siliconflow），显式指令模型用
 * write_file 写 workspace 外目录，验证真实模型 + 真实 HTTP 下：
 *   1. 写授权卡弹出（允许本次 / 本目录不再询问 / 拒绝）
 *   2. 点「允许本次」→ 写放行 → 产物落在 workspace 外目录
 *
 * 断言刻意收敛：真实模型回复文案不可控，只断言卡片出现、产物落盘。
 *
 * Run: cd apps/desktop && npx playwright test \
 *      --config=playwright.config.ts --project=electron \
 *      write-authorization-real-llm.spec.ts --workers=1
 */

import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { existsSync, readFileSync, mkdtempSync, rmSync } from 'node:fs';
import {
  LLM_TIMEOUT,
  sendMessage,
  waitForResponseComplete,
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';

test.describe('Write Authorization Card (real LLM)', () => {
  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;
  let outDir: string;

  test.beforeAll(async () => {
    outDir = mkdtempSync(join(tmpdir(), 'miqi-e2e-auth-llm-'));
    console.log(`[test] real-LLM auth out dir: ${outDir}`);
    // 真实 provider（不 patch provider 配置）。restrictToWorkspace 打开写
    // 白名单；bypassAll 关闭以让授权卡可弹。autoUserDirs 关闭——否则用户
    // 消息里的目标路径会命中 #821「用户点名目录自动授权」，直接放行、不弹卡。
    const fixture = await launchElectronApp((config: any) => {
      const tools = config.tools ?? {};
      config.tools = { ...tools, restrictToWorkspace: true, autoUserDirs: false };
    }, { bypassAll: false });
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;
  }, 180_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
    try { rmSync(outDir, { recursive: true, force: true }); } catch {}
  });

  test(
    '真实模型写 workspace 外目录 → 弹写授权卡 → 允许本次 → 写入成功',
    { timeout: LLM_TIMEOUT },
    async () => {
      const cardArea = page.getByTestId('confirm-card-area');
      const resolvedArea = page.getByTestId('confirm-card-resolved');

      // 跳过 PermissionEngine 的通用「文件操作审批」dialog（见
      // write-authorization.spec.ts 同款说明），精确测到授权卡。
      await page.evaluate(() =>
        (window as any).miqi.approvals.addPermanent('*:*', 'always'),
      );

      const fname = 'auth_probe_llm.txt';
      await sendMessage(
        page,
        `请调用 write_file 工具，把内容 "real-llm-authorization-probe" 写入 ` +
          `${join(outDir, fname)}（这是工作区外的目录）。` +
          `调用后只回复工具结果原文。`,
      );

      // 写授权卡弹出
      await expect(cardArea).toBeVisible({ timeout: 120_000 });
      await expect(cardArea.getByText('授权写入工作区外目录')).toBeVisible();
      await expect(cardArea.getByRole('button', { name: '允许本次' })).toBeVisible();

      await page.screenshot({
        path: `test-results/${test.info().title.replace(/\s+/g, '-')}-card.png`,
      });

      // 点「允许本次」→ 写放行
      await cardArea.getByRole('button', { name: '允许本次' }).click();
      await expect(resolvedArea.getByText(/授权写入工作区外目录/)).toBeVisible({
        timeout: 30_000,
      });

      // 产物落在 workspace 外目录
      const target = join(outDir, fname);
      await expect
        .poll(async () => existsSync(target), { timeout: 60_000 })
        .toBe(true);
      const content = readFileSync(target, 'utf-8');
      expect(content).toContain('real-llm-authorization-probe');
      console.log(`[test] ✅ 真实 LLM 写授权卡放行，产物落在 workspace 外目录`);

      await waitForResponseComplete(page, LLM_TIMEOUT);

      await page.screenshot({
        path: `test-results/${test.info().title.replace(/\s+/g, '-')}-final.png`,
        fullPage: true,
        timeout: 60_000,
      });
    },
  );
});
