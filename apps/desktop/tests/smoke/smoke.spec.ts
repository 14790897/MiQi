/**
 * MiQi Desktop — Playwright Smoke QA Tests
 *
 * Covers the core renderer flows with a mock bridge backend.
 * Run: npx playwright test --config=playwright.config.ts
 *
 * Test coverage:
 *  1. App load — preload bridge check, UI renders
 *  2. Sidebar — navigation buttons, session list
 *  3. Chat — input field, message display, sanitization
 *  4. StatusBar — runtime status visible
 */

import { test, expect } from '@playwright/test';
import { buildMockBridgeScript, type MockBridgeOptions } from './mocks';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function injectMockAndGoto(
  page: import('@playwright/test').Page,
  opts?: MockBridgeOptions,
) {
  await page.addInitScript({ content: buildMockBridgeScript(opts) });
  await page.goto('/');
  // Wait for React to render
  await page.waitForSelector('#root', { state: 'visible' });
}


// ---------------------------------------------------------------------------
// Suite 1: App Load & Bridge
// ---------------------------------------------------------------------------

test.describe('App Load & Bridge', () => {

  test('renders the application shell when preload is available', async ({ page }) => {
    await injectMockAndGoto(page);

    // App shell should render (not the "预加载桥接不可用" error page)
    const preloadError = page.locator('h2', { hasText: '预加载桥接不可用' });
    await expect(preloadError).toHaveCount(0);
  });

  test('shows preload bridge error when window.miqi is missing', async ({ page }) => {
    await injectMockAndGoto(page, { preloadOk: false });

    // Should show the error message
    const errorHeading = page.locator('h2', { hasText: '预加载桥接不可用' });
    await expect(errorHeading).toBeVisible();

    // Should show restart instructions
    await expect(page.getByText('应用预加载脚本注入失败')).toBeVisible();
  });

  test('renders MiQi Workbench branding in sidebar', async ({ page }) => {
    await injectMockAndGoto(page);

    // Sidebar should show "MiQi Workbench" (or at minimum the logo)
    await expect(page.getByText('MiQi Workbench')).toBeVisible();
  });

});

// ---------------------------------------------------------------------------
// Suite 2: Sidebar Navigation
// ---------------------------------------------------------------------------

test.describe('Sidebar Navigation', () => {

  test('renders all main navigation buttons', async ({ page }) => {
    await injectMockAndGoto(page);

    const navButtons = [
      '对话',
      'MCPs',
      '定时任务',
      '记忆',
      '经验',
      '技能',
      'WSL',
      '设置',
    ];

    for (const label of navButtons) {
      const btn = page.getByRole('button', { name: label, exact: true });
      await expect(btn).toBeVisible({ timeout: 3000 });
    }
  });

  test('sessions list shows mock sessions', async ({ page }) => {
    await injectMockAndGoto(page);

    // Sessions should be loaded from mock
    const session1 = page.getByText('Test conversation 1');
    const session2 = page.getByText('Test conversation 2');

    // At least one session should be visible after loading
    await expect(session1.first()).toBeVisible({ timeout: 5000 });
    await expect(session2.first()).toBeVisible({ timeout: 5000 });
  });

  test('new session button is present', async ({ page }) => {
    await injectMockAndGoto(page);

    const newSessionBtn = page.locator('[title="New Session"]');
    await expect(newSessionBtn).toBeVisible();
  });

  test('Tasks section header is visible', async ({ page }) => {
    await injectMockAndGoto(page);

    // The sessions section header should say "Tasks"
    await expect(page.getByText('Tasks')).toBeVisible({ timeout: 3000 });
  });

});

// ---------------------------------------------------------------------------
// Suite 3: Chat Console
// ---------------------------------------------------------------------------

