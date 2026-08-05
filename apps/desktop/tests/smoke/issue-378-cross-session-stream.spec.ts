/**
 * Issue #378: cross-session streaming must preserve assistant content.
 *
 * Run: cd apps/desktop && npx playwright test --project=smoke -g "#378"
 */
import { test, expect, type Page } from '@playwright/test';
import { buildMockBridgeScript } from './mocks';

const SA = 'desktop:issue378-A';
const SB = 'desktop:issue378-B';
const QA = 'QUESTION_A';
const QB = 'QUESTION_B';

async function boot(page: Page, initial: string) {
  await page.addInitScript({ content: `localStorage.setItem('miqi:lastSession','${initial}')` });
  await page.addInitScript({
    content: buildMockBridgeScript({
      providers: [{ configured: true }],
      sessions: [
        { key: SA, title: 'Session A', updated_at: Date.now(), message_count: 1 },
        { key: SB, title: 'Session B', updated_at: Date.now(), message_count: 1 },
      ],
      sessionMessages: {
        [SA]: [{ role: 'user', content: QA }],
        [SB]: [{ role: 'user', content: QB }],
      },
    }),
  });
  await page.goto('/');
  await expect(page.locator('[data-testid="chat-input-container"] textarea')).toBeEnabled({ timeout: 10_000 });
}

async function send(page: Page, text: string) {
  const ta = page.locator('[data-testid="chat-input-container"] textarea');
  await ta.click(); await ta.fill(''); await ta.type(text); await ta.press('Enter');
  await expect(page.getByText(text).first()).toBeVisible({ timeout: 5_000 });
}

async function fireProgress(page: Page, sk: string, text: string) {
  await page.evaluate(({ sk, t }) => {
    (window as any).__miqiMock.progress({ session_key: sk, text: t, delta: t, tool_hint: false });
  }, { sk, t: text });
}

async function fireFinal(page: Page, sk: string, content: string) {
  await page.evaluate(({ sk, c }) => {
    (window as any).__miqiMock._fireFinalWithSession?.(sk, c) ??
      (window as any).__miqiMock.rawFinal?.(c);
  }, { sk, c: content });
}

async function switchSession(page: Page, title: string) {
  const btn = page.getByRole('button', { name: title }).first();
  await expect(btn).toBeVisible({ timeout: 5_000 });
  await btn.click();
}

test.describe('#378 cross-session streaming', () => {
  test('switch mid-stream and back — reply visible without refresh', async ({ page }) => {
    await boot(page, SA);
    await send(page, QA);
    await fireProgress(page, SA, 'Cats are curious creatures');
    await page.getByText(/Cats are curious/).first().waitFor({ state: 'visible', timeout: 5_000 });

    await switchSession(page, 'Session B');
    await fireProgress(page, SA, ' who often nap in sunbeams');
    await switchSession(page, 'Session A');
    await page.waitForTimeout(200);
    await expect(page.locator('body').getByText(/nap in sunbeams/).first()).toBeVisible({ timeout: 5_000 });
  });

  test('final arrives while on other session — reply persists on return', async ({ page }) => {
    await boot(page, SA);
    await send(page, QA);
    await fireProgress(page, SA, 'Cats are curious creatures who often nap in sunbeams. The end.');
    await page.getByText(/nap in sunbeams/).first().waitFor({ state: 'visible', timeout: 5_000 });

    await switchSession(page, 'Session B');
    // final fires for A while B is visible
    await fireFinal(page, SA, 'Cats are curious creatures who often nap in sunbeams. The end.');
    await switchSession(page, 'Session A');
    await page.waitForTimeout(200);
    await expect(page.getByText(/nap in sunbeams/).first()).toBeVisible({ timeout: 5_000 });
  });

  test('orphan final (no session_key) routes to the only in-flight stream', async ({ page }) => {
    await boot(page, SA);
    await send(page, QA);
    await fireProgress(page, SA, 'thinking…');
    await switchSession(page, 'Session B');
    // final WITHOUT session_key — must route to A (the only in-flight stream)
    await page.evaluate(() => (window as any).__miqiMock.rawFinal?.('Cats are curious creatures who often nap in sunbeams. The end.'));
    await switchSession(page, 'Session A');
    await page.waitForTimeout(200);
    await expect(page.getByText(/nap in sunbeams/).first()).toBeVisible({ timeout: 5_000 });
  });
});
