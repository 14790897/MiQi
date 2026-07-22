/**
 * Convert Windows .ico to macOS .icns
 *
 * ICO format (little-endian):
 *   Header:  reserved(u16) type(u16=1) count(u16)
 *   Entries: width(u8) height(u8) palette(u8) reserved(u8) planes(u16) bpp(u16) size(u32) offset(u32)
 *
 * ICNS format (big-endian):
 *   Header: 'icns'(u32) totalLen(u32)
 *   Entries: iconType(u32) entryLen(u32) data[]
 *   Icon types: ic07=128px, ic08=256px, ic09=512px, ic10=1024px
 */

const fs = require('fs');
const path = require('path');

const icoPath = path.resolve(__dirname, '../src/renderer/assets/icon.ico');
const icnsPath = path.resolve(__dirname, '../src/renderer/assets/icon.icns');

const ico = fs.readFileSync(icoPath);
const buf = Buffer.from(ico);

// Parse ICO header
const reserved = buf.readUInt16LE(0);
const type = buf.readUInt16LE(2);
const count = buf.readUInt16LE(4);

console.log(`ICO: type=${type}, count=${count}`);

// Read entries
const entries = [];
for (let i = 0; i < count; i++) {
  const off = 6 + i * 16;
  const width = buf.readUInt8(off); // 0 means 256
  const height = buf.readUInt8(off + 1); // 0 means 256
  const size = buf.readUInt32LE(off + 8);
  const offset = buf.readUInt32LE(off + 12);
  const w = width === 0 ? 256 : width;
  const h = height === 0 ? 256 : height;
  entries.push({ w, h, size, offset });
  console.log(`  entry: ${w}x${h}, ${size} bytes at offset ${offset}`);
}

// Sort by size descending
entries.sort((a, b) => b.w - a.w);

// Build ICNS
const icnsTypeMap = {
  1024: 'ic10',
  512: 'ic09',
  256: 'ic08',
  128: 'ic07',
};

const icnsEntries = [];
for (const entry of entries) {
  const typeKey = icnsTypeMap[entry.w];
  if (!typeKey) {
    console.log(`  skipping ${entry.w}x${entry.h} — no ICNS type`);
    continue;
  }
  const pngData = buf.slice(entry.offset, entry.offset + entry.size);
  // Each ICNS entry is: type(u32 BE) + length(u32 BE, includes header) + data
  const entryHeader = Buffer.alloc(8);
  entryHeader.writeUInt32BE(
    typeKey.charCodeAt(0) << 24 |
    typeKey.charCodeAt(1) << 16 |
    typeKey.charCodeAt(2) << 8 |
    typeKey.charCodeAt(3),
    0
  );
  entryHeader.writeUInt32BE(8 + pngData.length, 4);
  icnsEntries.push(Buffer.concat([entryHeader, pngData]));
  console.log(`  -> ICNS ${typeKey} (${pngData.length} bytes)`);
}

// ICNS header
const icnsHeader = Buffer.alloc(8);
icnsHeader.writeUInt32BE(
  'i'.charCodeAt(0) << 24 |
  'c'.charCodeAt(0) << 16 |
  'n'.charCodeAt(0) << 8 |
  's'.charCodeAt(0),
  0
);

const totalLen = 8 + icnsEntries.reduce((s, e) => s + e.length, 0);
icnsHeader.writeUInt32BE(totalLen, 4);

const icns = Buffer.concat([icnsHeader, ...icnsEntries]);
fs.writeFileSync(icnsPath, icns);
console.log(`Written ${totalLen} bytes to ${icnsPath}`);
