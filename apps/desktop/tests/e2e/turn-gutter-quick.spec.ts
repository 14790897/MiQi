import { test, _electron as electron } from '@playwright/test';
import type { Page } from '@playwright/test';
import { createServer } from 'node:http';
import { resolve } from 'node:path';
import { tmpdir, homedir } from 'node:os';
import { mkdtempSync, existsSync, cpSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const MOCK_PORT = 9876;

function startMockLLM(): Promise<{ close: () => void }> {
  const server = createServer((req, res) => {
    let body = '';
    req.on('data', (c) => (body += c));
    req.on('end', () => {
      if (req.url?.includes('/chat/completions')) {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          id: 'm', object: 'chat.completion', created: 0, model: 'mock-model',
          choices: [{ index: 0, message: { role: 'assistant', content: 'mock 回答，测试珠子。' }, finish_reason: 'stop' }],
          usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
        }));
      } else { res.writeHead(404); res.end(); }
    });
  });
  return new Promise((r) => server.listen(MOCK_PORT, '127.0.0.1', () => r({ close: () => server.close() })));
}

test('珠子快速验证：2 轮对话', async () => {
  test.setTimeout(600_000);
  const mock = await startMockLLM();
  const miqiHome = mkdtempSync(join(tmpdir(), 'miqi-beads2-'));
  const srcCfg = join(homedir(), '.miqi', 'config.json');
  const dstCfg = join(miqiHome, 'config.json');
  if (existsSync(srcCfg)) cpSync(srcCfg, dstCfg);
  const cfg = existsSync(dstCfg) ? JSON.parse(readFileSync(dstCfg, 'utf-8')) : {};
  cfg.approvals = { ...(cfg.approvals ?? {}), bypass_all: true };
  cfg.channels = { ...(cfg.channels ?? {}), feishu: { enabled: false }, feedback: { enabled: false } };
  cfg.providers = { ...(cfg.providers ?? {}), custom: { api_key: 'no-key', api_base: `http://127.0.0.1:${MOCK_PORT}/v1` } };
  cfg.agents = { ...(cfg.agents ?? {}), defaults: { ...(cfg.agents?.defaults ?? {}), model: 'custom/mock-model' } };
  writeFileSync(dstCfg, JSON.stringify(cfg, null, 2));
  const env: Record<string, string | undefined> = { ...process.env };
  env.MIQI_HOME = miqiHome;
  delete env.ELECTRON_RUN_AS_NODE;

  const electronApp = await electron.launch({
    args: [resolve(__dirname, '../..')],
    executablePath: require('electron') as string,
    env: env as Record<string, string>,
    chromiumSandbox: false,
  });
  let page: Page | null = null;
  for (let i = 0; i < 100; i++) {
    for (const w of electronApp.windows()) {
      try {
        const info = await w.evaluate(() => ({ t: document.title, w: window.outerWidth }));
        if (info.w > 500 && info.t === 'MiQi Desktop') { page = w; break; }
      } catch {}
    }
    if (page) break;
    await new Promise((r) => setTimeout(r, 100));
  }
  if (!page) page = await electronApp.firstWindow();
  await page.waitForLoadState('domcontentloaded');
  await page.locator('[data-testid="chat-input-container"] textarea').first().waitFor({ timeout: 90_000 });

  const qs = ['问题一：什么是闭包？', '问题二：写一个快速排序', '问题三：解释HTTPS', '问题四：什么是区块链？', '问题五：写个防抖函数', '问题六：解释TCP三次握手', '问题七：什么是依赖注入？', '问题八：写个二分查找'];
  for (let i = 0; i < qs.length; i++) {
    const box = page.locator('[data-testid="chat-input-container"] textarea').first();
    await box.fill(qs[i]);
    await box.press('Enter');
    await page.waitForTimeout(9000);
  }
  await page.waitForTimeout(3000);

  const diag = await page.evaluate(() => ({
    winW: window.innerWidth,
    colTop: (() => {
      const c = document.querySelector('.turn-gutter');
      if (!c) return null;
      const r = c.getBoundingClientRect();
      return { top: Math.round(r.top), bottom: Math.round(r.bottom), h: Math.round(r.height) };
    })(),
    topbar: (() => {
      // 找 TopBar（顶部条）：含 --topbar-bg 或 h-10 的 div
      const all = [...document.querySelectorAll('div')];
      const tb = all.find((d) => {
        const r = d.getBoundingClientRect();
        return r.width > window.innerWidth * 0.9 && r.height <= 48 && r.top <= 5;
      });
      if (!tb) return null;
      const r = tb.getBoundingClientRect();
      return { top: Math.round(r.top), bottom: Math.round(r.bottom), h: Math.round(r.height), w: Math.round(r.width) };
    })(),
    aboveCol: (() => {
      const c = document.querySelector('.turn-gutter');
      if (!c) return null;
      const r = c.getBoundingClientRect();
      const el = document.elementFromPoint(r.left + 10, r.top - 20);
      return el ? (el.className ? String(el.className).slice(0, 60) : el.tagName) : null;
    })(),
    beadRight: (() => {
      const b = document.querySelector('.turn-gutter button');
      if (!b) return null;
      const r = b.getBoundingClientRect();
      return Math.round(window.innerWidth - r.right);
    })(),
    gutter: !!document.querySelector('.turn-gutter'),
    beads: document.querySelectorAll('.turn-gutter button').length,
    bubbles: document.querySelectorAll('[data-message-body]').length,
    msgs: document.querySelectorAll('[data-turn-idx]').length,
    roles: [...document.querySelectorAll('[data-turn-role]')].slice(0, 4).map((e) => e.getAttribute('data-turn-role')),
    gutterTop: document.querySelector('.turn-gutter') ? (document.querySelector('.turn-gutter') as HTMLElement).style.top : null,
  }));
  console.log('[beads2] 诊断:', JSON.stringify(diag));

  // 多状态截图（供 kimi 多模态审查）
  // 1) 初始刻度条（8 轮后）
  await page.screenshot({ path: 'beads-1-initial.png' });

  // 2) hover 第 1 颗珠子 → 预览弹窗
  const beads = page.locator('.turn-gutter button');
  const n = await beads.count();
  console.log('[beads2] 珠子数:', n);
  if (n > 0) {
    await beads.first().hover();
    await page.waitForTimeout(600);
    await page.screenshot({ path: 'beads-2-hover-first.png' });
    // 3) hover 中间珠子
    if (n > 2) {
      await beads.nth(Math.floor(n / 2)).hover();
      await page.waitForTimeout(600);
      await page.screenshot({ path: 'beads-3-hover-mid.png' });
    }
    // 4) 点击第 3 颗 → 跳转
    if (n > 2) {
      await beads.nth(2).click();
      await page.waitForTimeout(900);
      await page.screenshot({ path: 'beads-4-click-jump.png' });
    }
  }
  // 5) 滚动到底部
  await page.evaluate(() => {
    const sc = document.querySelector('.overflow-y-auto');
    if (sc) sc.scrollTop = sc.scrollHeight;
  });
  await page.waitForTimeout(800);
  await page.screenshot({ path: 'beads-5-scroll-bottom.png' });

  await page.screenshot({ path: 'turn-gutter-v2.png' });
  await electronApp.close();
  mock.close();
});
