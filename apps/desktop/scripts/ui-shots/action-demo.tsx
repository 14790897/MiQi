/**
 * ActionCard 视觉评审演示页（#646-v2）：upload/payment/delete 三态。
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { ActionCard, type ActionCardEntry } from '../../src/renderer/features/chat/components/ActionCard';

const base: ActionCardEntry = {
  action: 'upload',
  target: 'Qraft',
  fileName: 'workflow.json',
  sizeBytes: 23 * 1024,
  sha256: 'deadbeef1234567890abcdef1234567890',
  description: '上传 MOF-5 实验 workflow 到 Qraft',
};

const root = createRoot(document.getElementById('root')!);
root.render(
  <div style={{ fontFamily: 'system-ui', padding: 24, display: 'flex', flexDirection: 'column', gap: 20, background: '#f5f6e5', minHeight: '100vh' }}>
    <ActionCard entry={base} onResolve={() => {}} />
    <ActionCard entry={{ ...base, action: 'payment', target: 'DeepSeek API', fileName: '账单.pdf', sizeBytes: 12 * 1024 }} onResolve={() => {}} />
    <ActionCard entry={{ ...base, action: 'delete', target: '工作区', fileName: 'archive/', description: '删除 archive 目录（含 120 个文件）' }} onResolve={() => {}} />
  </div>
);
