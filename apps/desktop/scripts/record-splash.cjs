const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");

const outDir = path.resolve(__dirname, "..", "out", "renderer");
const splashPath = path.join(outDir, "splash.html");
const videoDir = path.resolve(__dirname, "..", "..", "..", "docs", "assets");
const videoPath = path.join(videoDir, "splash-demo.webm");

(async () => {
  if (!fs.existsSync(splashPath)) {
    console.error("splash.html not found at", splashPath);
    process.exit(1);
  }

  fs.mkdirSync(videoDir, { recursive: true });

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 400, height: 300 },
    recordVideo: {
      dir: videoDir,
      size: { width: 400, height: 300 },
    },
  });

  const page = await context.newPage();
  await page.goto("file://" + splashPath);

  await page.waitForFunction(() => document.title === "DONE", { timeout: 10000 }).catch(() => {
    console.warn("Timeout waiting for DONE signal, capturing anyway");
  });

  await context.close();
  await browser.close();

  const video = await page.video();
  const tmpFile = video ? await video.path() : null;
  if (tmpFile && tmpFile !== videoPath) {
    fs.renameSync(tmpFile, videoPath);
  }

  console.log("Video saved to", videoPath);
})();
