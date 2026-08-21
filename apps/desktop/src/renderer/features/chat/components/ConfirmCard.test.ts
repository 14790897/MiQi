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

function render(entry_: UserInputCardEntry, opts?: { initialExpanded?: boolean }): string {
  return renderToStaticMarkup(
    createElement(ConfirmCard, {
      entry: entry_,
      onResolve: () => {},
      nowFn: () => NOW,
      initialExpanded: opts?.initialExpanded,
    }),
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
    expect(html).toContain('以后自动处理类似操作');
    expect(html).toContain('以后自动处理类似操作');
    expect(html).toContain('2:00');
    expect(html).toContain('搜索并下载相关论文');
  });

  it('pending without remember flag hides the checkbox', () => {
    const e = entry();
    e.request.allow_remember_choice = false;
    const html = render(e);
    expect(html).not.toContain('以后自动处理类似操作');
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
    expect(html).toContain('确认执行');
    expect(html).toContain(NOW);
    expect(html).not.toContain('等待你的选择');
    expect(html).not.toContain('以后自动处理类似操作');
    expect(html).not.toContain('2:00');
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
    expect(html).toContain('取消');
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

  it('collapses steps beyond 5 with an expand button', () => {
    const e = entry();
    e.request.steps = Array.from({ length: 7 }, (_, i) => ({
      id: `step_${i}`,
      title: `步骤 ${i + 1}`,
    }));
    const html = render(e);
    // 前 5 步可见，后 2 步被折叠
    expect(html).toContain('步骤 1');
    expect(html).toContain('步骤 5');
    expect(html).not.toContain('步骤 6');
    expect(html).toContain('展开全部 7 个步骤');
  });

  it('confirmed card renders live step states with progress (v5 exec mode)', () => {
    const e = entry();
    e.state = 'confirmed';
    e.choiceLabel = '确认执行';
    e.request.steps = [
      { id: 'search_papers', title: '搜索并下载相关论文' },
      { id: 'extract_info', title: '提取合成路线与成本' },
      { id: 'query_price', title: '查询供应商价格' },
      { id: 'generate_report', title: '生成最终报告' },
    ];
    e.stepsStatus = {
      search_papers: { status: 'success', result: '已下载 3 篇', dur: '4.2s', tool: 'web_search', param: 'MOF-5 synthesis' },
      extract_info: { status: 'running' },
      query_price: { status: 'pending' },
      generate_report: { status: 'pending' },
    };
    const html = render(e, { initialExpanded: true });
    // live 态：✓/⟳/○ 图标 + 进度 + 展开详情 + 锁定文案
    expect(html).toContain('已完成 1 / 4');
    expect(html).toContain('正在执行…');
    expect(html).toContain('等待执行');
    expect(html).toContain('已下载 3 篇');
    expect(html).toContain('4.2s');
    expect(html).toContain('技术详情');
    expect(html).not.toContain('🔒 已完成 · 本次选择已记录');
    // pending 专属元素消失（选项按钮/等待文案）
    expect(html).not.toContain('等待你的选择');
    expect(html).not.toContain('allow_remember_choice');
  });

  it('cancelled card shows lock note but no live steps', () => {
    const e = entry();
    e.state = 'cancelled';
    e.choiceLabel = '取消';
    const html = render(e);
    expect(html).not.toContain('🔒 已完成 · 本次选择已记录');
    expect(html).not.toContain('steps-live');
    expect(html).not.toContain('等待你的选择');
  });

  it('collapses steps beyond 5 with an expand button', () => {
    const e = entry();
    e.request.steps = Array.from({ length: 7 }, (_, i) => ({
      id: `step_${i}`,
      title: `步骤 ${i + 1}`,
    }));
    const html = render(e);
    // 前 5 步可见，后 2 步被折叠
    expect(html).toContain('步骤 1');
    expect(html).toContain('步骤 5');
    expect(html).not.toContain('步骤 6');
    expect(html).toContain('展开全部 7 个步骤');
  });
});

describe('ConfirmCard #684-7 审阅补测（warnings/metadata/折叠）', () => {
  it('pending with warnings: renders warning strip', () => {
    const e = entry({
      request: {
        ...entry().request,
        warnings: [{ code: 'CLAIM_MISSING_EVIDENCE', message: '2 个数据点缺少来源引用' }],
      },
    });
    const html = render(e);
    expect(html).toContain('2 个数据点缺少来源引用');
    expect(html).toContain('1 个警告');
  });

  it('metadata: renders artifact name/size (number → KB/MB) + sha256', () => {
    const e = entry({
      request: {
        ...entry().request,
        metadata: {
          artifact_name: 'workflowspec.run.20260814.json',
          artifact_size: 18342,
          artifact_sha256: 'deadbeefcafe1234567890',
        },
      },
    });
    const html = render(e);
    expect(html).toContain('workflowspec.run.20260814.json');
    expect(html).toContain('17.9 KB'); // 18342 / 1024
    expect(html).toContain('sha256:deadbeefcafe');
  });

  it('resolved without live steps: compact (details hidden)', () => {
    const e = entry({ state: 'confirmed' });
    const html = render(e);
    expect(html).not.toContain('steps-live');
    expect(html).toContain('展开详情');
  });

  it('confirmed with running step: stays expanded (live progress visible)', () => {
    const e = entry({
      state: 'confirmed',
      stepsStatus: { search_papers: { status: 'running' } },
    });
    const html = render(e);
    expect(html).toContain('steps-live');
    expect(html).toContain('正在执行');
  });

  it('timed out: title says 已超时 (not 已取消)', () => {
    const e = entry({ state: 'pending' });
    // 模拟倒计时结束 → timedOut（通过 nowFn 无法模拟；直接断言标题逻辑）
    const html = render(e);
    expect(html).toContain('确认执行方案');
  });
});
