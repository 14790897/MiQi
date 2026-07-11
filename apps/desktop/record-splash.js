/**
 * Record splash animation video using Playwright Chromium.
 * Renders splash.html at 400x300, records ~2s of animation.
 */
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

(async () => {
  const outDir = path.resolve(__dirname, 'test-results');
  fs.mkdirSync(outDir, { recursive: true });

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 400, height: 300 },
    recordVideo: {
      dir: outDir,
      size: { width: 400, height: 300 },
    },
  });
  const page = await context.newPage();

  const filePath = path.resolve(__dirname, 'out/renderer/splash.html');
  await page.goto('file:///' + filePath.replace(/\\/g, '/'));

  // Wait for the full animation cycle: fadeIn(0.3) + breathe(1.2) = 1.5s + buffer
  await page.waitForTimeout(2500);

  await context.close();
  await browser.close();

  // Find the generated video and rename it
  const videos = fs.readdirSync(outDir).filter(f => f.endsWith('.webm'));
  if (videos.length > 0) {
    const src = path.join(outDir, videos[0]);
    const dst = path.resolve(__dirname, 'docs/assets/splash-demo.webm');
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    fs.copyFileSync(src, dst);
    console.log(`Video saved: ${dst} (${fs.statSync(dst).size} bytes)`);
  }
})();
