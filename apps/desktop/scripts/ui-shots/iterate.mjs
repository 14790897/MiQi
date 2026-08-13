/**
 * 确认卡 UI 迭代循环：截图 → Kimi 评审 → 输出建议（供自动/手动改进）
 * 网络恢复后运行: node scripts/ui-shots/iterate.mjs
 * 每次跑: 重新截图 + 调 Kimi 评审 + 保存评审结果 JSON
 */
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execSync } from 'node:child_process';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const outDir = resolve(join(__dirname, 'shots'));
mkdirSync(outDir, { recursive: true });

// 1. 重新 bundle（组件有改动时）
try {
  execSync('npx esbuild scripts/ui-shots/showcase.tsx --bundle --format=iife --jsx=automatic --loader:.tsx=tsx --outfile=scripts/ui-shots/showcase.bundle.js', { cwd: join(__dirname, '..', '..'), stdio: 'pipe' });
  console.log('bundle 完成');
} catch (e) { console.log('bundle 跳过:', e.message?.split('\n')[0]); }

// 2. 截图
const url = `file:///${join(__dirname, 'showcase.html').replace(/\\/g, '/')}`;
const scenes = ['pending', 'steps', 'confirmed', 'cancelled', 'timedout'];
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 860, height: 1400 }, deviceScaleFactor: 2 });
await page.goto(url);
await page.waitForSelector('[data-scene="pending"]');
for (const scene of scenes) {
  const el = page.locator(`[data-scene="${scene}"]`);
  await el.scrollIntoViewIfNeeded();
  await el.screenshot({ path: join(outDir, `card-${scene}.png`) });
}
await page.screenshot({ path: join(outDir, 'card-all.png'), fullPage: true });
await browser.close();
console.log('截图完成:', scenes.join(', '));

// 3. Kimi 评审
const review = execSync('python scripts/ui-shots/review_kimi.py', { cwd: __dirname, encoding: 'utf-8', timeout: 300 });
writeFileSync(join(outDir, 'review-latest.txt'), review);
console.log('\n===== Kimi 评审 =====\n');
console.log(review.slice(0, 3000));
