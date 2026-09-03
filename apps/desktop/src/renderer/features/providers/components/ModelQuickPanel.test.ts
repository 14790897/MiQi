import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import { ModelQuickPanel } from './ModelQuickPanel';

describe('ModelQuickPanel（#835 合规收口后）', () => {
  it('未登录时显示登录门控，隐藏自定义配置入口', () => {
    // renderToStaticMarkup 不跑 useEffect，useQraftStatus 初始 status 为 null →
    // loggedIn=false，应渲染登录引导而非模型下拉。
    const html = renderToStaticMarkup(
      createElement(ModelQuickPanel, {
        activeModel: 'deepseek/deepseek-v4-flash',
        onSaved: () => {},
        onGoToQraft: () => {},
      })
    );
    expect(html).toContain('模型设置');
    expect(html).toContain('默认模型');
    expect(html).toContain('登录后使用平台内置模型');
    expect(html).toContain('去登录');
    // 收口后不再出现自配 API Key / Base URL 入口
    expect(html).not.toContain('API Key');
    expect(html).not.toContain('API Base URL');
    expect(html).not.toContain('快速配置引导');
  });
});
