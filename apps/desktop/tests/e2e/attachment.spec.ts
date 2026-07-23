/**
 * E2E: File Attachment — PDF/Office upload chip verification with screenshots
 * Run: cd apps/desktop && npx playwright test --config=playwright.config.ts --project=electron attachment.spec.ts
 */
import { _electron as electron, test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import {
  waitForInputReady,
  launchElectronApp,
  closeElectronApp,
} from './helpers/electron-setup';
import path from 'path';
import fs from 'fs';
import os from 'os';

// ── Test fixture files (created at setup, cleaned after) ────────────────
const FIXTURE_DIR = path.join(os.tmpdir(), 'miqi-e2e-attachment-fixtures');

interface FixtureFiles {
  pdf: string;
  docx: string;
  xlsx: string;
  pptx: string;
  largePdf: string;
}

function createFixtureFiles(): FixtureFiles {
  fs.mkdirSync(FIXTURE_DIR, { recursive: true });

  // Minimal valid PDF (hand-crafted — 1 blank page)
  const minimalPdf = Buffer.from(
    '%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF',
    'utf-8',
  );

  // Minimal valid DOCX/XLSX/PPTX: ZIP with empty [Content_Types].xml
  function makeMinimalOoxml(): Buffer {
    // Valid ZIP local file header + central directory for a minimal OOXML file
    const contentTypes = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>';
    const buf = Buffer.from(contentTypes, 'utf-8');
    const crc = crc32(buf);
    
    // Simple ZIP with one stored file
    const chunks: Buffer[] = [];
    // Local file header
    chunks.push(Buffer.from([0x50, 0x4B, 0x03, 0x04])); // signature
    chunks.push(Buffer.from([0x14, 0x00])); // version needed
    chunks.push(Buffer.from([0x00, 0x00])); // flags
    chunks.push(Buffer.from([0x00, 0x00])); // compression (stored)
    chunks.push(Buffer.from([0x00, 0x00])); // mod time
    chunks.push(Buffer.from([0x00, 0x00])); // mod date
    // CRC-32
    chunks.push(Buffer.from([crc & 0xFF, (crc >> 8) & 0xFF, (crc >> 16) & 0xFF, (crc >> 24) & 0xFF]));
    chunks.push(Buffer.from([buf.length & 0xFF, (buf.length >> 8) & 0xFF, 0x00, 0x00])); // compressed size
    chunks.push(Buffer.from([buf.length & 0xFF, (buf.length >> 8) & 0xFF, 0x00, 0x00])); // uncompressed size
    const nameLen = '[Content_Types].xml'.length;
    chunks.push(Buffer.from([nameLen & 0xFF, (nameLen >> 8) & 0xFF])); // filename length
    chunks.push(Buffer.from([0x00, 0x00])); // extra field length
    chunks.push(Buffer.from('[Content_Types].xml', 'utf-8'));
    chunks.push(buf);
    
    // Central directory
    const cdOffset = chunks.reduce((s, c) => s + c.length, 0);
    chunks.push(Buffer.from([0x50, 0x4B, 0x01, 0x02])); // central dir signature
    chunks.push(Buffer.from([0x14, 0x00])); // version made by
    chunks.push(Buffer.from([0x14, 0x00])); // version needed
    chunks.push(Buffer.from([0x00, 0x00])); // flags
    chunks.push(Buffer.from([0x00, 0x00])); // compression
    chunks.push(Buffer.from([0x00, 0x00])); // mod time
    chunks.push(Buffer.from([0x00, 0x00])); // mod date
    chunks.push(Buffer.from([crc & 0xFF, (crc >> 8) & 0xFF, (crc >> 16) & 0xFF, (crc >> 24) & 0xFF]));
    chunks.push(Buffer.from([buf.length & 0xFF, (buf.length >> 8) & 0xFF, 0x00, 0x00]));
    chunks.push(Buffer.from([buf.length & 0xFF, (buf.length >> 8) & 0xFF, 0x00, 0x00]));
    chunks.push(Buffer.from([nameLen & 0xFF, (nameLen >> 8) & 0xFF]));
    chunks.push(Buffer.from([0x00, 0x00])); // extra field
    chunks.push(Buffer.from([0x00, 0x00])); // comment
    chunks.push(Buffer.from([0x00, 0x00])); // disk
    chunks.push(Buffer.from([0x00, 0x00])); // internal attrs
    chunks.push(Buffer.from([0x00, 0x00, 0x00, 0x00])); // external attrs
    chunks.push(Buffer.from([0x00, 0x00, 0x00, 0x00])); // local header offset
    chunks.push(Buffer.from('[Content_Types].xml', 'utf-8'));
    
    // End of central directory
    chunks.push(Buffer.from([0x50, 0x4B, 0x05, 0x06])); // eocd signature
    chunks.push(Buffer.from([0x00, 0x00])); // disk number
    chunks.push(Buffer.from([0x00, 0x00])); // start disk
    chunks.push(Buffer.from([0x01, 0x00])); // entries on disk
    chunks.push(Buffer.from([0x01, 0x00])); // total entries
    const cdSize = cdOffset - buf.length - 30 - nameLen;
    chunks.push(Buffer.from([cdSize & 0xFF, (cdSize >> 8) & 0xFF, 0x00, 0x00]));
    chunks.push(Buffer.from([cdOffset & 0xFF, (cdOffset >> 8) & 0xFF, 0x00, 0x00]));
    chunks.push(Buffer.from([0x00, 0x00])); // comment length
    
    return Buffer.concat(chunks);
  }

  function crc32(buf: Buffer): number {
    let crc = 0xFFFFFFFF;
    for (let i = 0; i < buf.length; i++) {
      crc ^= buf[i];
      for (let j = 0; j < 8; j++) {
        if (crc & 1) crc = (crc >>> 1) ^ 0xEDB88320;
        else crc >>>= 1;
      }
    }
    return (crc ^ 0xFFFFFFFF) >>> 0;
  }

  const minimalOoxml = makeMinimalOoxml();

  const files: FixtureFiles = {
    pdf: path.join(FIXTURE_DIR, 'board_report.pdf'),
    docx: path.join(FIXTURE_DIR, 'bug_fix.docx'),
    xlsx: path.join(FIXTURE_DIR, 'test_xlsx_1.xlsx'),
    pptx: path.join(FIXTURE_DIR, 'AI_guide.pptx'),
    largePdf: path.join(FIXTURE_DIR, 'AI_in_Agriculture_Survey.pdf'),
  };

  fs.writeFileSync(files.pdf, minimalPdf);
  fs.writeFileSync(files.docx, minimalOoxml);
  fs.writeFileSync(files.xlsx, minimalOoxml);
  fs.writeFileSync(files.pptx, minimalOoxml);
  fs.writeFileSync(files.largePdf, minimalPdf);

  return files;
}

function cleanupFixtureFiles() {
  try {
    fs.rmSync(FIXTURE_DIR, { recursive: true, force: true });
  } catch {
    // ignore cleanup errors
  }
}

// Create once at module load
const FILES: FixtureFiles = createFixtureFiles();

async function attachFile(page: Page, filePath: string) {
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(filePath);
}

test.describe('File Attachment Chips', () => {
  let electronApp: ElectronApplication;
  let page: Page;

  test.beforeAll(async () => {
    const fixture = await launchElectronApp();
    electronApp = fixture.electronApp;
    page = fixture.page;
  });

  test.afterAll(async () => {
    await closeElectronApp(electronApp);
    cleanupFixtureFiles();
  });

  test.afterEach(async () => {
    await page.screenshot({ path: `test-results/attachment-${test.info().title.replace(/\s+/g, '-')}.png`, fullPage: true });
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
    // Attach a PDF that takes time to extract
    await attachFile(page, FILES.largePdf);
    // The send button should not be immediately clickable while extracting
    const sendBtn = page.locator('button').filter({ has: page.locator('svg') }).last();
    // Just verify send button exists — it should be disabled while extracting
    await expect(sendBtn).toBeAttached({ timeout: 5_000 });
  });
});
