/**
 * Billing 真实链路 E2E（opt-in，需凭据；CI 无凭据自动跳过）：
 *   真实 OAuth2 登录（设置页 MiQroForge 平台）→ 新会话发消息 → 真实 LLM 调用 write_file
 *   → 计费闸门在首次工具执行前扣 30 积分 → 聊天区出现扣费提示。
 *
 * 运行（会真实消耗测试账号 30 积分）：
 *   QRAFT_PHONE=… QRAFT_PASSWORD=… npx playwright test  *     --config=playwright.config.ts --project=electron tests/e2e/billing-live.spec.ts
 * 依赖：真实平台可达、本地 provider 配置（launchElectronApp 复制用户配置）。
 */

import { test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  LLM_TIMEOUT,
  sendMessage,
  waitForResponseComplete,
  createNewConversation,
  launchElectronApp,
  closeElectronApp,
  type ElectronFixture,
} from './helpers/electron-setup';

async function approveLoop(page: Page, timeout = 180_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const btn = page
      .getByRole('button', { name: '持久允许' })
      .or(page.getByRole('button', { name: '永久允许' }));
    if (await btn.isVisible({ timeout: 1000 }).catch(() => false)) {
      await btn.click();
    }
    const thinking = await page
      .getByText('Thinking…')
      .isVisible()
      .catch(() => false);
    if (!thinking) break;
    await page.waitForTimeout(1000);
  }
}

const HAS_CREDS = !!process.env.QRAFT_PHONE && !!process.env.QRAFT_PASSWORD;

const describeFn = HAS_CREDS ? test.describe : test.describe.skip;

describeFn('Billing live E2E (opt-in)', () => {
  let fixture: ElectronFixture;
  let electronApp: ElectronApplication;
  let page: Page;

  test.beforeAll(async () => {
    fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
  }, 180_000);

  test.afterAll(async () => {
    if (electronApp) await closeElectronApp(electronApp, fixture?.miqiHome);
  });

  test('真实登录 → 对话触发工具 → 扣 30 积分 → 聊天区提示', { timeout: LLM_TIMEOUT }, async () => {
    // 1. 设置页真实登录（dev userData 可能残留上次运行的登录态，幂等处理）
    await page.getByText(/^(System Settings|系统设置)$/).click();
    await page
      .getByRole('tab')
      .filter({ hasText: /MiQroForge/ })
      .first()
      .click();
    const loggedInBadge = page.getByText('已登录');
    if (!(await loggedInBadge.isVisible({ timeout: 5000 }).catch(() => false))) {
      await page.getByTestId('qraft-phone-input').fill(process.env.QRAFT_PHONE!);
      await page.getByTestId('qraft-password-input').fill(process.env.QRAFT_PASSWORD!);
      await page.getByTestId('qraft-login-btn').click();
    }
    await expect(loggedInBadge).toBeVisible({ timeout: 90_000 });
    // 登录后余额展示（真实余额查询）
    await expect(page.getByTestId('qraft-points-value')).toBeVisible({ timeout: 30_000 });

    // 2. 新会话 + 预授权（避免审批卡住工具执行）
    await createNewConversation(page);
    await page.evaluate(() => (window as any).miqi.approvals.addPermanent('*:*', 'always'));

    // 3. 发送触发工具调用的消息
    await sendMessage(
      page,
      '使用 write_file 工具创建文件 billing-e2e.txt，内容为 hello billing。完成后只回复 DONE_BILLING'
    );
    await approveLoop(page);

    // 4. 计费提示：首次工具执行前扣 30 分（活动行与消息体各渲染一次，取首个）
    await expect(page.getByText(/已扣 30 积分/).first()).toBeVisible({ timeout: LLM_TIMEOUT });

    // 5. 回合正常收尾（限定 assistant 气泡，避免与用户消息/思考摘要撞词）
    await waitForResponseComplete(page, LLM_TIMEOUT);
    await expect(
      page
        .getByTestId('chat-message-assistant')
        .getByText(/DONE_BILLING/)
        .first()
    ).toBeVisible({ timeout: 30_000 });

    await page.screenshot({ path: 'test-results/billing-live-e2e.png', fullPage: true });
  });
});
