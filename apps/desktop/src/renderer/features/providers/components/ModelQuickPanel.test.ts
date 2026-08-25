import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import { ModelQuickPanel } from './ModelQuickPanel';
import type { ProviderInfo } from '../../../../shared/ipc';

function makeProvider(partial: Partial<ProviderInfo>): ProviderInfo {
  return {
    name: 'deepseek',
    display_name: 'DeepSeek',
    env_key: 'DEEPSEEK_API_KEY',
    provider_type: 'openai',
    is_gateway: false,
    is_local: false,
    default_api_base: 'https://api.deepseek.com/v1',
    api_base: null,
    configured: false,
    ...partial,
  };
}

describe('ModelQuickPanel（issue #788 一体化面板）', () => {
  it('未配置 provider 时显示 3 步引导', () => {
    const html = renderToStaticMarkup(
      createElement(ModelQuickPanel, {
        providers: [makeProvider({})],
        activeModel: '',
        activeProvider: null,
        onSaved: () => {},
      })
    );
    expect(html).toContain('模型与连接设置');
    expect(html).toContain('快速配置引导');
    expect(html).toContain('选择模型');
    expect(html).toContain('填写 API Key');
    expect(html).toContain('测试并保存');
    expect(html).toContain('测试连接');
    expect(html).toContain('保存并启用');
  });

  it('已配置 provider 时显示当前模型，不显示引导', () => {
    const html = renderToStaticMarkup(
      createElement(ModelQuickPanel, {
        providers: [makeProvider({ configured: true })],
        activeModel: 'deepseek/deepseek-chat',
        activeProvider: 'deepseek',
        onSaved: () => {},
      })
    );
    expect(html).toContain('deepseek/deepseek-chat');
    expect(html).not.toContain('快速配置引导');
  });

  it('内置支持的 provider 显示激活码提示', () => {
    const html = renderToStaticMarkup(
      createElement(ModelQuickPanel, {
        providers: [makeProvider({ builtin_available: true, builtin_activated: false })],
        activeModel: '',
        activeProvider: 'deepseek',
        onSaved: () => {},
      })
    );
    expect(html).toContain('内置支持');
    expect(html).toContain('激活码');
  });
});
