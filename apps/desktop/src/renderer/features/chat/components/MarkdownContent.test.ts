import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MarkdownContent } from './MarkdownContent';

describe('MarkdownContent HTML preview swap', () => {
  it('renders the HtmlPreviewCard instead of markdown when content is a full HTML document', () => {
    const html =
      '<!doctype html><html><head><meta charset="utf-8"></head><body><h1>销售仪表盘</h1></body></html>';
    const markup = renderToStaticMarkup(createElement(MarkdownContent, { content: html }));
    expect(markup).toContain('HTML 预览');
    expect(markup).toContain('<iframe');
    expect(markup).toContain('sandbox');
    expect(markup).toContain('销售仪表盘');
  });

  it('renders the HTML inside a ```html fenced block as a preview card', () => {
    const fenced = '```html\n<html><body><p>ok</p></body></html>\n```';
    const markup = renderToStaticMarkup(createElement(MarkdownContent, { content: fenced }));
    expect(markup).toContain('<iframe');
  });

  it('keeps normal markdown rendering for non-HTML content', () => {
    const markup = renderToStaticMarkup(
      createElement(MarkdownContent, { content: '**加粗** 一段普通文本' })
    );
    expect(markup).not.toContain('<iframe');
    expect(markup).toContain('加粗');
  });

  it('renders mermaid fenced block with MermaidBlock (issue #671)', () => {
    const markup = renderToStaticMarkup(
      createElement(MarkdownContent, {
        content: '```mermaid\nflowchart TD\nA[开始] --> B[成型]\n```',
      })
    );
    // SSR 下 useEffect 不执行 → 未渲染前显示源码（muted 预览）
    expect(markup).toContain('flowchart TD');
    expect(markup).toContain('A[开始]');
  });

  it('keeps normal code block for non-mermaid fenced blocks', () => {
    const markup = renderToStaticMarkup(
      createElement(MarkdownContent, { content: '```python\nprint(1)\n```' })
    );
    expect(markup).toContain('print(1)');
  });
});

describe('MarkdownContent syntax highlighting', () => {
  it('adds a language label and hljs token spans to a fenced code block', () => {
    const md = '```ts\nconst x: number = 1;\n```';
    const markup = renderToStaticMarkup(createElement(MarkdownContent, { content: md }));
    expect(markup).toContain('>TypeScript</span>');
    expect(markup).toContain('hljs-keyword');
    expect(markup).toContain('hljs-built_in');
    expect(markup).toContain('hljs-number');
  });

  it('keeps plain text (no label, no hljs) for a code block without a language', () => {
    const md = '```\nplain text\n```';
    const markup = renderToStaticMarkup(createElement(MarkdownContent, { content: md }));
    expect(markup).toContain('plain text');
    expect(markup).not.toContain('hljs-keyword');
  });
});
