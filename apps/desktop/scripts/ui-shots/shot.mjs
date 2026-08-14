/**
 * 确认卡 UI 截图脚本（Kimi 视觉评审管道）
 * 用法: node scripts/ui-shots/shot.mjs <输出目录>
 * 逐个场景截图: pending / steps / confirmed / cancelled / timedout
 */
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const outDir = resolve(process.argv[2] || join(__dirname, 'shots'));
mkdirSync(outDir, { recursive: true });

const url = `file:///${join(__dirname, 'showcase.html').replace(/\\/g, '/')}`;
const scenes = ['pending', 'steps', 'confirmed', 'cancelled', 'timedout'];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 860, height: 1400 }, deviceScaleFactor: 2 });
await page.goto(url);
await page.waitForSelector('[data-scene="pending"]');

for (const scene of scenes) {
  const el = page.locator(`[data-scene="${scene}"]`);
  await el.scrollIntoViewIfNeeded();
  const file = join(outDir, `card-${scene}.png`);
  await el.screenshot({ path: file });
  console.log('shot:', file);
}

// 整页（全部场景同框，给 Kimi 看整体布局）
const full = join(outDir, 'card-all.png');
await page.screenshot({ path: full, fullPage: true });
console.log('shot:', full);

await browser.close();
