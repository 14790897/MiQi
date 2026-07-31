// Pure parser that splits assistant content into ordered text/think segments.
// Extracted from MarkdownContent.tsx so unit tests can exercise the string
// parser without loading ReactMarkdown / remark-gfm / lucide-react.

export type Segment = { type: 'text'; value: string } | { type: 'think'; value: string };

const OPEN_RE = /<think(?:\s[^>]*)?>/gi;
const CLOSE_RE = /<\/think\s*>/gi;

/** Split content into ordered text/think segments.
 *  Handles complete `…` blocks (case-insensitive) and a trailing
 *  unclosed `` (orphan from streaming chunks) by treating the rest
 *  as an in-progress reasoning block. Nested/overlapping opening tags
 *  that fall inside an already-consumed think span are skipped so their
 *  content is not duplicated. */
export function splitThink(content: string): Segment[] {
  if (!content) return [];
  const segments: Segment[] = [];

  // Collect every opening tag occurrence up-front, then walk them in order,
  // pairing each with the next closing tag at/after it. Any opening tag whose
  // index is behind the current cursor sits inside an already-consumed think
  // span (nested/malformed input) and is skipped.
  const opens: { idx: number; len: number }[] = [];
  let m: RegExpExecArray | null;
  OPEN_RE.lastIndex = 0;
  while ((m = OPEN_RE.exec(content)) !== null) {
    opens.push({ idx: m.index, len: m[0].length });
  }

  let cursor = 0;
  for (const open of opens) {
    // Skip opening tags inside an already-consumed think span (nested input).
    if (open.idx < cursor) continue;
    // text before this think tag
    if (open.idx > cursor) {
      segments.push({ type: 'text', value: content.slice(cursor, open.idx) });
    }
    const thinkStart = open.idx + open.len;
    // find the next closing tag at or after thinkStart
    CLOSE_RE.lastIndex = thinkStart;
    const cm = CLOSE_RE.exec(content);
    if (cm) {
      segments.push({ type: 'think', value: content.slice(thinkStart, cm.index) });
      cursor = cm.index + cm[0].length;
    } else {
      // orphaned opening tag (streaming, not yet closed): rest is in-progress think
      segments.push({ type: 'think', value: content.slice(thinkStart) });
      cursor = content.length;
    }
  }
  // trailing text after the last think block (or the whole string if no think tags)
  if (cursor < content.length) {
    segments.push({ type: 'text', value: content.slice(cursor) });
  }
  if (segments.length === 0 && content.length > 0) {
    segments.push({ type: 'text', value: content });
  }
  return segments;
}
