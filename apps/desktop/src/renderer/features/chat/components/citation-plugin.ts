/**
 * remark 插件（#671 citation，ChatGPT 决策 6）：
 * 正文文本节点里的【n】→ link node（data-citation-id），不建新 mdast 类型。
 *
 * - 只处理 text 节点；跳过 code / inlineCode / link 等已有结构（避免
 *   代码样例里的【1】被误转、引用里套引用）
 * - 只识别 【数字】，第一版不做 [1] / [2,3] / [^1] 等多格式（防解析器膨胀）
 */
import type { Root } from 'mdast';
import type { Plugin } from 'unified';
import { visit } from 'unist-util-visit';

const CITATION_RE = /【(\d+)】/g;

interface CitationLink {
  type: 'link';
  url: string;
  data?: Record<string, unknown>;
  children: Array<{ type: 'text'; value: string }>;
}

/** split 【n】 from a text node into text + citation-link nodes. */
function splitCitationText(value: string): Array<{ type: 'text'; value: string } | CitationLink> {
  const parts: Array<{ type: 'text'; value: string } | CitationLink> = [];
  let last = 0;
  CITATION_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = CITATION_RE.exec(value)) !== null) {
    if (m.index > last) parts.push({ type: 'text', value: value.slice(last, m.index) });
    parts.push({
      type: 'link',
      url: `#citation-${m[1]}`,
      data: { citationId: m[1] },
      children: [{ type: 'text', value: m[0] }],
    });
    last = m.index + m[0].length;
  }
  if (last < value.length) parts.push({ type: 'text', value: value.slice(last) });
  return parts;
}

export const remarkCitations: Plugin<[], Root> = () => (tree) => {
  visit(tree, 'text', (node: { value: string }, index, parent) => {
    if (!parent || index === undefined || index === null) return;
    // 跳过已有结构：链接内 / 行内代码内不解析（mdast 类型收窄，用 any 比较）
    const parentType = (parent as { type: string }).type;
    if (parentType === 'link' || parentType === 'inlineCode') return;
    if (!CITATION_RE.test(node.value)) return;
    CITATION_RE.lastIndex = 0; // reset after test()
    parent.children.splice(index, 1, ...splitCitationText(node.value));
  });
};
