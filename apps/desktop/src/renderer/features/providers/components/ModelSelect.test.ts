import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import { ModelSelect } from './ModelSelect';

describe('ModelSelect（issue #788 常用模型预设）', () => {
  it('后端不可用时回退预设列表（SSR：useEffect 不执行）', () => {
    const html = renderToStaticMarkup(
      createElement(ModelSelect, { value: 'deepseek/deepseek-chat', onChange: () => {} })
    );
    expect(html).toContain('deepseek/deepseek-chat');
    expect(html).toContain('deepseek/deepseek-reasoner');
    expect(html).toContain('openai/gpt-4o');
    expect(html).toContain('自定义模型');
  });

  it('当前值不在预设中时显示自定义输入框', () => {
    const html = renderToStaticMarkup(
      createElement(ModelSelect, { value: 'custom/my-model', onChange: () => {} })
    );
    expect(html).toContain('custom/my-model');
    expect(html).toContain('provider/model-name');
  });

  it('外部传入预设时使用外部预设', () => {
    const html = renderToStaticMarkup(
      createElement(ModelSelect, {
        value: 'x/y',
        onChange: () => {},
        presets: [
          {
            id: 'x/y',
            name: 'X Y',
            provider: 'x',
            providerDisplayName: 'X',
            hidden: false,
            default: false,
          },
        ],
      })
    );
    expect(html).toContain('x/y');
  });
});
