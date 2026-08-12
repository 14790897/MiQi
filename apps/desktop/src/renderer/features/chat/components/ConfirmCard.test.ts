import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { IPC, IPC_EVENTS } from '../../../../shared/ipc';
import type { UserInputCardEntry } from '../../../contexts/UserInputContext';
import { ConfirmCard } from './ConfirmCard';

const NOW = '12:03:21';

function entry(overrides: Partial<UserInputCardEntry> = {}): UserInputCardEntry {
  return {
    request: {
      input_id: 'user_input_abc123',
      title: '确认执行方案？',
      message: '我将执行 4 个步骤，包含：',
      steps: [
        { id: 'search_papers', title: '搜索并下载相关论文' },
        { id: 'query_price', title: '查询供应商价格（国内）' },
      ],
      choices: [
        { id: 'confirm', label: '确认执行' },
        { id: 'cancel', label: '取消' },
      ],
      timeout_seconds: 120,
      allow_remember_choice: true,
    },
    state: 'pending',
    ...overrides,
  };
}

function render(entry_: UserInputCardEntry): string {
  return renderToStaticMarkup(
    createElement(ConfirmCard, { entry: entry_, onResolve: () => {}, nowFn: () => NOW }),
  );
}

describe('IPC channels (issue #646)', () => {
  it('defines resolve channel + renderer event names', () => {
    expect(IPC.USER_INPUT_RESOLVE).toBe('userInput:resolve');
    expect(IPC_EVENTS.USER_INPUT_REQUEST).toBe('userInput:request');
    expect(IPC_EVENTS.USER_INPUT_RESOLVED).toBe('userInput:resolved');
  });
});

describe('ConfirmCard', () => {
  it('pending: renders choices, remember checkbox and countdown', () => {
    const html = render(entry());
    expect(html).toContain('等待你的选择');
    expect(html).toContain('确认执行');
    expect(html).toContain('取消');
    expect(html).toContain('本次会话不再询问');
    expect(html).toContain('120s');
    expect(html).toContain('搜索并下载相关论文');
  });

  it('pending without remember flag hides the checkbox', () => {
    const e = entry();
    e.request.allow_remember_choice = false;
    const html = render(e);
    expect(html).not.toContain('本次会话不再询问');
  });

  it('confirmed: shows the picked choice, no choices/countdown', () => {
    const e = entry({
      state: 'confirmed',
      choiceId: 'confirm',
      choiceLabel: '确认执行',
      resolvedAt: new Date('2026-08-11T12:03:21').getTime(),
    });
    const html = render(e);
    expect(html).toContain('✓ 已确认');
    expect(html).toContain('已选择「确认执行」');
    expect(html).toContain(NOW);
    expect(html).not.toContain('等待你的选择');
    expect(html).not.toContain('本次会话不再询问');
    expect(html).not.toContain('120s');
    expect(html).not.toContain('data-testid="countdown"');
  });

  it('cancelled: neutral grey end state, not an error card', () => {
    const e = entry({
      state: 'cancelled',
      choiceId: 'cancel',
      choiceLabel: '取消',
      resolvedAt: new Date('2026-08-11T12:03:21').getTime(),
    });
    const html = render(e);
    expect(html).toContain('已取消');
    expect(html).toContain('已选择「取消」');
    // neutral: no error styling class or red accents on the badge
    expect(html).not.toContain('var(--danger)');
    expect(html).not.toContain('等待你的选择');
  });

  it('defaults choices when backend sends none', () => {
    const e = entry();
    e.request.choices = [];
    const html = render(e);
    expect(html).toContain('确认执行');
    expect(html).toContain('调整方案');
    expect(html).toContain('取消');
  });

  it('collapses steps beyond 4 with an expand button', () => {
    const e = entry();
    e.request.steps = Array.from({ length: 7 }, (_, i) => ({
      id: `step_${i}`,
      title: `步骤 ${i + 1}`,
    }));
    const html = render(e);
    // 前 4 步可见，后 3 步被折叠
    expect(html).toContain('步骤 1');
    expect(html).toContain('步骤 4');
    expect(html).not.toContain('步骤 5');
    expect(html).toContain('展开全部 7 个步骤');
  });
});
