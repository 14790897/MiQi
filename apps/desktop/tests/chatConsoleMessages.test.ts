import { describe, expect, it } from 'vitest';
import { sessionMsgsToUi } from '../src/renderer/features/chat/ChatConsole';

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
