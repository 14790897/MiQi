/**
 * Full Electron E2E — manual launch + Puppeteer connect
 *
 * Launches Electron via child_process with debug port,
 * waits for CDP endpoint, then connects Puppeteer.
 */
import puppeteer, { Browser, Page } from 'puppeteer';
import { spawn, ChildProcess } from 'child_process';
import { resolve } from 'path';
import http from 'http';

const APPS_DESKTOP = resolve(__dirname, '../..');
const DEBUG_ENTRY = resolve(APPS_DESKTOP, 'out/main/electron-debug-loader.js');
const ELECTRON_BIN = resolve(APPS_DESKTOP, 'node_modules/electron/dist/electron.exe');
const LLM_TIMEOUT = 120_000;

function fetchJson(url: string): Promise<any> {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); } catch (e) { reject(e); }
      });
    }).on('error', reject);
  });
}

async function getWSEndpoint(port: number, retries = 30): Promise<string> {
  for (let i = 0; i < retries; i++) {
    try {
      const data = await fetchJson(`http://localhost:${port}/json/version`);
      if (data.webSocketDebuggerUrl) return data.webSocketDebuggerUrl;
    } catch {}
    await new Promise(r => setTimeout(r, 1000));
  }
  throw new Error(`CDP not available on port ${port} after ${retries}s`);
}

async function main() {
  console.log('Starting Electron...');

  // Launch Electron manually
  const proc: ChildProcess = spawn(ELECTRON_BIN, [DEBUG_ENTRY], {
    cwd: APPS_DESKTOP,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env },
  });

  proc.stdout?.on('data', (d) => process.stdout.write(`[e] ${d}`));
  proc.stderr?.on('data', (d) => process.stderr.write(`[e:err] ${d}`));

  let passed = 0;
  let failed = 0;

  try {
    // Wait for CDP endpoint
    console.log('Waiting for CDP endpoint...');
    const wsUrl = await getWSEndpoint(9222);
    console.log('CDP ready:', wsUrl);

    const browser: Browser = await puppeteer.connect({ browserWSEndpoint: wsUrl });
    const page: Page = (await browser.pages())[0];

    await page.waitForFunction(
      () => document.body.innerText.includes('MiQi Workbench'),
      { timeout: 30000 }
    );
    console.log('✅ App loaded');
    passed++;

    // Wait for textarea
    await page.waitForFunction(() => {
      const ta = document.querySelector('textarea[placeholder="Ask Agent to analyze or edit files..."]');
      return ta && !(ta as HTMLTextAreaElement).disabled;
    }, { timeout: 60000 });

    // AI conversation
    console.log('\nSending message...');
    const textarea = await page.$('textarea[placeholder="Ask Agent to analyze or edit files..."]');
    await textarea!.type('回复一个字：好');
    await textarea!.press('Enter');

    await page.waitForFunction(
      (t: string) => document.body.innerText.includes(t),
      { timeout: LLM_TIMEOUT },
      '好'
    );
    console.log('✅ AI conversation passed');
    passed++;

  } catch (e: any) {
    console.error('❌ Failed:', e.message);
    failed++;
  } finally {
    console.log(`\n======== Results: ${passed} passed, ${failed} failed ========`);
    proc.kill();
    process.exit(failed > 0 ? 1 : 0);
  }
}

main();
