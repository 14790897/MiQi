import { expect, test } from '@playwright/test';
import { buildMockBridgeScript } from './mocks';

async function injectMockAndGoto(
  page: import('@playwright/test').Page,
  opts?: Parameters<typeof buildMockBridgeScript>[0]
) {
  await page.addInitScript({ content: buildMockBridgeScript(opts) });
  await page.goto('/');
  await page.waitForSelector('#root', { state: 'visible' });
}

test.describe('Issue #172 assistant turn collapse', () => {
  test('hides transient assistant status text after final response arrives', async ({ page }) => {
    await injectMockAndGoto(page);

    const textarea = page.getByPlaceholder('Ask Agent to analyze or edit files...');
    await expect(textarea).toBeVisible({ timeout: 5000 });

    await textarea.fill('make several tool calls');
    await textarea.press('Enter');

    await page.evaluate(() => {
      (window as any).__miqiMock.progress({ text: 'I will start by checking the document.' });
      (window as any).__miqiMock.toolProgress('read_file("report.md")', 'call_issue_172_read');
      (window as any).__miqiMock.progress({ text: 'The document is updated.' });
      (window as any).__miqiMock._fireFinal('Final answer: report.md was updated and verified.');
    });

    await expect(page.getByText('Final answer: report.md was updated and verified.')).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText('I will start by checking the document.')).toHaveCount(0);
    await expect(page.getByText('The document is updated.')).toHaveCount(0);
    await expect(page.getByText('read_file')).toBeVisible();
  });

  test('replaces an earlier final bubble when a later final arrives in the same turn', async ({
    page,
  }) => {
    await injectMockAndGoto(page);

    const textarea = page.getByPlaceholder('Ask Agent to analyze or edit files...');
    await expect(textarea).toBeVisible({ timeout: 5000 });

    await textarea.fill('create a ppt');
    await textarea.press('Enter');

    await page.evaluate(async () => {
      (window as any).__miqiMock.rawFinal('文件已成');
      await new Promise<void>((resolve) => {
        requestAnimationFrame(() => {
          (window as any).__miqiMock.toolProgress('create_pptx("office_tools_review_final.pptx")');
          requestAnimationFrame(() => {
            (window as any).__miqiMock.rawFinal(
              '文件已成功创建！已创建的等效文件：office_tools_review_final.pptx'
            );
            resolve();
          });
        });
      });
    });

    await expect(page.getByText('文件已成功创建！已创建的等效文件：office_tools_review_final.pptx')).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByText('文件已成', { exact: true })).toHaveCount(0);
    await expect(page.getByText('create_pptx')).toBeVisible();
  });

  test('replays only final assistant text from historical multi-tool turns', async ({ page }) => {
    await injectMockAndGoto(page, {
      sessions: [
        {
          key: 'issue-172-session',
          title: 'Issue 172 repro',
          updated_at: Date.now(),
          message_count: 5,
        },
      ],
      sessionMessages: {
        'issue-172-session': [
          {
            role: 'user',
            content: 'edit the document',
            timestamp: '2026-07-08T01:00:00.000Z',
          },
          {
            role: 'assistant',
            content: 'I will start by reading the file.',
            tool_calls: [{ function: { name: 'read_file', arguments: '{"path":"report.md"}' } }],
            timestamp: '2026-07-08T01:00:01.000Z',
          },
          {
            role: 'tool',
            name: 'read_file',
            content: 'draft',
            timestamp: '2026-07-08T01:00:02.000Z',
          },
          {
            role: 'assistant',
            content: 'The edit is done.',
            timestamp: '2026-07-08T01:00:03.000Z',
          },
          {
            role: 'assistant',
            content: 'Final answer: document edited and checked.',
            timestamp: '2026-07-08T01:00:04.000Z',
          },
        ],
      },
    });

    await page.getByText('Issue 172 repro').click();

    await expect(page.getByText('Final answer: document edited and checked.')).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText('I will start by reading the file.')).toHaveCount(0);
    await expect(page.getByText('The edit is done.')).toHaveCount(0);
    await expect(page.getByText('read_file')).toBeVisible();
  });
});
