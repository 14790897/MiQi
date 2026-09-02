import { expect, test } from '@playwright/test';
import { buildMockBridgeScript } from './mocks';

async function injectMockAndGoto(
  page: import('@playwright/test').Page,
  opts?: Parameters<typeof buildMockBridgeScript>[0]
) {
  // Privacy gate (#837) reads localStorage before the app mounts — pre-consent
  // so the chat screen is reachable without scrolling the agreement.
  await page.addInitScript({
    content: `localStorage.setItem('miqi:privacyConsentVersion', '1.0');`,
  });
  await page.addInitScript({
    content: buildMockBridgeScript({
      // A configured provider lets the send path pass its guard.
      providers: [{ id: 'openrouter', name: 'OpenRouter', configured: true }],
      activeModel: 'model-x',
      activeProvider: 'openrouter',
      ...opts,
    }),
  });
  await page.goto('/');
  await page.waitForSelector('#root', { state: 'visible' });
}

test.describe('Issue #902 exec command expand', () => {
  test('clicking an exec tool row expands to the full untruncated command', async ({ page }) => {
    await injectMockAndGoto(page);

    const textarea = page.getByPlaceholder('请输入消息或拖入文件...');
    await expect(textarea).toBeVisible({ timeout: 5000 });
    await textarea.fill('run a long command');
    await textarea.press('Enter');

    // Long command (> 60 chars) so the collapsed summary truncates and only
    // the expanded block reveals the full text.
    const longCommand =
      'echo "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron" | tr -d " " | wc -c';
    await page.evaluate((cmd) => {
      (window as any).__miqiMock.progress({
        text: 'exec("echo alpha beta …")',
        tool_hint: true,
        tool_call_id: 'call_902_1',
        tool_args: { command: cmd },
      });
    }, longCommand);

    const label = page.getByRole('button', { name: /执行命令/ });
    await expect(label).toBeVisible({ timeout: 5000 });
    // Collapsed summary is truncated — the full command is not on screen yet.
    await expect(page.getByText(longCommand)).toHaveCount(0);

    await label.click();
    await expect(page.getByText(longCommand)).toBeVisible();
  });
});
