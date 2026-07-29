import { describe, expect, it } from 'vitest';
import { pickThreadToResume } from '../src/renderer/features/chat/ChatConsole';

/**
 * Issue #490: when (re)entering a session the frontend must resume the
 * session's most-recent active thread instead of calling thread/start and
 * minting a fresh random thread_id. pickThreadToResume selects that
 * thread from a `thread/list` result. These tests pin the selection rule
 * (most-recent updatedAt, skip archived/ephemeral, null when empty) so the
 * resume path keeps loading A's own history — without ever pulling B/C
 * content into A.
 */
describe('pickThreadToResume', () => {
  it('returns null when there are no threads (brand-new session)', () => {
    expect(pickThreadToResume([])).toBeNull();
    expect(pickThreadToResume(null)).toBeNull();
    expect(pickThreadToResume(undefined)).toBeNull();
    expect(pickThreadToResume('not-an-array')).toBeNull();
  });

  it('picks the single active thread', () => {
    const items = [{ id: 'thread-a', updatedAt: 1000, archived: false, ephemeral: false }];
    expect(pickThreadToResume(items)).toBe('thread-a');
  });

  it('picks the most recently updated thread', () => {
    const items = [
      { id: 'thread-old', updatedAt: 1000, createdAt: 1000, archived: false, ephemeral: false },
      { id: 'thread-new', updatedAt: 5000, createdAt: 2000, archived: false, ephemeral: false },
      { id: 'thread-mid', updatedAt: 3000, createdAt: 1500, archived: false, ephemeral: false },
    ];
    expect(pickThreadToResume(items)).toBe('thread-new');
  });

  it('falls back to createdAt when updatedAt is missing', () => {
    const items = [
      { id: 'thread-x', createdAt: 9000, archived: false, ephemeral: false },
      { id: 'thread-y', createdAt: 1000, archived: false, ephemeral: false },
    ];
    expect(pickThreadToResume(items)).toBe('thread-x');
  });

  it('skips archived threads', () => {
    const items = [
      { id: 'archived-but-recent', updatedAt: 9999, archived: true, ephemeral: false },
      { id: 'active-but-older', updatedAt: 1000, archived: false, ephemeral: false },
    ];
    expect(pickThreadToResume(items)).toBe('active-but-older');
  });

  it('skips ephemeral threads', () => {
    const items = [
      { id: 'ephemeral-recent', updatedAt: 9999, archived: false, ephemeral: true },
      { id: 'persistent', updatedAt: 1000, archived: false, ephemeral: false },
    ];
    expect(pickThreadToResume(items)).toBe('persistent');
  });

  it('treats archived/ephemeral as falsey when absent (only archived:false survives)', () => {
    // Mirrors real ThreadView rows where archived/ephemeral are booleans.
    const items = [
      { id: 'only-id', updatedAt: 1234 }, // archived/ephemeral absent → not filtered out
    ];
    expect(pickThreadToResume(items)).toBe('only-id');
  });

  it('returns null when every thread is archived or ephemeral', () => {
    const items = [
      { id: 'a', updatedAt: 1000, archived: true, ephemeral: false },
      { id: 'b', updatedAt: 2000, archived: false, ephemeral: true },
    ];
    expect(pickThreadToResume(items)).toBeNull();
  });

  it('ignores rows with a missing or empty id', () => {
    const items = [
      { id: '', updatedAt: 9999, archived: false, ephemeral: false },
      { updatedAt: 9998, archived: false, ephemeral: false },
      { id: 'valid', updatedAt: 1, archived: false, ephemeral: false },
    ];
    expect(pickThreadToResume(items)).toBe('valid');
  });

  it('handles stringy/non-numeric timestamps defensively', () => {
    const items = [
      { id: 'a', updatedAt: 'abc', createdAt: 5, archived: false, ephemeral: false },
      { id: 'b', updatedAt: '10', createdAt: 1, archived: false, ephemeral: false },
    ];
    // Number('abc') is NaN → coerced to 0; Number('10') is 10 → picked.
    expect(pickThreadToResume(items)).toBe('b');
  });
});
