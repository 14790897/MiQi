import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 720, height: 900 } });
await p.goto('file:///' + process.cwd().replace(/\\/g, '/') + '/scripts/ui-shots/action-demo.html');
await p.waitForTimeout(1200);
await p.screenshot({ path: 'scripts/ui-shots/shots/action-card-all.png' });
await b.close();
console.log('action-card 截图完成');
