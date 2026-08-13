/**
 * 确认卡 UI 截图展示页（Kimi 视觉评审用）
 * 渲染真实 ConfirmCard 组件的 5 个状态，放在模拟聊天布局中。
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { ConfirmCard } from '../../src/renderer/features/chat/components/ConfirmCard';
import type { UserInputCardEntry } from '../../src/renderer/contexts/UserInputContext';

declare global {
  interface Window {
    __shots: () => void;
  }
}

const NOW = '14:03';

function entry(over: Partial<UserInputCardEntry>): UserInputCardEntry {
  return {
    request: {
      input_id: 'card_1',
      thread_id: 'thr_1',
      toolName: 'web_fetch',
      title: '确认访问外部网页？',
      message: 'AI 想访问外部网页：\nhttps://vicena.ai/wiki/solvothermal-synthesis-of-mof-5-X8ga8A',
      choices: [
        { id: 'confirm', label: '确认执行', role: 'confirm' },
        { id: 'cancel', label: '取消', role: 'cancel' },
      ],
      timeout_seconds: 120,
      allow_remember_choice: true,
    },
    state: 'pending',
    ...over,

  };
}

const PENDING = entry();
const CONFIRMED = entry({
  state: 'confirmed',
  choiceId: 'confirm',
  choiceLabel: '确认执行',
  resolvedAt: new Date().getTime(),
});
const CANCELLED = entry({
  state: 'cancelled',
  choiceId: 'cancel',
  choiceLabel: '取消',
  resolvedAt: new Date().getTime(),
});
const TIMED_OUT = entry({
  state: 'cancelled',
  timedOut: true,
  resolvedAt: new Date().getTime(),
});
const UPLOAD = entry({
  request: {
    ...entry().request,
    toolName: 'upload_workflow',
    title: '确认上传方案到 Qraft？',
    message: 'WorkflowRun 校验通过，即将上传到 Qraft 平台。',
    warnings: [
      { code: 'CLAIM_MISSING_EVIDENCE', message: '2 个数据点缺少来源引用' },
    ],
    metadata: { run_id: 'ab12cd34', artifact_name: 'run.json', artifact_size: '18 KB', artifact_sha256: 'deadbeef12345678' },
    choices: [
      { id: 'confirm', label: '确认上传', role: 'confirm' },
      { id: 'modify', label: '返回修改', role: 'adjust' },
      { id: 'cancel', label: '取消', role: 'cancel' },
    ],
  },
});

const STEPS = entry({
  request: {
    ...entry().request,
    toolName: 'write_file',
    title: '确认执行调研方案？',
    message: '我将按以下 4 个步骤执行：',
    steps: [
      { id: 's1', title: '搜索并下载相关论文' },
      { id: 's2', title: '提取 MOF-5 合成路线与成本' },
      { id: 's3', title: '查询供应商价格（国内）' },
      { id: 's4', title: '生成最终报告' },
    ],
    choices: [
      { id: 'confirm', label: '确认执行', role: 'confirm' },
      { id: 'adjust', label: '调整方案', role: 'adjust' },
      { id: 'cancel', label: '取消', role: 'cancel' },
    ],
  },
});

function Message({ role, children }: { role: 'user' | 'ai'; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', gap: 10, marginBottom: 12, justifyContent: role === 'user' ? 'flex-end' : 'flex-start' }}>
      {role === 'ai' && (
        <div
          style={{
            width: 32, height: 32, borderRadius: 9, flexShrink: 0,
            background: 'linear-gradient(135deg,#4db2ff,#2a7de1)', color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 12, fontWeight: 600,
          }}
        >
          AI
        </div>
      )}
      <div
        style={{
          maxWidth: 560, padding: '10px 14px', borderRadius: 12, fontSize: 14, lineHeight: 1.6,
          background: role === 'user' ? 'var(--bubble-user-bg)' : 'var(--bubble-ai-bg)',
          color: role === 'user' ? 'var(--bubble-user-text)' : 'var(--bubble-ai-text)',
          border: role === 'user' ? 'none' : '1px solid var(--bubble-ai-border)',
        }}
      >
        {children}
      </div>
    </div>
  );
}

function CardScene({ name, card, userMsg, aiMsg }: { name: string; card: UserInputCardEntry; userMsg: string; aiMsg: string }) {
  return (
    <div className="scene" data-scene={name}>
      <Message role="user">{userMsg}</Message>
      <Message role="ai">{aiMsg}</Message>
      <div style={{ display: 'flex', gap: 10 }}>
        <div
          style={{
            width: 32, height: 32, borderRadius: 9, flexShrink: 0, marginTop: 2,
            background: 'linear-gradient(135deg,#4db2ff,#2a7de1)', color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 600,
          }}
        >
          AI
        </div>
        <div style={{ minWidth: 0 }}>
          <ConfirmCard
            entry={card}
            nowFn={() => NOW}
            onResolve={() => {}}
          />
        </div>
      </div>
    </div>
  );
}

function App() {
  return (
    <div style={{ background: 'var(--background)', minHeight: '100vh', padding: 24, fontFamily: 'var(--font-display)' }}>
      <div style={{ maxWidth: 720, margin: '0 auto' }}>
        <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 4 }}>确认卡 UI 快照</div>
        <div style={{ fontSize: 13, color: 'var(--text-faint)', marginBottom: 24 }}>5 个状态 · 真实组件渲染 · Kimi 视觉评审用</div>

        <CardScene name="upload" card={UPLOAD} userMsg="把 MOF-5 方案上传到 Qraft" aiMsg="校验通过（2 个 B 级警告），请确认上传。" />
        <CardScene name="pending" card={PENDING} userMsg="帮我搜索 MOF-5 的合成方法" aiMsg="好的，我先搜索相关文献，然后抓取 2 个网页详情。" />
        <CardScene name="steps" card={STEPS} userMsg="调研 MOF-5 市场并生成报告" aiMsg="我整理了 4 步执行方案，请确认后开始。" />
        <CardScene name="confirmed" card={CONFIRMED} userMsg="继续" aiMsg="" />
        <CardScene name="cancelled" card={CANCELLED} userMsg="不用了" aiMsg="好的，已取消。" />
        <CardScene name="timedout" card={TIMED_OUT} userMsg="" aiMsg="" />
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
