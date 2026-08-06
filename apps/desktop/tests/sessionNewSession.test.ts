import { describe, expect, it } from 'vitest';

import { shouldCreateNewSession } from '../src/renderer/lib/sessionNewSession';

describe('shouldCreateNewSession', () => {
  it('reuses an empty session instead of creating a new one', () => {
    expect(shouldCreateNewSession(true)).toBe(false);
  });

  it('creates a new session after a real conversation', () => {
    expect(shouldCreateNewSession(false)).toBe(true);
  });
});
