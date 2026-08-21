import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 900, height: 600 } });
await p.goto('file:///' + process.cwd().replace(/\\/g, '/') + '/scripts/ui-shots/toast-demo.html');
await p.waitForTimeout(800);
await p.screenshot({ path: 'scripts/ui-shots/shots/toast-demo.png' });
await b.close();
console.log('toast 截图完成');
