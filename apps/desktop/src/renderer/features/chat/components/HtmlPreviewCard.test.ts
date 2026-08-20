import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { HtmlPreviewCard, detectHtmlDocument } from './HtmlPreviewCard';

describe('detectHtmlDocument', () => {
  it('detects a raw full HTML document', () => {
    const html =
      '<!doctype html><html><head><meta charset="utf-8"></head><body><h1>销售仪表盘</h1></body></html>';
    expect(detectHtmlDocument(html)).toBe(html);
  });

  it('detects HTML inside a ```html fenced block', () => {
    const fenced = '```html\n<html><body><p>ok</p></body></html>\n```';
    expect(detectHtmlDocument(fenced)).toBe('<html><body><p>ok</p></body></html>');
  });

  it('returns null for plain text and non-document HTML fragments', () => {
    expect(detectHtmlDocument('hello world')).toBeNull();
    expect(detectHtmlDocument('<div>fragment</div>')).toBeNull();
    expect(detectHtmlDocument('解释一下 <html> 标签的用法')).toBeNull();
  });
});

describe('HtmlPreviewCard', () => {
  it('renders a sandboxed iframe with the html as srcdoc in preview mode', () => {
    const html = '<html><body><h1>销售仪表盘</h1></body></html>';
    const markup = renderToStaticMarkup(createElement(HtmlPreviewCard, { html }));
    expect(markup).toContain('<iframe');
    expect(markup).toContain('sandbox');
    expect(markup).toContain('销售仪表盘');
    expect(markup).toContain('预览');
    expect(markup).toContain('源码');
  });
});
