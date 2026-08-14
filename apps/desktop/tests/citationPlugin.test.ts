import { describe, expect, it } from 'vitest';
import { remarkCitations } from '../src/renderer/features/chat/components/citation-plugin';
import { parseReferenceSection } from '../src/renderer/features/chat/components/CitationAnchor';

/** 构造最小 mdast（paragraph + text）并跑插件 transformer */
function transform(text: string, parentType: string = 'paragraph') {
  const tree: any = {
    type: 'root',
    children: parentType === 'paragraph' ? [{ type: 'paragraph', children: [{ type: 'text', value: text }] }] : [],
  };
  if (parentType === 'inlineCode') {
    tree.children = [{ type: 'paragraph', children: [{ type: 'inlineCode', value: text }] }];
  }
  if (parentType === 'code') {
    tree.children = [{ type: 'code', lang: 'text', value: text }];
  }
  const plugin = remarkCitations();
  (plugin as any)(tree, {} as any);
  return tree;
}

describe('remarkCitations（#671）', () => {
  it('把正文【n】转成 citation link', () => {
    const tree = transform('BET 损失约 8.7%【2】。');
    const p = tree.children[0];
    expect(p.type).toBe('paragraph');
    expect(p.children.map((c: any) => c.type)).toEqual(['text', 'link', 'text']);
    const link = p.children[1];
    expect(link.url).toBe('#citation-2');
    expect(link.data?.citationId).toBe('2');
    expect(link.children[0].value).toBe('【2】');
  });

  it('多个引用连续解析', () => {
    const tree = transform('结果【1】【3】均一致。');
    const p = tree.children[0];
    const links = p.children.filter((c: any) => c.type === 'link');
    expect(links.map((l: any) => l.data.citationId)).toEqual(['1', '3']);
  });

  it('inlineCode 里的【n】不解析', () => {
    const tree = transform('echo 【1】', 'inlineCode');
    expect(tree.children[0].children.map((c: any) => c.type)).not.toContain('link');
  });

  it('fenced code 块内的【n】不解析', () => {
    const tree = transform('【1】', 'code');
    expect(tree.children[0].type).toBe('code');
  });
});

describe('parseReferenceSection（#671 过渡版）', () => {
  it('解析文末参考文献【n】+ DOI', () => {
    const content = [
      '冷冻造粒影响较小【1】。',
      '',
      '### 参考文献',
      '',
      '【1】 Freeze granulation of MOF materials',
      'Journal of Materials Chemistry A, 2025',
      'DOI: 10.1039/example123',
    ].join('\n');
    const map = parseReferenceSection(content);
    expect(map.size).toBe(1);
    const r = map.get(1)!;
    expect(r.title).toContain('Freeze granulation');
    expect(r.doi).toBe('10.1039/example123');
  });

  it('无参考文献段时返回空', () => {
    expect(parseReferenceSection('普通回答没有引用')).toEqual(new Map());
  });

  it('URL 来源也解析', () => {
    const content = ['### 参考文献', '', '【2】 网页来源', 'https://example.com/page'].join('\n');
    const map = parseReferenceSection(content);
    expect(map.get(2)?.url).toBe('https://example.com/page');
  });
});
