import { describe, expect, it, vi } from 'vitest';
import { createTypedAppClient } from './app-client';

describe('createTypedAppClient', () => {
  it('dispatches typed method params through the send function', async () => {
    const send = vi.fn(async () => ({ dataBase64: 'aGVsbG8=' }));
    const client = createTypedAppClient(send);

    const result = await client.request('fs/readFile', {
      path: 'C:/repo/file.txt',
    });

    expect(result).toEqual({ dataBase64: 'aGVsbG8=' });
    expect(send).toHaveBeenCalledWith('fs/readFile', { path: 'C:/repo/file.txt' }, undefined);
  });

  it('passes event callback through unchanged', async () => {
    const send = vi.fn(async () => ({}));
    const client = createTypedAppClient(send);
    const onEvent = vi.fn();

    await client.request(
      'command/exec',
      {
        command: ['echo', 'hello'],
        processId: 'cmd-1',
        streamStdoutStderr: true,
      },
      onEvent
    );

    expect(send).toHaveBeenCalledWith(
      'command/exec',
      {
        command: ['echo', 'hello'],
        processId: 'cmd-1',
        streamStdoutStderr: true,
      },
      onEvent
    );
  });
});
