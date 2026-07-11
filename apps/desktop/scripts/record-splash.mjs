import { chromium } from 'playwright';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { existsSync, unlinkSync, renameSync, readdirSync, mkdirSync } from 'fs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, '..', '..', '..');
const splashPath = join(__dirname, '..', 'out/renderer/splash.html');
const videoDir = join(root, 'docs/assets');
const videoPath = join(videoDir, 'splash-demo.webm');
const stillPath = join(videoDir, 'splash-still.png');

mkdirSync(videoDir, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 400, height: 300 },
  recordVideo: {
    dir: videoDir,
    size: { width: 400, height: 300 }
  }
});
const page = await context.newPage();
await page.goto('file:///' + splashPath.replaceAll('\\', '/'), { waitUntil: 'networkidle' });

await page.waitForTimeout(1000);
await page.screenshot({ path: stillPath });
console.log('Still frame captured at 1.0s');

await page.waitForTimeout(1500);

await context.close();

const files = readdirSync(videoDir).filter(f => f.endsWith('.webm'));
const videoFile = files.find(f => f !== 'splash-demo.webm');
if (videoFile) {
  if (existsSync(videoPath)) unlinkSync(videoPath);
  renameSync(join(videoDir, videoFile), videoPath);
  console.log('Video saved to', videoPath);
}
await browser.close();
console.log('Done');
