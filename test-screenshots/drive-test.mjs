// Smoke test: drive the MiQi mode selector + approval settings
import { chromium } from 'playwright-core';
import { mkdirSync } from 'fs';

(async () => {
  mkdirSync('d:/Desktop/mode/MiQi/test-screenshots', { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: false });
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1280, height: 800 });

  // Try each possible port
  let url = null;
  for (const port of [5173, 5174, 5175, 5176]) {
    try {
      await page.goto(`http://localhost:${port}`, { timeout: 3000 });
      url = `http://localhost:${port}`;
      break;
    } catch {}
  }
  if (!url) { console.log('No dev server found'); process.exit(1); }
  console.log('Connected to:', url);
  await page.waitForTimeout(3000);

  const shot = async (name) => {
    const p = `d:/Desktop/mode/MiQi/test-screenshots/${name}`;
    await page.screenshot({ path: p });
    console.log('Screenshot:', name);
    return p;
  };

  await shot('00-initial.png');

  // Click mode selector
  const modeBtn = page.locator('button').filter({ hasText: /规划|手动|允许编辑|自动/ }).first();
  await modeBtn.click();
  await page.waitForTimeout(500);
  await shot('01-mode-dropdown.png');

  // Click 规划
  await page.getByText('规划', { exact: true }).first().click();
  await page.waitForTimeout(500);
  await shot('02-mode-plan.png');

  // Click 允许编辑
  await modeBtn.click();
  await page.waitForTimeout(300);
  await page.getByText('允许编辑', { exact: true }).first().click();
  await page.waitForTimeout(500);
  await shot('03-mode-edit.png');

  // Dropdown again for compact view
  await modeBtn.click();
  await page.waitForTimeout(500);
  await shot('04-mode-dropdown-compact.png');

  // Click 审批设置
  const approvalBtn = page.getByText('审批设置').first();
  if (await approvalBtn.isVisible()) {
    await approvalBtn.click();
    await page.waitForTimeout(1500);
    await shot('05-approvals-page.png');
  }

  // Keyboard shortcuts
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  await page.keyboard.press('1');
  await page.waitForTimeout(500);
  await shot('06-keyboard-1-plan.png');

  await page.keyboard.press('3');
  await page.waitForTimeout(500);
  await shot('07-keyboard-3-edit.png');

  // Toast
  await modeBtn.click();
  await page.waitForTimeout(300);
  await page.getByText('手动', { exact: true }).first().click();
  await page.waitForTimeout(300);
  await shot('08-toast.png');

  // Auto confirm dialog
  await page.keyboard.press('4');
  await page.waitForTimeout(500);
  await shot('09-auto-confirm.png');

  await page.getByText('取消').last().click();
  await page.waitForTimeout(300);

  console.log('\nAll done!');
  await browser.close();
})();
