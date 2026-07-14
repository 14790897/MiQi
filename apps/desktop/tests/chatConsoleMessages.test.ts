import { describe, expect, it } from 'vitest';
import {
  buildTaskReproContext,
  buildTaskHeaderMeta,
  buildTaskShareText,
  getTaskShareDownloadName,
  sessionMsgsToUi,
} from '../src/renderer/features/chat/ChatConsole';

describe('sessionMsgsToUi', () => {
  it('shows only the final assistant text within a tool-heavy turn', () => {
    const messages = sessionMsgsToUi([
      { role: 'user', content: 'edit the file', timestamp: '2026-07-08T01:00:00.000Z' },
      {
        role: 'assistant',
        content: 'I will update it now.',
        tool_calls: [{ function: { name: 'read_file', arguments: '{"path":"a.md"}' } }],
        timestamp: '2026-07-08T01:00:01.000Z',
      },
      {
        role: 'tool',
        name: 'read_file',
        content: 'old content',
        timestamp: '2026-07-08T01:00:02.000Z',
      },
      {
        role: 'assistant',
        content: 'The edit is complete.',
        timestamp: '2026-07-08T01:00:03.000Z',
      },
      {
        role: 'assistant',
        content: 'Final summary: updated a.md and verified the result.',
        timestamp: '2026-07-08T01:00:04.000Z',
      },
    ]);

    const assistantMessages = messages.filter((message) => message.role === 'assistant');

    expect(assistantMessages).toHaveLength(1);
    expect(assistantMessages[0].content).toBe(
      'Final summary: updated a.md and verified the result.'
    );
    expect(messages.some((message) => message.role === 'progress' && message.toolHint)).toBe(true);
  });

  it('keeps final assistant text scoped to each user turn', () => {
    const messages = sessionMsgsToUi([
      { role: 'user', content: 'first', timestamp: '2026-07-08T01:00:00.000Z' },
      { role: 'assistant', content: 'first draft', timestamp: '2026-07-08T01:00:01.000Z' },
      { role: 'assistant', content: 'first final', timestamp: '2026-07-08T01:00:02.000Z' },
      { role: 'user', content: 'second', timestamp: '2026-07-08T01:00:03.000Z' },
      { role: 'assistant', content: 'second final', timestamp: '2026-07-08T01:00:04.000Z' },
    ]);

    expect(
      messages.filter((message) => message.role === 'assistant').map((message) => message.content)
    ).toEqual(['first final', 'second final']);
  });
});

describe('buildTaskHeaderMeta', () => {
  it('uses real file count and omits fake plugin/link placeholders', () => {
    const label = buildTaskHeaderMeta(Date.now(), 2, 3);

    expect(label).toContain('2 个文件');
    expect(label).toContain('3 个启用插件');
    expect(label).not.toContain('linked files');
    expect(label).not.toContain('Active Plugins');
  });
});

describe('buildTaskShareText', () => {
  it('builds a shareable task summary with recent messages and files', () => {
    const text = buildTaskShareText({
      title: '测试任务',
      meta: '刚刚更新 · 1 个文件',
      messages: [
        { role: 'user', content: '请修改 README', timestamp: 1 },
        { role: 'assistant', content: '已完成修改', timestamp: 2 },
        { role: 'progress', content: 'Write: README.md', timestamp: 3 },
      ],
      files: [{ path: 'README.md', name: 'README.md', op: 'edit', lastSeen: 4 }],
    });

    expect(text).toContain('# 测试任务');
    expect(text).toContain('刚刚更新 · 1 个文件');
    expect(text).toContain('- 用户: 请修改 README');
    expect(text).toContain('- MiQi: 已完成修改');
    expect(text).toContain('- README.md (edit)');
    expect(text).not.toContain('Write: README.md');
  });
});

describe('task share helpers', () => {
  it('builds a reproduction context with session id and full file paths', () => {
    const text = buildTaskReproContext({
      sessionKey: 'desktop:issue-243',
      title: '修复任务更新时间',
      meta: '刚刚更新 · 1 个文件',
      messages: [
        { role: 'user', content: '顶部也要显示真实文件数', timestamp: 1 },
        { role: 'assistant', content: '已接入 trackedFiles.length', timestamp: 2 },
      ],
      files: [
        {
          path: 'apps/desktop/src/renderer/features/chat/ChatConsole.tsx',
          name: 'ChatConsole.tsx',
          op: 'edit',
          lastSeen: 3,
        },
      ],
    });

    expect(text).toContain('desktop:issue-243');
    expect(text).toContain('- 用户: 顶部也要显示真实文件数');
    expect(text).toContain('[edit] apps/desktop/src/renderer/features/chat/ChatConsole.tsx');
  });

  it('sanitizes exported markdown filenames', () => {
    const name = getTaskShareDownloadName('修复: 顶部/侧边 文件?', 1783993200000);

    expect(name).toBe('修复-顶部-侧边-文件-2026-07-14T01-40-00-000Z.md');
  });
});
