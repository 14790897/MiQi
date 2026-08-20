```tsx
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

export function PlanCard({
  entry,
  onResolve,
}: {
  entry: PlanCardEntry;
  onResolve: (choiceId: string) => void;
}) {
  const [detailsOpen, setDetailsOpen] = useState<boolean | null>(null);
  const waiting = entry.phase === 'wait_confirm';
  const running = entry.phase === 'running';
  const done = entry.phase === 'completed';
  const cancelled = entry.phase === 'cancelled';
  const effectiveOpen = detailsOpen ?? (waiting || running);

  return (
    <div
      className="rounded-[20px] my-2 max-w-[520px] overflow-hidden bg-white"
      data-testid="plan-card"
      style={{
        border: '1px solid rgba(0, 0, 0, 0.05)',
        boxShadow: '0 6px 24px rgba(0, 0, 0, 0.03)',
      }}
    >
      {/* Header */}
      <div className="flex items-start gap-3 px-5 pt-5 pb-3">
        <span className="w-8 h-8 rounded-full bg-[#1f1f1f] text-white flex items-center justify-center text-[13px] shrink-0">
          📋
        </span>
        <div className="min-w-0 flex-1 pt-0.5">
          <div className="text-[14px] font-semibold leading-snug text-[#1a1a1a]">
            {entry.title}
          </div>
          {entry.goal && (
            <div className="text-[12px] mt-1 leading-relaxed text-[#8a8a8a]">
              {entry.goal}
            </div>
          )}
        </div>
        {!waiting && (
          <span className="text-[11px] text-[#8a8a8a] shrink-0 mt-0.5">
            {done ? '已完成' : cancelled ? '已取消' : '执行中'}
          </span>
        )}
      </div>

      {/* Steps */}
      {effectiveOpen && (
        <div className="px-5 pb-2">
          <div className="flex flex-col">
            {entry.steps.map((s, i) => {
              const st = running || done ? entry.stepStatus?.[s.name] ?? 'pending' : 'pending';
              const active = st === 'running';
              const isLast = i === entry.steps.length - 1;

              return (
                <div
                  key={i}
                  className="group flex items-start gap-3 py-2.5 text-[13px]"
                  style={{
                    color: active ? '#1a1a1a' : st === 'done' ? '#6b6b6b' : '#8a8a8a',
                  }}
                >
                  <div className="relative flex flex-col items-center pt-1.5 shrink-0">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{
                        background: st === 'done' ? '#22c55e' : active ? '#1f1f1f' : '#d4d4d4',
                      }}
                    />
                    {!isLast && (
                      <span
                        className="w-px flex-1 min-h-[20px] mt-1.5"
                        style={{ background: '#f0f0f0' }}
                      />
                    )}
                  </div>
                  <div className="flex-1 min-w-0 pt-0.5">
                    <div className={`leading-snug ${active ? 'font-medium' : 'font-normal'}`}>
                      {s.name}
                    </div>
                    {s.tools && s.tools.length > 0 && (
                      <div className="text-[11px] mt-1 text-[#b0b0b0]">
                        {s.tools.join(' / ')}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Permissions */}
      {waiting && entry.permissions.length > 0 && (
        <div className="px-5 pt-1 pb-4">
          <div className="text-[11px] text-[#b0b0b0] mb-2">需要权限</div>
          <div className="flex flex-wrap gap-2">
            {entry.permissions.map((p) => {
              const meta = PERM_LABELS[p] ?? { icon: '🔐', label: p };
              return (
                <span
                  key={p}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] text-[#6b6b6b] bg-[#f7f7f7]"
                >
                  {meta.icon} {meta.label}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-end gap-2 px-5 py-3.5 border-t border-[#f0f0f0]">
        {waiting ? (
          <>
            <button
              onClick={() => onResolve('cancel')}
              className="px-3 py-1.5 rounded-lg text-[12px] text-[#8a8a8a] hover:text-[#1a1a1a] hover:bg-[#f7f7f7] transition-colors cursor-pointer"
            >
              取消
            </button>
            <button
              onClick={() => onResolve('modify')}
              className="px-3 py-1.5 rounded-lg text-[12px] text-[#6b6b6b] hover:text-[#1a1a1a] hover:bg-[#f7f7f7] transition-colors cursor-pointer"
            >
              修改计划
            </button>
            <button
              onClick={() => onResolve('confirm')}
              className="px-4 py-1.5 rounded-lg text-[12px] font-medium text-white cursor-pointer hover:opacity-90 transition-opacity"
              style={{ background: '#1f1f1f' }}
            >
              开始执行
            </button>
          </>
        ) : (
          <button
            onClick={() => setDetailsOpen((v) => !v)}
            className="text-[11