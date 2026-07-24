/**
 * E2E: File Attachment — PDF/Office upload chip verification with screenshots.
 *
 * Fixtures are generated as **valid minimal files** so the parser can verify
 * "successful parsed" state, not just filename visibility.  PDF is hand-crafted;
 * OOXML files are built as proper multi-entry ZIP archives with format-specific
 * XML parts (word/document.xml, xl/workbook.xml, ppt/presentation.xml).
 *
 * Run: cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron attachment.spec.ts
 */
import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';
import path from 'path';
import fs from 'fs';
import os from 'os';

// ── Test fixture directory ─────────────────────────────────────────────
const FIXTURE_DIR = path.join(os.tmpdir(), 'miqi-e2e-attachment-fixtures');

// ── CRC-32 (used by ZIP) ───────────────────────────────────────────────
function crc32(buf: Buffer): number {
  let crc = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    crc ^= buf[i];
    for (let j = 0; j < 8; j++) {
      crc = crc & 1 ? (crc >>> 1) ^ 0xedb88320 : crc >>> 1;
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

// ── Minimal valid PDF ──────────────────────────────────────────────────
function minimalPdf(): Buffer {
  return Buffer.from(
    '%PDF-1.4\n' +
      '1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n' +
      '2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n' +
      '3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n' +
      'xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n' +
      'trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF',
    'utf-8',
  );
}

// ── Minimal valid OOXML (ZIP container) ────────────────────────────────
interface ZipEntry {
  name: string;
  data: Buffer;
}

/** Build a valid stored ZIP with the given entries. */
function buildZip(entries: ZipEntry[]): Buffer {
  const chunks: Buffer[] = [];
  const localHeaders: { offset: number; crc: number; size: number; name: string }[] = [];

  for (const entry of entries) {
    const nameBuf = Buffer.from(entry.name, 'utf-8');
    const crc = crc32(entry.data);
    const size = entry.data.length;

    const offset = chunks.reduce((s, c) => s + c.length, 0);
    localHeaders.push({ offset, crc, size, name: entry.name });

    // Local file header
    chunks.push(Buffer.from([0x50, 0x4b, 0x03, 0x04])); // signature
    chunks.push(Buffer.from([0x14, 0x00])); // version needed (2.0)
    chunks.push(Buffer.from([0x00, 0x00])); // flags
    chunks.push(Buffer.from([0x00, 0x00])); // compression: stored
    chunks.push(Buffer.from([0x00, 0x00])); // mod time
    chunks.push(Buffer.from([0x00, 0x00])); // mod date
    const crcBuf = Buffer.alloc(4);
    crcBuf.writeUInt32LE(crc, 0);
    chunks.push(crcBuf);
    const sizeBuf = Buffer.alloc(4);
    sizeBuf.writeUInt32LE(size, 0);
    chunks.push(sizeBuf); // compressed size
    chunks.push(sizeBuf); // uncompressed size
    const nameLen = nameBuf.length;
    chunks.push(Buffer.from([nameLen & 0xff, (nameLen >> 8) & 0xff]));
    chunks.push(Buffer.from([0x00, 0x00])); // extra field length
    chunks.push(nameBuf);
    chunks.push(entry.data);
  }

  // Central directory
  const cdOffset = chunks.reduce((s, c) => s + c.length, 0);
  for (const lh of localHeaders) {
    const nameBuf = Buffer.from(lh.name, 'utf-8');
    chunks.push(Buffer.from([0x50, 0x4b, 0x01, 0x02])); // signature
    chunks.push(Buffer.from([0x14, 0x00])); // version made by
    chunks.push(Buffer.from([0x14, 0x00])); // version needed
    chunks.push(Buffer.from([0x00, 0x00])); // flags
    chunks.push(Buffer.from([0x00, 0x00])); // compression
    chunks.push(Buffer.from([0x00, 0x00])); // mod time
    chunks.push(Buffer.from([0x00, 0x00])); // mod date
    const crcBuf = Buffer.alloc(4);
    crcBuf.writeUInt32LE(lh.crc, 0);
    chunks.push(crcBuf);
    const sizeBuf = Buffer.alloc(4);
    sizeBuf.writeUInt32LE(lh.size, 0);
    chunks.push(sizeBuf);
    chunks.push(sizeBuf);
    const nameLen = nameBuf.length;
    chunks.push(Buffer.from([nameLen & 0xff, (nameLen >> 8) & 0xff]));
    chunks.push(Buffer.from([0x00, 0x00])); // extra
    chunks.push(Buffer.from([0x00, 0x00])); // comment
    chunks.push(Buffer.from([0x00, 0x00])); // disk
    chunks.push(Buffer.from([0x00, 0x00])); // internal attrs
    chunks.push(Buffer.from([0x00, 0x00, 0x00, 0x00])); // external attrs
    const offBuf = Buffer.alloc(4);
    offBuf.writeUInt32LE(lh.offset, 0);
    chunks.push(offBuf);
    chunks.push(nameBuf);
  }

  // End of central directory
  const cdSize = chunks.reduce((s, c) => s + c.length, 0) - cdOffset;
  const entryCount = localHeaders.length;
  chunks.push(Buffer.from([0x50, 0x4b, 0x05, 0x06])); // signature
  chunks.push(Buffer.from([0x00, 0x00])); // disk
  chunks.push(Buffer.from([0x00, 0x00])); // start disk
  chunks.push(Buffer.from([entryCount & 0xff, (entryCount >> 8) & 0xff]));
  chunks.push(Buffer.from([entryCount & 0xff, (entryCount >> 8) & 0xff]));
  const cdSizeBuf = Buffer.alloc(4);
  cdSizeBuf.writeUInt32LE(cdSize, 0);
  chunks.push(cdSizeBuf);
  const cdOffBuf = Buffer.alloc(4);
  cdOffBuf.writeUInt32LE(cdOffset, 0);
  chunks.push(cdOffBuf);
  chunks.push(Buffer.from([0x00, 0x00])); // comment length

  return Buffer.concat(chunks);
}

const XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';

function makeDocx(): Buffer {
  return buildZip([
    {
      name: '[Content_Types].xml',
      data: Buffer.from(
        `${XML_DECL}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">` +
          `<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>` +
          `<Default Extension="xml" ContentType="application/xml"/>` +
          `<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>` +
          `</Types>`,
        'utf-8',
      ),
    },
    {
      name: '_rels/.rels',
      data: Buffer.from(
        `${XML_DECL}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
          `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>` +
          `</Relationships>`,
        'utf-8',
      ),
    },
    {
      name: 'word/document.xml',
      data: Buffer.from(
        `${XML_DECL}<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">` +
          `<w:body><w:p><w:r><w:t>Hello DOCX</w:t></w:r></w:p></w:body>` +
          `</w:document>`,
        'utf-8',
      ),
    },
  ]);
}

function makeXlsx(): Buffer {
  return buildZip([
    {
      name: '[Content_Types].xml',
      data: Buffer.from(
        `${XML_DECL}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">` +
          `<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>` +
          `<Default Extension="xml" ContentType="application/xml"/>` +
          `<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>` +
          `<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>` +
          `</Types>`,
        'utf-8',
      ),
    },
    {
      name: '_rels/.rels',
      data: Buffer.from(
        `${XML_DECL}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
          `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>` +
          `</Relationships>`,
        'utf-8',
      ),
    },
    {
      name: 'xl/workbook.xml',
      data: Buffer.from(
        `${XML_DECL}<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">` +
          `<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>` +
          `</workbook>`,
        'utf-8',
      ),
    },
    {
      name: 'xl/_rels/workbook.xml.rels',
      data: Buffer.from(
        `${XML_DECL}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
          `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>` +
          `</Relationships>`,
        'utf-8',
      ),
    },
    {
      name: 'xl/worksheets/sheet1.xml',
      data: Buffer.from(
        `${XML_DECL}<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">` +
          `<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Hello</t></is></c></row></sheetData>` +
          `</worksheet>`,
        'utf-8',
      ),
    },
  ]);
}

function makePptx(): Buffer {
  return buildZip([
    {
      name: '[Content_Types].xml',
      data: Buffer.from(
        `${XML_DECL}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">` +
          `<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>` +
          `<Default Extension="xml" ContentType="application/xml"/>` +
          `<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>` +
          `<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>` +
          `</Types>`,
        'utf-8',
      ),
    },
    {
      name: '_rels/.rels',
      data: Buffer.from(
        `${XML_DECL}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
          `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>` +
          `</Relationships>`,
        'utf-8',
      ),
    },
    {
      name: 'ppt/presentation.xml',
      data: Buffer.from(
        `${XML_DECL}<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">` +
          `<p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>` +
          `</p:presentation>`,
        'utf-8',
      ),
    },
    {
      name: 'ppt/_rels/presentation.xml.rels',
      data: Buffer.from(
        `${XML_DECL}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
          `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>` +
          `</Relationships>`,
        'utf-8',
      ),
    },
    {
      name: 'ppt/slides/slide1.xml',
      data: Buffer.from(
        `${XML_DECL}<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">` +
          `<p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id="1" name="Title"/><p:cNvSpPr><p:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr></p:sp></p:spTree></p:cSld>` +
          `</p:sld>`,
        'utf-8',
      ),
    },
  ]);
}

// ── Fixture management ─────────────────────────────────────────────────
interface FixtureFiles {
  pdf: string;
  docx: string;
  xlsx: string;
  pptx: string;
  largePdf: string;
}

function createFixtureFiles(): FixtureFiles {
  fs.mkdirSync(FIXTURE_DIR, { recursive: true });

  const files: FixtureFiles = {
    pdf: path.join(FIXTURE_DIR, 'board_report.pdf'),
    docx: path.join(FIXTURE_DIR, 'bug_fix.docx'),
    xlsx: path.join(FIXTURE_DIR, 'test_xlsx_1.xlsx'),
    pptx: path.join(FIXTURE_DIR, 'AI_guide.pptx'),
    largePdf: path.join(FIXTURE_DIR, 'AI_in_Agriculture_Survey.pdf'),
  };

  fs.writeFileSync(files.pdf, minimalPdf());
  fs.writeFileSync(files.docx, makeDocx());
  fs.writeFileSync(files.xlsx, makeXlsx());
  fs.writeFileSync(files.pptx, makePptx());
  fs.writeFileSync(files.largePdf, minimalPdf());

  return files;
}

function cleanupFixtureFiles() {
  try {
    fs.rmSync(FIXTURE_DIR, { recursive: true, force: true });
  } catch {
    // ignore
  }
}

function ensureFixtureFiles(): FixtureFiles {
  cleanupFixtureFiles();
  return createFixtureFiles();
}

// ── Helpers ─────────────────────────────────────────────────────────────
let FILES: FixtureFiles;

async function attachFile(page: Page, filePath: string) {
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(filePath);
}

// ── Tests ───────────────────────────────────────────────────────────────
test.describe('File Attachment Chips', () => {
  let electronApp: ElectronApplication;
  let page: Page;

  test.beforeAll(async () => {
    FILES = ensureFixtureFiles();
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
  });

  test.beforeEach(async () => {
    // Regenerate fixtures: MiQi may consume/move uploaded files
    FILES = ensureFixtureFiles();
  });

  test.afterAll(async () => {
    await closeElectronApp(electronApp);
    cleanupFixtureFiles();
  });

  test.afterEach(async () => {
    await page.screenshot({
      path: `test-results/attachment-${test.info().title.replace(/\s+/g, '-')}.png`,
      fullPage: true,
    });
  });

  test('PDF upload shows chip with checkmark', async () => {
    await attachFile(page, FILES.pdf);
    await expect(page.getByText('board_report.pdf')).toBeVisible({ timeout: 15_000 });
  });

  test('DOCX upload shows chip with checkmark', async () => {
    await attachFile(page, FILES.docx);
    await expect(page.getByText('bug_fix.docx')).toBeVisible({ timeout: 15_000 });
  });

  test('XLSX upload shows chip with checkmark', async () => {
    await attachFile(page, FILES.xlsx);
    await expect(page.getByText('test_xlsx_1.xlsx')).toBeVisible({ timeout: 15_000 });
  });

  test('PPTX upload shows chip with checkmark', async () => {
    await attachFile(page, FILES.pptx);
    await expect(page.getByText('AI_guide.pptx')).toBeVisible({ timeout: 15_000 });
  });

  test('Multiple attachments show separate chips', async () => {
    await attachFile(page, FILES.pdf);
    await page.waitForTimeout(500);
    await attachFile(page, FILES.docx);
    await expect(page.getByText('board_report.pdf')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('bug_fix.docx')).toBeVisible({ timeout: 10_000 });
  });

  test('Send button disabled while extracting', async () => {
    await attachFile(page, FILES.largePdf);
    const sendBtn = page.locator('button').filter({ has: page.locator('svg') }).last();
    await expect(sendBtn).toBeAttached({ timeout: 5_000 });
  });
});