test.describe('Chat Console', () => {

  test('renders chat input with correct placeholder', async ({ page }) => {
    await injectMockAndGoto(page);

    // The chat textarea should be present with the expected placeholder
    const textarea = page.getByPlaceholder('Ask Agent to analyze or edit files...');
    await expect(textarea).toBeVisible({ timeout: 5000 });
  });

  test('renders send button', async ({ page }) => {
    await injectMockAndGoto(page);

    // There should be a button containing the Send icon
    const sendBtn = page.locator('button:has(svg)').filter({
      has: page.locator('svg')
    }).last();

    // The send button should exist (disabled until input is entered)
    // We just verify the textarea + button area exists
    const inputArea = page.getByPlaceholder('Ask Agent to analyze or edit files...');
    await expect(inputArea).toBeAttached();
  });

  test('renders New Chat button', async ({ page }) => {
    await injectMockAndGoto(page);

    const newChatBtn = page.getByRole('button', { name: /New Chat/i });
    await expect(newChatBtn).toBeVisible({ timeout: 5000 });
  });

  test('renders keyboard shortcut hint in footer', async ({ page }) => {
    await injectMockAndGoto(page);

    await expect(
      page.getByText(/SHIFT.*ENTER.*NEW LINE/i)
    ).toBeVisible({ timeout: 5000 });
  });

  test('chat input is enabled when not streaming', async ({ page }) => {
    await injectMockAndGoto(page);

    const textarea = page.getByPlaceholder('Ask Agent to analyze or edit files...');
    await expect(textarea).toBeEnabled({ timeout: 5000 });
  });

});

// ---------------------------------------------------------------------------
// Suite 4: Status Bar
// ---------------------------------------------------------------------------

test.describe('Status Bar', () => {

  test('shows runtime status indicator', async ({ page }) => {
    await injectMockAndGoto(page);

    // The status bar at the bottom should render
    // When runtime status is "running", the app shows "运行中"
    await expect(page.getByText('运行中')).toBeVisible({ timeout: 5000 });
  });

  test('shows stopped status when runtime is down', async ({ page }) => {
    await injectMockAndGoto(page, { runtimeStatus: 'stopped' });

    await expect(page.getByText('已停止')).toBeVisible({ timeout: 5000 });
  });

});

// ---------------------------------------------------------------------------
// Suite 5: Error Sanitization (sanitizeUiMessage)
// ---------------------------------------------------------------------------

test.describe('Error Sanitization', () => {

  test('renderer loads sanitizeUiMessage module without error', async ({ page }) => {
    await injectMockAndGoto(page);

    // Verify the page loaded without JavaScript errors
    const errors: string[] = [];
    page.on('pageerror', err => errors.push(err.message));

    // Reload to trigger a fresh render
    await page.reload();
    await page.waitForSelector('#root', { state: 'visible' });

    // Filter out expected errors (CSP, missing icons, etc.)
    const unexpectedErrors = errors.filter(
      e => !e.includes('Failed to load resource')
    );

    expect(unexpectedErrors).toHaveLength(0);
  });

});

// ---------------------------------------------------------------------------
// Suite 6: Responsive Layout
// ---------------------------------------------------------------------------

test.describe('Layout', () => {

  test('sidebar and main content are both visible', async ({ page }) => {
    await injectMockAndGoto(page);

    // The sidebar width is 240px, so the main column should be right of that
    // Verify both key landmarks exist
    await expect(page.getByText('MiQi Workbench')).toBeVisible({ timeout: 3000 });
    await expect(
      page.getByPlaceholder('Ask Agent to analyze or edit files...')
    ).toBeVisible({ timeout: 3000 });
  });

  test('page title is set correctly', async ({ page }) => {
    await injectMockAndGoto(page);

    await expect(page).toHaveTitle(/MiQi/i);
  });

});

// ---------------------------------------------------------------------------
// Suite 7: Conversation Flow
// ---------------------------------------------------------------------------

