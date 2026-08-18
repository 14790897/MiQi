/**
 * Qraft 平台 OAuth2 登录 — Electron E2E（issue #726）。
 *
 * 覆盖真实主进程链路（qraft IPC → QraftService → QraftStore 落盘）：
 *   1. 登录表单渲染、密码掩码、高级设置折叠
 *   2. 登录失败的错误分类提示（不可路由 baseUrl 强制网络失败，无外部依赖）
 *   3. 预置登录态（MIQI_QRAFT_STORE 指向临时文件）→ 账号信息展示 →
 *      退出登录 → 磁盘文件被清空（验证真实持久化路径）
 *
 * 不依赖 Qraft 网络：登录态由测试预置（plain 信封），错误路径用
 * TEST-NET-1（192.0.2.1）强制请求失败，任何平台（含 macOS CI）行为一致。
 */

import { test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { writeFileSync, readFileSync, existsSync, rmSync } from 'node:fs';
import {
  launchElectronApp,
  closeElectronApp,
  type ElectronFixture,
} from './helpers/electron-setup';

const STORE_ENV = 'MIQI_QRAFT_STORE';
const TEST_BASE_URL = 'https://192.0.2.1/api'; // TEST-NET-1，永远不可达

/** 构造 plain 信封的预置登录态文件内容（QraftStore 支持无 safeStorage 降级读取）。 */
function buildSeededStoreContent(): string {
  const state = {
    version: 1,
    env: 'test',
    baseUrl: 'https://test.forge.miqroera.com/api',
    clientId: 'miqi',
    clientSecret: 'test-client-secret',
    redirectUri: 'http://localhost:38000/callback',
    cookie: 'Authorization=e2e-test-cookie',
    account: {
      phone: '18500000000',
      sub: '19',
      username: 'E2E-USER',
      nickname: 'E2E测试账号',
    },
    tokens: {
      accessToken: 'e2e-fake-access-token',
      refreshToken: 'e2e-fake-refresh-token',
      openid: 'e2e-fake-openid',
      expiresAt: Date.now() + 7_199_000, // 实测 expires_in=7199
    },
  };
  return JSON.stringify({
    v: 1,
    enc: 'plain',
    payload: Buffer.from(JSON.stringify(state), 'utf8').toString('base64'),
  });
}

async function gotoQraftTab(page: Page): Promise<void> {
  await page.getByText(/^(System Settings|系统设置)$/).click();
  await page.getByRole('tab').filter({ hasText: /Qraft/ }).click();
}

let storePath: string;

test.describe('Qraft 平台登录 E2E (issue #726)', () => {
  let fixture: ElectronFixture;
  let electronApp: ElectronApplication;
  let page: Page;

  test.beforeAll(async () => {
    storePath = join(tmpdir(), `qraft-e2e-store-${process.pid}.json`);
    process.env[STORE_ENV] = storePath;
    fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
  });

  test.afterAll(async () => {
    delete process.env[STORE_ENV];
    if (electronApp) await closeElectronApp(electronApp, fixture?.miqiHome);
    if (existsSync(storePath)) rmSync(storePath, { force: true });
  });

  test('登录表单渲染：手机号/密码（掩码）/环境/高级设置默认折叠', async () => {
    await gotoQraftTab(page);

    const phoneInput = page.getByTestId('qraft-phone-input');
    const passwordInput = page.getByTestId('qraft-password-input');
    await expect(phoneInput).toBeVisible({ timeout: 15_000 });
    await expect(passwordInput).toBeVisible();
    await expect(passwordInput).toHaveAttribute('type', 'password');
    await expect(page.getByTestId('qraft-login-btn')).toBeVisible();
    await expect(page.getByRole('button', { name: '测试环境' })).toBeVisible();
    await expect(page.getByRole('button', { name: '生产环境' })).toBeVisible();
    // 高级设置默认折叠，展开后出现接入配置输入框
    await expect(page.getByTestId('qraft-baseurl-input')).not.toBeVisible();
    await page.getByText('高级设置（接入配置，默认按环境预填）').click();
    await expect(page.getByTestId('qraft-baseurl-input')).toBeVisible();
    await expect(page.getByTestId('qraft-client-secret-input')).toBeVisible();
  });

  test('登录失败展示分类错误提示（不可达 baseUrl → 网络类错误）', async () => {
    await gotoQraftTab(page);

    await page.getByTestId('qraft-phone-input').fill('18500000000');
    await page.getByTestId('qraft-password-input').fill('not-a-real-password');
    await page.getByText('高级设置（接入配置，默认按环境预填）').click();
    await page.getByTestId('qraft-baseurl-input').fill(TEST_BASE_URL);
    await page.getByTestId('qraft-login-btn').click();

    // 主进程对 192.0.2.1 重试 3 次后失败 → 错误框给出分类提示。
    // 用户可感知结果：错误提示出现且包含网络类文案，而不是空白/崩溃。
    const errorBox = page.getByTestId('qraft-login-error');
    await expect(errorBox).toBeVisible({ timeout: 120_000 });
    const text = (await errorBox.textContent()) ?? '';
    expect(/网络请求失败|网络请求|请检查网络/.test(text)).toBe(true);

    await page.screenshot({
      path: 'test-results/qraft-e2e-login-error.png',
      fullPage: true,
    });
  });

  test('预置登录态展示账号信息，退出登录清空状态与磁盘文件', async () => {
    // 登录态在 service 构造时从磁盘加载 —— 先关掉当前实例，
    // 预置 store 文件后重新启动（走真实持久化读取路径）。
    await closeElectronApp(electronApp, fixture.miqiHome);
    writeFileSync(storePath, buildSeededStoreContent(), 'utf8');

    const f2 = await launchElectronApp();
    electronApp = f2.electronApp;
    page = f2.page;
    fixture = f2;

    await gotoQraftTab(page);

    // 账号信息（nickname/username/脱敏手机号）与 token 到期时间
    await expect(page.getByText('E2E测试账号').first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('已登录')).toBeVisible();
    await expect(page.getByText(/185\*{4}0000/)).toBeVisible();
    await expect(page.getByText('access_token 到期：')).toBeVisible();
    await expect(page.getByTestId('qraft-logout-btn')).toBeVisible();

    // token 文件通道：登录态恢复时同步写入 workspace/.qraft/token.json
    //（供 Skill/agent 读取，仅含 accessToken + expiresAt）
    const tokenFile = join(fixture.miqiHome, 'workspace', '.qraft', 'token.json');
    await expect
      .poll(() => (existsSync(tokenFile) ? readFileSync(tokenFile, 'utf8') : ''), {
        timeout: 10_000,
      })
      .toContain('e2e-fake-access-token');
    expect(JSON.parse(readFileSync(tokenFile, 'utf8'))).not.toHaveProperty('refreshToken');

    // agent 视角：走 agent 文件工具同一条链路（files.read，workspace 相对路径）
    // 读取 token 文件 —— 验证 MiQi agent（Python 后端）确实拿得到 access_token。
    const agentRead = await page.evaluate(async () => {
      try {
        const r: { path?: string; content?: string; size?: number } =
          await (window as any).miqi.files.read('.qraft/token.json');
        return { ok: true, content: r?.content ?? '', size: r?.size ?? 0 };
      } catch (e) {
        return { ok: false, error: String(e) };
      }
    });
    expect(agentRead.ok, `agent 读取 token 文件失败：${JSON.stringify(agentRead)}`).toBe(true);
    expect(agentRead.content).toContain('e2e-fake-access-token');
    expect(agentRead.content).toContain('expiresAt');

    await page.screenshot({
      path: 'test-results/qraft-e2e-logged-in.png',
      fullPage: true,
    });

    // 退出登录：界面回到登录表单，磁盘凭据清空（store 文件与 token 文件）
    // IPC 返回与磁盘写入存在竞态，轮询文件直到为空。
    await page.getByTestId('qraft-logout-btn').click();
    await expect(page.getByTestId('qraft-phone-input')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('qraft-login-btn')).toBeVisible();
    await expect
      .poll(() => (existsSync(storePath) ? readFileSync(storePath, 'utf8') : ''), {
        timeout: 10_000,
      })
      .toBe('');
    await expect.poll(() => existsSync(tokenFile), { timeout: 10_000 }).toBe(false);
  });
});
