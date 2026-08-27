import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { PlanCard, type PlanCardEntry } from './PlanCard';

function entry(overrides: Partial<PlanCardEntry> = {}): PlanCardEntry {
  return {
    title: '生成 MOF 实验报告',
    goal: '整理 5 篇论文并生成 Workflow',
    steps: [
      { name: '论文检索', tools: ['web_search'] },
      { name: '生成报告', tools: ['write_file'] },
      { name: '上传 Qraft', tools: ['upload'] },
    ],
    permissions: ['network_read', 'workspace_write', 'external_upload'],
    phase: 'wait_confirm',
    ...overrides,
  };
}

function render(e: PlanCardEntry): string {
  return renderToStaticMarkup(createElement(PlanCard, { entry: e, onResolve: () => {} }));
}

describe('PlanCard (#646-v2)', () => {
  it('wait_confirm: renders title + plan + permissions + start button', () => {
    const html = render(entry());
    expect(html).toContain('生成 MOF 实验报告');
    expect(html).toContain('论文检索');
    expect(html).toContain('网络访问');
    expect(html).toContain('外部上传');
    expect(html).toContain('开始执行');
  });

  it('running: shows step progress, no start button', () => {
    const e = entry({ phase: 'running', stepStatus: { '论文检索': 'done', '生成报告': 'running' } });
    const html = render(e);
    expect(html).toContain('执行中');
    expect(html).not.toContain('开始执行');
    expect(html).not.toContain('需要权限');
    expect(html).not.toContain('网络访问');
  });

  it('completed / cancelled: summary badge states', () => {
    expect(render(entry({ phase: 'completed' }))).toContain('已完成');
    expect(render(entry({ phase: 'cancelled' }))).toContain('已取消');
  });
});
