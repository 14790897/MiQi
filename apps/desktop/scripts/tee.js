/**
 * Cross-platform tee — pipes stdin to stdout AND to a file.
 * Usage: node scripts/tee.js <output-file>
 */
const fs = require('fs');
const path = require('path');

const outFile = path.resolve(process.argv[2] || 'test-output.log');
const dir = path.dirname(outFile);

if (!fs.existsSync(dir)) {
  fs.mkdirSync(dir, { recursive: true });
}

const ws = fs.createWriteStream(outFile);

process.stdin.pipe(ws);
process.stdin.pipe(process.stdout);

process.stdin.on('end', () => {
  ws.end();
});

ws.on('error', (err) => {
  console.error(`tee: write error: ${err.message}`);
});
