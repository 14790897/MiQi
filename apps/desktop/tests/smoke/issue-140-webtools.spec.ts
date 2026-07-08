import { expect, test } from '@playwright/test';
import { buildMockBridgeScript } from './mocks';

test.describe('Issue #140 Web search settings', () => {
  test('shows ddgs search options and keeps Ollama only for web fetch', async ({ page }) => {
    await page.addInitScript({ content: buildMockBridgeScript() });
    await page.goto('/');
    await page.waitForSelector('#root', { state: 'visible' });

    await page.getByText('System Settings').click();
    await page.getByRole('tab').filter({ hasText: /Web/ }).click();

    const webSearch = page
      .locator('section')
      .filter({ has: page.getByRole('button', { name: 'DuckDuckGo' }) });
    await expect(webSearch).toBeVisible();
    await expect(webSearch.getByRole('button', { name: 'DuckDuckGo' })).toBeVisible();
    await expect(webSearch.getByRole('button', { name: 'Brave' })).toBeVisible();
    await expect(webSearch.getByRole('button', { name: 'Hybrid' })).toBeVisible();
    await expect(webSearch).not.toContainText('Ollama');

    const webFetch = page
      .locator('section')
      .filter({ has: page.getByRole('button', { name: 'Ollama' }) });
    await expect(webFetch.getByRole('button', { name: 'Ollama' })).toBeVisible();

    await page.screenshot({
      path: 'test-results/issue-140/settings-webtools.png',
      fullPage: true,
    });
  });
});
