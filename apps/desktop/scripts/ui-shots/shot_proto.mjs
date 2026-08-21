import { chromium } from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 820, height: 1600 } });
await page.goto('file:///D:/Desktop/811/MiQi/docs/ui-proto-%E5%8F%82%E8%80%83%E5%9B%BE%E9%A3%8E%E6%A0%BC.html');
await page.waitForTimeout(400);
await page.screenshot({ path: 'D:/Desktop/811/MiQi/docs/ui-proto-参考图风格.png', fullPage: true });
await browser.close();
console.log('OK');
