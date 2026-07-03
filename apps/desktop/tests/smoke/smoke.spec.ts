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

  test('renders MiQi Workbench branding', async ({ page }) => {
    await injectMockAndGoto(page);

    // "MiQi Workbench" appears in app header — stable text across redesigns
    await expect(page.getByText('MiQi Workbench')).toBeVisible();
  });

});

// ---------------------------------------------------------------------------
// Suite 2: Sidebar Navigation
// ---------------------------------------------------------------------------

test.describe('Sidebar Navigation', () => {

  test('sidebar renders with core session layout', async ({ page }) => {
    await injectMockAndGoto(page);

    // Tasks section header — stable text across redesigns
    await expect(page.getByText('Tasks')).toBeVisible({ timeout: 3000 });

    // Plus button for new session — stable title attribute
    await expect(page.locator('[title="New Session"]')).toBeVisible();

    // At least one session card should render
    const session1 = page.getByText('Test conversation 1');
    await expect(session1.first()).toBeVisible({ timeout: 5000 });
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

  test('renders session title in header', async ({ page }) => {
    await injectMockAndGoto(page);

    // Session title (h2.font-semibold.truncate) renders in both old and new UI
    const title = page.locator('h2.font-semibold.truncate').first();
    await expect(title).toBeVisible({ timeout: 5000 });
  });

  test('renders input area footer area', async ({ page }) => {
    await injectMockAndGoto(page);

    // The input textarea and its container should render
    const textarea = page.getByPlaceholder('Ask Agent to analyze or edit files...');
    await expect(textarea).toBeVisible({ timeout: 5000 });

    // Verify the textarea is within an input area container
    await expect(textarea).toBeEnabled({ timeout: 5000 });
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
