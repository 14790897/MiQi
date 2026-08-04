import { describe, expect, it } from 'vitest';
import { splitThink } from '../src/renderer/features/chat/components/splitThink';

// Construct think tags programmatically so the literal tags don't get
// mangled by tooling / escaping when editing this file.
const OPEN = '<' + 'think>';
const CLOSE = '<' + '/think>';
const tag = (inner: string) => `${OPEN}${inner}${CLOSE}`;

describe('splitThink', () => {
  it('returns an empty array for empty input', () => {
    expect(splitThink('')).toEqual([]);
  });

  it('returns plain text as a single text segment when no think tags present', () => {
    expect(splitThink('hello world')).toEqual([{ type: 'text', value: 'hello world' }]);
  });

  it('extracts a complete think block into a think segment', () => {
    expect(splitThink(`before${tag('inner')}after`)).toEqual([
      { type: 'text', value: 'before' },
      { type: 'think', value: 'inner' },
      { type: 'text', value: 'after' },
    ]);
  });

  it('handles multiple consecutive think blocks', () => {
    expect(splitThink(`one${tag('1')}two${tag('2')}three`)).toEqual([
      { type: 'text', value: 'one' },
      { type: 'think', value: '1' },
      { type: 'text', value: 'two' },
      { type: 'think', value: '2' },
      { type: 'text', value: 'three' },
    ]);
  });

  it('treats an unclosed think tag as an in-progress think segment to end of string', () => {
    expect(splitThink(`pre${OPEN}still thinking`)).toEqual([
      { type: 'text', value: 'pre' },
      { type: 'think', value: 'still thinking' },
    ]);
  });

  it('is case-insensitive on tag names', () => {
    const upperOpen = '<' + 'THINK>';
    const upperClose = '<' + '/THINK>';
    expect(splitThink(`a${upperOpen}INNER${upperClose}b`)).toEqual([
      { type: 'text', value: 'a' },
      { type: 'think', value: 'INNER' },
      { type: 'text', value: 'b' },
    ]);
  });

  it('handles a think block at the very start (no leading text)', () => {
    expect(splitThink(`${tag('only thinking')}then text`)).toEqual([
      { type: 'think', value: 'only thinking' },
      { type: 'text', value: 'then text' },
    ]);
  });

  it('handles a think block at the very end (no trailing text)', () => {
    expect(splitThink(`text${tag('then')}`)).toEqual([
      { type: 'text', value: 'text' },
      { type: 'think', value: 'then' },
    ]);
  });

  it('preserves an empty think block as an empty think segment (no trailing text)', () => {
    expect(splitThink(tag(''))).toEqual([{ type: 'think', value: '' }]);
  });

  it('does not duplicate content for nested think tags', () => {
    // Nested/overlapping opens: the inner  sits inside the outer span
    // already consumed, so "inner" must NOT appear twice. The outer opening
    // tag is paired with the FIRST closing tag (inner's), which leaves the
    // outer's own closing tag unconsumed — it falls through into the trailing
    // text segment. react-markdown drops raw HTML tags by default, so this
    // residual is not user-visible; the regression we guard against here is
    // the content-duplication ("inner" appearing twice) that the
    // `open.idx < cursor` skip prevents.
    const nested = `pre${OPEN}outer ${OPEN}inner${CLOSE}${CLOSE}post`;
    const segs = splitThink(nested);
    expect(segs.some((s) => s.type === 'think' && s.value.includes('inner'))).toBe(true);
    // "inner" must appear in exactly ONE think segment (no duplication).
    const thinkCount = segs.filter(
      (s) => s.type === 'think' && s.value.includes('inner')
    ).length;
    expect(thinkCount).toBe(1);
    // "post" survives in a trailing text segment.
    expect(segs.some((s) => s.type === 'text' && s.value.includes('post'))).toBe(true);
  });
});
