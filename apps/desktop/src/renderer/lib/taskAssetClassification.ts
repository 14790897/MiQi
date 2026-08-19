/**
 * Task Assets 结果/过程资产分类 (issue #607)
 *
 * Frontend-only heuristic — no backend schema change, no manual marking.
 * 结果资产 = 任务最终交付物；过程资产 = 中间产物/脚本/临时文件/引用上下文。
 *
 * WHITELIST RULES (user-specified 2026-08-13 — MOF journey; #715 扩充):
 * 1. filename markers (temp/tmp/debug/draft/scratch/backup/cache/working/old/bak,
 *    stepN, .log) → process, even for deliverable formats.
 * 2. delete → process (removed files are never deliverables).
 * 3. deliverable formats (excel/word/pdf/svg/html — 2026-08-18 扩充 svg/html:
 *    graph_render 渲染产物即交付物, issue #715) → results, regardless of op
 *    (a READ of a deliverable usually means a subprocess wrote it and the
 *    agent inspected it — the write was invisible to tracking).
 * 4. everything else (md/json/csv/txt/py/…) → process.
 *
 * Results sorted lastSeen DESC (newest first); process ASC.
 */

/** Deliverable document whitelist — excel/word/pdf/svg/html (user-specified). */
export const DELIVERABLE_EXT_RE = /\.(?:docx?|xlsx?|pdf|svg|html?)$/i;

/** Conservative filename markers — `step_by_step_guide.md` must NOT match. */
export const PROCESS_FILE_NAME_RE =
  /(?:^|[._-])(?:temp|tmp|debug|draft|scratch|backup|cache|working|old|bak)\d*(?:[._-]|$)|(?:^|[._-])step\d+(?:[._-]|$)|\.log$/i;

export function isProcessFileName(name: string): boolean {
  return PROCESS_FILE_NAME_RE.test(name);
}

export interface ClassifiableTrackedFile {
  name: string;
  op: string;
  lastSeen: number;
}

export function classifyTrackedFiles<T extends ClassifiableTrackedFile>(
  files: T[]
): { results: T[]; process: T[] } {
  const results: T[] = [];
  const process: T[] = [];

  for (const file of files) {
    if (isProcessFileName(file.name) || file.op === 'delete') {
      process.push(file);
    } else if (DELIVERABLE_EXT_RE.test(file.name)) {
      results.push(file);
    } else {
      process.push(file);
    }
  }

  results.sort((a, b) => b.lastSeen - a.lastSeen);
  process.sort((a, b) => a.lastSeen - b.lastSeen);
  return { results, process };
}
