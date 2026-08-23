import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MarkdownContent } from './MarkdownContent';

describe('MarkdownContent HTML preview swap', () => {
  it('renders the HtmlPreviewCard instead of markdown when content is a full HTML document', () => {
    const html = '<!doctype html><html><head><meta charset="utf-8"></head><body><h1>销售仪表盘</h1></body></html>';
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
});
