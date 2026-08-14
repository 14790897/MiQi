/**
 * CitationAnchor — 正文引用标（#671，ChatGPT 决策 6/7）。
 *
 * remarkCitations 把【n】转成 link(data-citation-id) → 本组件渲染成
 * 可点击引用标，点击打开对应来源（DOI/URL，从文末参考文献解析）。
 *
 * 过渡期（9 月）：参考文献来自模型输出（model_declared），UI 不声称
 * "已验证"——诚实边界：只打开来源，不标注验证状态。
 */
import { useCallback, type ReactNode } from 'react';

export interface CitationRecord {
  id: number;
  title?: string;
  doi?: string;
  url?: string;
  /** 过渡期恒为 model_declared；后续与 #547 SourceRecord 对接后升级 */
  provenance?: 'model_declared' | 'system_verified';
}

/** 从文末「### 参考文献」段解析【n】条目（过渡版，模型输出格式） */
export function parseReferenceSection(content: string): Map<number, CitationRecord> {
  const map = new Map<number, CitationRecord>();
  const m = content.match(/###\s*参考文献[\s\S]*$/);
  if (!m) return map;
  // 每行：【n】 标题 / DOI: 10.xxx / URL
  let current: CitationRecord | null = null;
  for (const line of m[0].split('\n')) {
    const head = line.match(/^\s*【(\d+)】\s*(.*)$/);
    if (head) {
      current = { id: Number(head[1]), title: head[2].trim() };
      map.set(current.id, current);
      continue;
    }
    if (!current) continue;
    const doi = line.match(/doi\s*[:：]\s*(10\.\S+)/i);
    if (doi) current.doi = doi[1].replace(/[.,;:]\s*$/, '');
    const url = line.match(/https?:\/\/\S+/);
    if (url && !doi) current.url = url[0].replace(/[.,;:)\]]\s*$/, '');
  }
  return map;
}

export function CitationAnchor({
  citationId,
  children,
  registry,
}: {
  citationId: number;
  children: ReactNode;
  registry: Map<number, CitationRecord>;
}) {
  const rec = registry.get(citationId);

  const open = useCallback(() => {
    if (!rec) return;
    const target = rec.doi ? `https://doi.org/${rec.doi}` : rec.url;
    if (target) window.open(target, '_blank');
  }, [rec]);

  return (
    <sup
      onClick={open}
      title={rec ? `${rec.title ?? '来源'}${rec.doi ? ` · DOI: ${rec.doi}` : ''}` : `引用 ${citationId}`}
      style={{
        cursor: rec?.doi || rec?.url ? 'pointer' : 'default',
        color: 'var(--accent)',
        fontWeight: 600,
        fontSize: 11,
        lineHeight: 0,
        padding: '0 1px',
      }}
    >
      {children}
    </sup>
  );
}
