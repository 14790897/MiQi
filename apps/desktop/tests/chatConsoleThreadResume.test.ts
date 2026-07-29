import { describe, expect, it } from 'vitest';
import { pickThreadToResume } from '../src/renderer/features/chat/ChatConsole';

/**
 * Issue #490: when (re)entering a session the frontend must resume the
 * session's existing thread instead of calling thread/start and minting a
 * fresh random thread_id. pickThreadToResume selects that thread from a
 * `thread/list` result. These tests pin the selection rule so the resume
 * path keeps loading A's own history — without ever pulling B/C content
 * into A.
 *
 * Selection rule (revised for fragmented legacy sessions): prefer the
 * thread with the MOST persisted turns (`turnCount`), ties broken by the
 * largest `updatedAt`. On a clean single-thread session both heuristics
 * agree; on a fragmented session the richness rule lands on the thread
 * that holds the real conversation rather than a nearly-empty thread that
 * was merely touched last.
 */
describe('pickThreadToResume', () => {
  it('returns null when there are no threads (brand-new session)', () => {
    expect(pickThreadToResume([])).toBeNull();
    expect(pickThreadToResume(null)).toBeNull();
    expect(pickThreadToResume(undefined)).toBeNull();
    expect(pickThreadToResume('not-an-array')).toBeNull();
  });

  it('picks the single active thread', () => {
    const items = [{ id: 'thread-a', turnCount: 3, updatedAt: 1000, archived: false, ephemeral: false }];
    expect(pickThreadToResume(items)).toBe('thread-a');
  });

  it('prefers the thread with the most turns even if it is not the most recent', () => {
    // Real fragmented-session shape: a nearly-empty recap thread touched
    // last vs. a history-rich thread touched earlier.
    const items = [
      { id: 'rich-but-older', turnCount: 14, updatedAt: 2000, createdAt: 1000, archived: false, ephemeral: false },
      { id: 'empty-but-recent', turnCount: 1, updatedAt: 9000, createdAt: 8000, archived: false, ephemeral: false },
      { id: 'mid', turnCount: 6, updatedAt: 5000, createdAt: 1500, archived: false, ephemeral: false },
    ];
    expect(pickThreadToResume(items)).toBe('rich-but-older');
  });

  it('breaks turnCount ties by the largest updatedAt', () => {
    const items = [
      { id: 'same-turns-old', turnCount: 5, updatedAt: 1000, createdAt: 1000, archived: false, ephemeral: false },
      { id: 'same-turns-new', turnCount: 5, updatedAt: 5000, createdAt: 2000, archived: false, ephemeral: false },
      { id: 'same-turns-mid', turnCount: 5, updatedAt: 3000, createdAt: 1500, archived: false, ephemeral: false },
    ];
    expect(pickThreadToResume(items)).toBe('same-turns-new');
  });

  it('treats a missing turnCount as 0 (richness still drives selection)', () => {
    const items = [
      { id: 'no-count', updatedAt: 9000, createdAt: 9000, archived: false, ephemeral: false },
      { id: 'has-count', turnCount: 2, updatedAt: 1000, createdAt: 1000, archived: false, ephemeral: false },
    ];
    expect(pickThreadToResume(items)).toBe('has-count');
  });

  it('falls back to createdAt when updatedAt is missing (richness still wins)', () => {
    const items = [
      { id: 'thread-x', turnCount: 4, createdAt: 1000, archived: false, ephemeral: false },
      { id: 'thread-y', turnCount: 1, createdAt: 9000, archived: false, ephemeral: false },
    ];
    expect(pickThreadToResume(items)).toBe('thread-x');
  });

  it('skips archived threads', () => {
    const items = [
      { id: 'archived-but-richest', turnCount: 99, updatedAt: 9999, archived: true, ephemeral: false },
      { id: 'active-thin', turnCount: 1, updatedAt: 1000, archived: false, ephemeral: false },
    ];
    expect(pickThreadToResume(items)).toBe('active-thin');
  });

  it('skips ephemeral threads', () => {
    const items = [
      { id: 'ephemeral-richest', turnCount: 99, updatedAt: 9999, archived: false, ephemeral: true },
      { id: 'persistent', turnCount: 1, updatedAt: 1000, archived: false, ephemeral: false },
    ];
    expect(pickThreadToResume(items)).toBe('persistent');
  });

  it('treats archived/ephemeral as falsey when absent (only archived:false survives)', () => {
    // Mirrors real ThreadView rows where archived/ephemeral are booleans.
    const items = [
      { id: 'only-id', turnCount: 2, updatedAt: 1234 }, // archived/ephemeral absent → not filtered out
    ];
    expect(pickThreadToResume(items)).toBe('only-id');
  });

  it('returns null when every thread is archived or ephemeral', () => {
    const items = [
      { id: 'a', turnCount: 9, updatedAt: 1000, archived: true, ephemeral: false },
      { id: 'b', turnCount: 9, updatedAt: 2000, archived: false, ephemeral: true },
    ];
    expect(pickThreadToResume(items)).toBeNull();
  });

  it('ignores rows with a missing or empty id', () => {
    const items = [
      { id: '', turnCount: 99, updatedAt: 9999, archived: false, ephemeral: false },
      { turnCount: 98, updatedAt: 9998, archived: false, ephemeral: false },
      { id: 'valid', turnCount: 1, updatedAt: 1, archived: false, ephemeral: false },
    ];
    expect(pickThreadToResume(items)).toBe('valid');
  });

  it('handles stringy/non-numeric counts and timestamps defensively', () => {
    const items = [
      { id: 'a', turnCount: 'abc', updatedAt: 'abc', createdAt: 5, archived: false, ephemeral: false },
      { id: 'b', turnCount: '10', updatedAt: '10', createdAt: 1, archived: false, ephemeral: false },
    ];
    // Number('abc') → NaN → 0; Number('10') → 10. b has more turns → picked.
    expect(pickThreadToResume(items)).toBe('b');
  });
});
