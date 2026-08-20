/**
 * SkillHub E2E — 技能市场浏览/搜索/安装（Issue #113）
 *
 * 覆盖（test.describe.serial，共享一次 Electron 实例）：
 *   1. 打开技能页 → registry index.json 加载 → 技能卡片显示
 *   2. 搜索过滤 → 只显示匹配技能
 *   3. 安装 → 下载 SKILL.md → 真实 IPC upload → 已安装状态
 *
 * 设计要点（外部评审共识）：
 *   - registry 网络请求用 Playwright route mock（零网络依赖，CI 稳定）
 *   - 安装链路真实 IPC（window.miqi.skills.upload → preload → main → Python）
 *   - 不测搜索之外的下载细节（issue 原文是"技能下载使用测试"）
 *
 * Run:
 *   cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron skillhub.spec.ts
 */
import { test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  launchElectronApp,
  closeElectronApp,
  waitForBridgeInitialized,
} from './helpers/electron-setup';

// mock 的 registry 数据（与 SkillHubPage 的 fetch 路径一致）
const REGISTRY_INDEX = 'https://skills.sixiangjia.de/index.json';
const SKILL_MD = `---
name: e2e-demo-skill
description: E2E 测试用的演示技能
version: 1.0.0
---
# e2e-demo-skill

E2E 测试技能内容。
`;

const FAKE_INDEX = [
  {
    name: 'e2e-demo-skill',
    description: 'E2E 测试用的演示技能',
    version: '1.0.0',
    author: 'e2e',
  },
  {
    name: 'another-e2e-skill',
    description: '另一个测试技能',
    version: '0.2.0',
    author: 'e2e',
  },
];

test.describe.serial('SkillHub E2E (#113)', () => {
  let electronApp: ElectronApplication;
  let page: Page;
  let miqiHome: string;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
    miqiHome = fixture.miqiHome;
    await waitForBridgeInitialized(page, 30);

    // mock registry（在导航到技能页之前设置）
    await page.route('**/skills.sixiangjia.de/index.json', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(FAKE_INDEX),
      }),
    );
    // 搜索端点：按 q 过滤返回
    await page.route('**/skills.sixiangjia.de/api/search?*', (route) => {
      const url = new URL(route.request().url());
      const q = url.searchParams.get('q')?.toLowerCase() ?? '';
      const results = FAKE_INDEX.filter((s) => s.name.includes(q));
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(results),
      });
    });
    await page.route('**/skills.sixiangjia.de/e2e-demo-skill/SKILL.md', (route) =>
      route.fulfill({ status: 200, contentType: 'text/markdown', body: SKILL_MD }),
    );
  }, 120_000);

  test.afterAll(async () => {
    await closeElectronApp(electronApp, miqiHome);
  });

  /** 打开系统设置 → 技能 tab → SkillHub 子页（与 cron spec 相同的导航模式） */
  async function openSkillsPage(p: Page) {
    const settingsBtn = p.locator('[data-testid="nav-system-settings"]');
    await expect(settingsBtn).toBeVisible({ timeout: 15_000 });
    await settingsBtn.click();
    const skillsTab = p.getByRole('tab', { name: /技能/ }).first();
    await expect(skillsTab).toBeVisible({ timeout: 10_000 });
    await skillsTab.click();
    // 技能页有「本地技能」/「SkillHub」两个子 tab，点进 SkillHub
    const hubBtn = p.getByRole('button', { name: 'SkillHub' }).first();
    await expect(hubBtn).toBeVisible({ timeout: 10_000 });
    await hubBtn.click();
    // SkillHub 标题出现（说明已渲染）
    await expect(p.getByRole('heading', { name: 'SkillHub' })).toBeVisible({ timeout: 10_000 });
    // serial 模式共享页面：清空残留搜索词，确保显示完整 registry 列表
    const searchBox = p.getByPlaceholder('搜索技能…');
    if ((await searchBox.inputValue().catch(() => '')) !== '') {
      await searchBox.fill('');
      await expect(p.getByText('e2e-demo-skill').first()).toBeVisible({ timeout: 10_000 });
    }
  }

  test('打开技能页 → registry 技能卡片显示', async () => {
    await openSkillsPage(page);
    // 两个 mock 技能都显示
    await expect(page.getByText('e2e-demo-skill').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('another-e2e-skill').first()).toBeVisible({ timeout: 10_000 });
  });

  test('搜索过滤 → 只显示匹配技能', async () => {
    await openSkillsPage(page);
    await page.getByPlaceholder('搜索技能…').fill('another');
    // e2e-demo-skill 消失，another-e2e-skill 保留
    await expect(page.getByText('e2e-demo-skill').first()).not.toBeVisible({ timeout: 5_000 });
    await expect(page.getByText('another-e2e-skill').first()).toBeVisible({ timeout: 5_000 });
  });

  test('安装技能 → 下载 SKILL.md → 真实 IPC upload → 已安装状态', async () => {
    await openSkillsPage(page);
    // 点第一个技能的「安装」按钮
    const installBtn = page
      .locator('div', { hasText: 'e2e-demo-skill' })
      .getByRole('button', { name: '安装' })
      .first();
    await expect(installBtn).toBeVisible({ timeout: 10_000 });
    await installBtn.click();
    // 安装成功 → 按钮变「已安装」（onSkillInstalled 触发刷新）
    await expect(
      page
        .locator('div', { hasText: 'e2e-demo-skill' })
        .getByText('已安装')
        .first(),
    ).toBeVisible({ timeout: 15_000 });
  });
});
