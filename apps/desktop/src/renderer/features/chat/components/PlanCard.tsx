/**
 * PlanCard — 任务计划卡（#646-v2，GPT 评审拍板）。
 *
 * 与 ConfirmCard 的分工：
 * - PlanCard：任务开始前**一次**（多步骤任务）——展示计划+权限清单，用户[开始执行]
 * - ConfirmCard：危险动作（上传/支付/删除）最后确认
 *
 * 不是审批弹窗——是 AI 助手展示计划（Claude Code 式体验）。
 * 状态随 TaskState 变化：planning → running（步骤进度）→ completed/cancelled。
 */
import { useState } from 'react';

export interface PlanStep {
  name: string;
  tools?: string[];
}

export interface PlanCardEntry {
  title: string;
  goal: string;
  steps: PlanStep[];
  permissions: string[];
  /** 任务状态（TaskState phase） */
  phase: 'wait_confirm' | 'running' | 'completed' | 'cancelled' | 'wait_dangerous';
  /** 步骤状态（name → pending/running/done/failed） */
  stepStatus?: Record<string, string>;
}

const PERM_LABELS: Record<string, { icon: string; label: string }> = {
  network_read: { icon: '🌐', label: '网络访问' },
  workspace_write: { icon: '📄', label: '创建/修改文件' },
  external_upload: { icon: '☁', label: '外部上传' },
  exec: { icon: '⚡', label: '执行命令' },
};

const STEP_ICONS: Record<string, string> = {
  done: '✓',
  running: '⟳',
  failed: '!',
  pending: '○',
};

export function PlanCard({
  entry,
  onResolve,
}: {
  entry: PlanCardEntry;
  onResolve: (choiceId: string) => void;
}) {
  const waiting = entry.phase === 'wait_confirm';
  const running = entry.phase === 'running';
  const done = entry.phase === 'completed';
  const cancelled = entry.phase === 'cancelled';

  return (
    <div
      className="rounded-2xl p-4 my-2 max-w-[520px]"
      data-testid="plan-card"
      style={{
        background: waiting ? 'color-mix(in srgb, var(--accent) 6%, var(--surface))' : 'var(--surface)',
        border: `1px solid ${waiting ? 'var(--accent)' : 'var(--border-subtle)'}`,
      }}
    >
      {/* 标题行 */}
      <div className="flex items-start gap-2.5 mb-2">
        <span className="text-[15px]">📋</span>
        <div className="min-w-0 flex-1">
          <div className="text-[13.5px] font-semibold" style={{ color: 'var(--text)' }}>
            {waiting ? '准备执行任务' : done ? '任务已完成' : cancelled ? '任务已取消' : '正在执行任务'}
          </div>
          <div className="text-[14px] font-semibold mt-0.5" style={{ color: 'var(--text)' }}>
            {entry.title}
          </div>
          {entry.goal && (
            <div className="text-[12px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
              {entry.goal}
            </div>
          )}
        </div>
      </div>

      {/* 执行计划 */}
      {entry.steps.length > 0 && (
        <div className="mb-2.5">
          <div className="text-[11px] font-semibold uppercase tracking-wider mb-1" style={{ color: 'var(--text-faint)' }}>
            执行计划
          </div>
          <div className="flex flex-col gap-1">
            {entry.steps.map((s, i) => {
              const st = running || done ? entry.stepStatus?.[s.name] ?? 'pending' : 'pending';
              const icon = st === 'pending' && !running && !done ? String(i + 1).padStart(2, '0') : STEP_ICONS[st] ?? '○';
              return (
                <div key={i} className="flex items-center gap-2 text-[12.5px]" style={{ color: 'var(--text)' }}>
                  <span
                    className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] shrink-0"
                    style={{
                      background: st === 'done' ? 'var(--success-bg)' : st === 'running' ? 'var(--accent-bg)' : 'var(--surface-3)',
                      color: st === 'done' ? 'var(--success-text)' : st === 'running' ? 'var(--accent)' : 'var(--text-faint)',
                    }}
                  >
                    {icon}
                  </span>
                  <span className="truncate">{s.name}</span>
                  {s.tools && s.tools.length > 0 && (
                    <span className="text-[10.5px] shrink-0" style={{ color: 'var(--text-faint)' }}>
                      {s.tools.join(' / ')}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 所需权限 */}
      {waiting && entry.permissions.length > 0 && (
        <div className="mb-3">
          <div className="text-[11px] font-semibold uppercase tracking-wider mb-1" style={{ color: 'var(--text-faint)' }}>
            需要权限
          </div>
          <div className="flex flex-wrap gap-1.5">
            {entry.permissions.map((p) => {
              const meta = PERM_LABELS[p] ?? { icon: '🔐', label: p };
              return (
                <span
                  key={p}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px]"
                  style={{ background: 'var(--surface-3)', color: 'var(--text-muted)' }}
                >
                  {meta.icon} {meta.label}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* 操作 */}
      {waiting && (
        <div className="flex justify-end gap-2 pt-1">
          <button
            onClick={() => onResolve('cancel')}
            className="px-3 py-1.5 rounded-lg text-[12.5px] font-medium cursor-pointer"
            style={{ background: 'none', border: '1px solid var(--border)', color: 'var(--text-muted)' }}
          >
            取消
          </button>
          <button
            onClick={() => onResolve('confirm')}
            className="px-4 py-1.5 rounded-lg text-[12.5px] font-semibold cursor-pointer"
            style={{ background: 'var(--accent)', color: '#fff', border: 'none' }}
          >
            开始执行
          </button>
        </div>
      )}

      {/* 完成/取消摘要 */}
      {!waiting && (
        <div className="flex justify-end pt-1 text-[11px]" style={{ color: 'var(--text-faint)' }}>
          {done ? '✓ 任务完成' : cancelled ? '○ 已取消' : '执行中…'}
        </div>
      )}
    </div>
  );
}