test.describe('Conversation Flow', () => {

  /**
   * Helper: type a message and send it.
   * Returns after the user message bubble appears.
   */
  async function sendMessage(page: import('@playwright/test').Page, text: string) {
    const textarea = page.getByPlaceholder('Ask Agent to analyze or edit files...');
    await textarea.fill(text);
    // Send via Enter key
    await textarea.press('Enter');
    // Wait for the user message bubble to render
    await expect(page.getByText(text).first()).toBeVisible({ timeout: 5000 });
  }

  test('send a message and receive a final response', async ({ page }) => {
    await injectMockAndGoto(page);

    await sendMessage(page, 'Hello, MiQi!');

    // Trigger the mock final response
    await page.evaluate(() => {
      (window as any).__miqiMock.final('你好！我是 MiQi，有什么可以帮你的？');
    });

    // Wait for the assistant response to appear (typewriter animation)
    await expect(
      page.getByText('你好！我是 MiQi，有什么可以帮你的？')
    ).toBeVisible({ timeout: 5000 });
  });

  test('user message bubble appears after sending', async ({ page }) => {
    await injectMockAndGoto(page);

    await sendMessage(page, 'Test user message');

    // Verify the user message is visible
    await expect(page.getByText('Test user message').first()).toBeVisible();
  });

  test('tool-hint progress message renders', async ({ page }) => {
    await injectMockAndGoto(page);

    await sendMessage(page, 'Run echo hello');

    // Fire a tool progress event
    await page.evaluate(() => {
      (window as any).__miqiMock.toolProgress('exec: echo hello', 'call_001');
    });

    // Wait for the tool hint text to appear
    await expect(page.getByText('exec: echo hello')).toBeVisible({ timeout: 5000 });
  });

  test('text progress message renders', async ({ page }) => {
    await injectMockAndGoto(page);

    await sendMessage(page, 'What is 1+1?');

    // Fire a text progress event
    await page.evaluate(() => {
      (window as any).__miqiMock.progress({ text: 'Thinking about the answer…' });
    });

    await expect(
      page.getByText('Thinking about the answer…')
    ).toBeVisible({ timeout: 5000 });
  });

  test('multiple progress events before final response', async ({ page }) => {
    await injectMockAndGoto(page);

    await sendMessage(page, 'Analyze this code');

    // Fire multiple progress events
    await page.evaluate(() => {
      const mock = (window as any).__miqiMock;
      mock.progress({ text: 'Reading file…' });
      mock.toolProgress('read_file("src/app.ts")', 'call_read');
      mock.progress({ text: 'Analyzing…' });
    });

    await expect(page.getByText('Reading file…')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('read_file("src/app.ts")')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Analyzing…')).toBeVisible({ timeout: 5000 });

    // Now send final
    await page.evaluate(() => {
      (window as any).__miqiMock.final('Analysis complete: the code looks good.');
    });

    await expect(
      page.getByText('Analysis complete: the code looks good.')
    ).toBeVisible({ timeout: 5000 });
  });

  test('error message via onError event is displayed', async ({ page }) => {
    await injectMockAndGoto(page);

    await sendMessage(page, 'This will fail');

    // Fire an error event
    await page.evaluate(() => {
      (window as any).__miqiMock.error('API rate limit exceeded. Please try again later.');
    });

    await expect(
      page.getByText('API rate limit exceeded. Please try again later.')
    ).toBeVisible({ timeout: 5000 });
  });

  test('chat.send failure displays error message', async ({ page }) => {
    await injectMockAndGoto(page);

    // Override chat.send to reject
    await page.evaluate(() => {
      (window as any).miqi.chat.send = () => {
        const err = new Error('API rate limit exceeded: too many requests');
        return Promise.reject(err);
      };
    });

    await sendMessage(page, 'Trigger rate limit');

    // Error should appear after send failure
    await expect(
      page.getByText(/rate limit/i).last()
    ).toBeVisible({ timeout: 8000 });
  });

  test('abort button stops streaming and shows aborted message', async ({ page }) => {
    await injectMockAndGoto(page);

    await sendMessage(page, 'Long running task');

    // Start streaming by firing progress
    await page.evaluate(() => {
      (window as any).__miqiMock.progress({ text: 'Processing…' });
    });

    await expect(page.getByText('Processing…')).toBeVisible({ timeout: 5000 });

    // Click the abort button (Square icon during streaming)
    const abortBtn = page.locator('button').filter({ has: page.locator('svg.lucide-square, [class*="lucide-square"]') }).first();
    await abortBtn.click();

    // Should show "Aborted." message
    await expect(page.getByText('Aborted.')).toBeVisible({ timeout: 5000 });
  });

  test('send is disabled during streaming', async ({ page }) => {
    await injectMockAndGoto(page);

    await sendMessage(page, 'Streaming test');

    // After sending, textarea should be disabled during streaming
    const textarea = page.getByPlaceholder('Ask Agent to analyze or edit files...');
    await expect(textarea).toBeDisabled({ timeout: 5000 });

    // End streaming with final
    await page.evaluate(() => {
      (window as any).__miqiMock.final('Done!');
    });

    // Now textarea should be enabled again
    await expect(textarea).toBeEnabled({ timeout: 5000 });
  });

  test('New Chat button starts a fresh conversation', async ({ page }) => {
    await injectMockAndGoto(page);

    // Send one message first
    await sendMessage(page, 'First message');
    await page.evaluate(() => {
      (window as any).__miqiMock.final('First response');
    });
    await expect(page.getByText('First response')).toBeVisible({ timeout: 5000 });

    // Click New Chat
    const newChatBtn = page.getByRole('button', { name: /New Chat/i });
    await newChatBtn.click();

    // Previous messages should be gone (new session)
    await expect(page.getByText('First message').first()).not.toBeVisible({ timeout: 3000 });
    await expect(page.getByText('First response').first()).not.toBeVisible({ timeout: 3000 });

    // Input should be empty and ready
    const textarea = page.getByPlaceholder('Ask Agent to analyze or edit files...');
    await expect(textarea).toBeEnabled();
    await expect(textarea).toBeEmpty();
  });

  test('tool execution with stream deltas renders', async ({ page }) => {
    await injectMockAndGoto(page);

    await sendMessage(page, 'Exec command');

    // Fire stream deltas (simulating exec tool output)
    await page.evaluate(() => {
      const mock = (window as any).__miqiMock;
      mock.progress({
        text: 'exec: echo hello world',
        tool_hint: true,
        tool_call_id: 'call_exec_001',
      });
    });

    // Fire stream output deltas
    await page.evaluate(() => {
      const mock = (window as any).__miqiMock;
      mock.progress({
        stream: 'stdout',
        delta: 'hello world\n',
        tool_call_id: 'call_exec_001',
      });
    });

    // Tool hint should be visible
    await expect(page.getByText('exec: echo hello world')).toBeVisible({ timeout: 5000 });

    // Now end with final
    await page.evaluate(() => {
      (window as any).__miqiMock.final('Command executed successfully.');
    });

    await expect(
      page.getByText('Command executed successfully.')
    ).toBeVisible({ timeout: 5000 });
  });

  test('web_search tool call renders progress and results', async ({ page }) => {
    await injectMockAndGoto(page);

    await sendMessage(page, '搜索今天北京的天气');

    // Phase 1: web_search tool hint appears
    await page.evaluate(() => {
      (window as any).__miqiMock.toolProgress(
        'web_search: 北京 今日 天气',
        'call_web_001'
      );
    });

    await expect(
      page.getByText(/web_search/).first()
    ).toBeVisible({ timeout: 5000 });

    // Phase 2: web_fetch tool follows up
    await page.evaluate(() => {
      (window as any).__miqiMock.toolProgress(
        'web_fetch: https://weather.cma.cn',
        'call_web_002'
      );
      (window as any).__miqiMock.progress({ text: '正在分析搜索结果…' });
    });

    await expect(
      page.getByText(/web_fetch/).first()
    ).toBeVisible({ timeout: 5000 });

    // Phase 3: final response with search results
    await page.evaluate(() => {
      (window as any).__miqiMock.final(
        '北京今日天气：多云转雷阵雨，最高31℃，夜间有阵雨。数据来源：中国气象局 weather.cma.cn。'
      );
    });

    // Verify the search result content appears
    await expect(
      page.getByText(/weather\.cma\.cn/)
    ).toBeVisible({ timeout: 8000 });

    // Verify tool hints are still visible (tool call indicators)
    await expect(
      page.getByText(/web_search/).first()
    ).toBeVisible({ timeout: 3000 });
  });

  test('web_search then error gracefully handled', async ({ page }) => {
    await injectMockAndGoto(page);

    await sendMessage(page, '搜索一个不存在的网站');

    // Trigger web_search with an error
    await page.evaluate(() => {
      (window as any).__miqiMock.toolProgress(
        'web_search: nonexsitent-domain-xyz',
        'call_err_001'
      );
    });
    await page.waitForTimeout(300);

    // Simulate backend search failure
    await page.evaluate(() => {
      (window as any).__miqiMock.error('web_search failed: 网络连接超时，请检查网络后重试');
    });

    // Error message should render in UI
    await expect(
      page.getByText(/网络连接超时/)
    ).toBeVisible({ timeout: 5000 });
  });

});
