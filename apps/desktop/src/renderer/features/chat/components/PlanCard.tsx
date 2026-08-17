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
  const [detailsOpen, setDetailsOpen] = useState(false);
  const waiting = entry.phase === 'wait_confirm';
  const running = entry.phase === 'running';
  const done = entry.phase === 'completed';
  const cancelled = entry.phase === 'cancelled';
  const accent = 'var(--accent, #2a7de1)';

  return (
    <div
      className="rounded-xl my-2 max-w-[520px] overflow-hidden"
      data-testid="plan-card"
      style={{
        background: 'var(--surface, #fff)',
        border: `1px solid ${waiting ? 'rgba(42,125,225,.35)' : 'var(--border-subtle, #eceef1)'}`,
        boxShadow: waiting ? '0 2px 12px rgba(42,125,225,.08)' : 'none',
      }}
    >
      {/* 标题行 */}
      <div className="flex items-center gap-2.5 px-3.5 pt-3 pb-2">
        <span
          className="w-7 h-7 rounded-lg flex items-center justify-center text-[13px] shrink-0"
          style={{ background: 'color-mix(in srgb, var(--accent, #2a7de1) 10%, transparent)', color: accent }}
        >
          📋
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[12.5px] font-semibold" style={{ color: 'var(--text, #1d2129)' }}>
            {entry.title}
          </div>
          {entry.goal && (
            <div className="text-[11.5px] mt-0.5 truncate" style={{ color: 'var(--text-muted, #6b7280)' }}>
              {entry.goal}
            </div>
          )}
        </div>
        {!waiting && (
          <span
            className="text-[10.5px] px-2 py-0.5 rounded-full shrink-0"
            style={{
              background: done ? 'rgba(52,199,123,.12)' : cancelled ? 'rgba(148,155,166,.12)' : 'rgba(42,125,225,.1)',
              color: done ? '#2fb27b' : cancelled ? '#8a919e' : accent,
            }}
          >
            {done ? '已完成' : cancelled ? '已取消' : '执行中'}
          </span>
        )}
      </div>

      {/* 执行计划（等待态展开；running 显示进度；历史折叠） */}
      {(waiting || running || detailsOpen) && (
        <div className="px-3.5 pb-1">
          <div className="flex flex-col gap-0.5">
            {entry.steps.map((s, i) => {
              const st = running || done ? entry.stepStatus?.[s.name] ?? 'pending' : 'pending';
              const active = st === 'running';
              return (
                <div
                  key={i}
                  className="flex items-center gap-2 py-[3px] text-[12.5px] rounded-md px-1"
                  style={{ background: active ? 'color-mix(in srgb, var(--accent, #2a7de1) 6%, transparent)' : 'none', color: 'var(--text, #1d2129)' }}
                >
                  <span
                    className="w-[18px] h-[18px] rounded-full flex items-center justify-center text-[9.5px] shrink-0"
                    style={{
                      background: st === 'done' ? 'rgba(52,199,123,.15)' : active ? 'rgba(42,125,225,.12)' : 'var(--surface-3, #f1f2f4)',
                      color: st === 'done' ? '#2fb27b' : active ? accent : 'var(--text-faint, #a0a6b0)',
                    }}
                  >
                    {st === 'done' ? '✓' : active ? '⟳' : st === 'failed' ? '!' : String(i + 1).padStart(2, '0')}
                  </span>
                  <span className="truncate">{s.name}</span>
                  {s.tools && s.tools.length > 0 && (
                    <span className="text-[10px] shrink-0 ml-auto" style={{ color: 'var(--text-faint, #a0a6b0)' }}>
                      {s.tools.join(' / ')}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 需要权限（仅等待态） */}
      {waiting && entry.permissions.length > 0 && (
        <div className="px-3.5 pt-1.5 pb-2">
          <div className="flex flex-wrap gap-1.5">
            {entry.permissions.map((p) => {
              const meta = PERM_LABELS[p] ?? { icon: '🔐', label: p };
              return (
                <span
                  key={p}
                  className="inline-flex items-center gap-1 px-2 py-[3px] rounded-md text-[10.5px]"
                  style={{ background: 'var(--surface-3, #f1f2f4)', color: 'var(--text-muted, #6b7280)' }}
                >
                  {meta.icon} {meta.label}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* 底部操作条 */}
      <div
        className="flex items-center justify-end gap-2 px-3.5 py-2"
        style={{ borderTop: '1px solid var(--border-subtle, #eceef1)' }}
      >
        {waiting ? (
          <>
            <button
              onClick={() => onResolve('cancel')}
              className="px-3.5 py-[6px] rounded-lg text-[12px] font-medium cursor-pointer hover:opacity-80"
              style={{ background: 'none', color: 'var(--text-muted, #6b7280)' }}
            >
              取消
            </button>
            <button
              onClick={() => onResolve('confirm')}
              className="px-4 py-[6px] rounded-lg text-[12px] font-semibold cursor-pointer hover:opacity-90"
              style={{ background: accent, color: '#fff', border: 'none' }}
            >
              开始执行
            </button>
          </>
        ) : (
          <button
            onClick={() => setDetailsOpen((v) => !v)}
            className="text-[11px] cursor-pointer hover:opacity-80"
            style={{ background: 'none', border: 'none', color: 'var(--text-faint, #a0a6b0)' }}
          >
            {detailsOpen ? '收起详情 ▴' : '展开详情 ▾'}
          </button>
        )}
      </div>
    </div>
  );
}
