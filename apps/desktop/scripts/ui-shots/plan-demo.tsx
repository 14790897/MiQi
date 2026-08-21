/**
 * PlanCard 视觉评审演示页（#646-v2）：wait_confirm / running / completed 三态。
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { PlanCard, type PlanCardEntry } from '../../src/renderer/features/chat/components/PlanCard';

const base: PlanCardEntry = {
  title: '生成 MOF 实验报告',
  goal: '整理 5 篇论文并生成 Workflow，上传 Qraft',
  steps: [
    { name: '搜集论文资料' },
    { name: '提取实验参数' },
    { name: '创建实验报告' },
    { name: '上传到 Qraft' },
  ],
  permissions: ['network_read', 'workspace_write', 'external_upload'],
  phase: 'wait_confirm',
};

const root = createRoot(document.getElementById('root')!);
root.render(
  <div style={{ fontFamily: 'system-ui', padding: 24, display: 'flex', flexDirection: 'column', gap: 20, background: '#f5f6e5', minHeight: '100vh' }}>
    <PlanCard entry={base} onResolve={() => {}} />
    <PlanCard
      entry={{
        ...base,
        phase: 'running',
        stepStatus: { '论文检索': 'done', '提取实验参数': 'done', '创建报告': 'running', '上传 Qraft': 'pending' },
      }}
      onResolve={() => {}}
    />
    <PlanCard entry={{ ...base, phase: 'completed', stepStatus: { '论文检索': 'done', '提取实验参数': 'done', '创建报告': 'done', '上传 Qraft': 'done' } }} onResolve={() => {}} />
  </div>
);
