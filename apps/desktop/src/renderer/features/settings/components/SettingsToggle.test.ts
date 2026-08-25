import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import { Settings2 } from 'lucide-react';
import { SettingsToggle } from './SettingsToggle';

describe('SettingsToggle（issue #789 热生效提示）', () => {
  it('初始渲染开关按钮与测试 id（enabled 未加载时显示占位）', () => {
    const html = renderToStaticMarkup(
      createElement(SettingsToggle, {
        label: '沙箱',
        icon: Settings2,
        testId: 'sandbox-toggle',
        getInitial: () => true,
        onToggle: async () => {},
      })
    );
    expect(html).toContain('data-testid="sandbox-toggle-btn"');
    expect(html).toContain('data-testid="sandbox-toggle-label"');
    // SSR 下 useEffect 不执行 → enabled=null → 占位“…”
    expect(html).toContain('…');
  });

  it('支持 effect 类别（hot 默认 / new-session / restart 不抛错）', () => {
    for (const effect of ['hot', 'new-session', 'restart'] as const) {
      const html = renderToStaticMarkup(
        createElement(SettingsToggle, {
          label: '开关',
          icon: Settings2,
          testId: 't-' + effect,
          getInitial: () => false,
          onToggle: async () => {},
          effect,
          restartReason: 'Python 解释器路径',
        })
      );
      expect(html).toContain('data-testid="t-' + effect + '-btn"');
    }
  });
});
