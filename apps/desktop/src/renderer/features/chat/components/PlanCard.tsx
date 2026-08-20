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
  // 折叠控制（与思维列表一致）：waiting/running 默认展开，resolved 默认收起；
  // 用户手动点过展开/收起则优先
  const [detailsOpen, setDetailsOpen] = useState<boolean | null>(null);
  const waiting = entry.phase === 'wait_confirm';
  const running = entry.phase === 'running';
  const done = entry.phase === 'completed';
  const cancelled = entry.phase === 'cancelled';
  const effectiveOpen = detailsOpen ?? (waiting || running);
  const accent = 'var(--accent, #2a7de1)';

  return (
    <div
      className="rounded-[16px] my-2 w-full max-w-full overflow-hidden"
      data-testid="plan-card"
      style={{
        background: '#ffffff',
        border: waiting ? '1px solid rgba(42,125,225,.25)' : '1px solid rgba(0,0,0,.06)',
        boxShadow: '0 1px 4px rgba(0,0,0,.04), 0 4px 16px rgba(0,0,0,.04)',
      }}
    >
      {/* 标题行 */}
      <div className="flex items-center gap-2.5 px-4 pt-3.5 pb-2.5">
        <span
          className="w-7 h-7 rounded-lg flex items-center justify-center text-[13px] shrink-0"
          style={{ background: 'color-mix(in srgb, var(--accent, #2a7de1) 10%, transparent)', color: accent }}
        >
          📋
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold leading-snug" style={{ color: 'var(--text, #1d2129)' }}>
            {entry.title}
          </div>
          {entry.goal && (
            <div className="text-[11.5px] mt-1 truncate" style={{ color: 'var(--text-muted, #6b7280)' }}>
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

      {/* 执行计划（waiting/running 展开；resolved 默认收起可展开——思维列表式） */}
      {effectiveOpen && (
        <div className="px-3.5 pb-1.5">
          {/* 原型：步骤直接平铺（无独立背景块）——hover 浅灰 */}
          <div className="flex flex-col gap-0.5 px-2.5 py-1.5">
            {entry.steps.map((s, i) => {
              const st = running || done ? entry.stepStatus?.[s.name] ?? 'pending' : 'pending';
              const active = st === 'running';
              return (
                <div
                  key={i}
                  className="flex items-center gap-2 py-[4px] px-1.5 text-[12.5px] rounded-[10px] hover:bg-[#f0f0f0] transition-colors"
                  style={{
                    background: active ? 'rgba(120,160,205,.08)' : 'none',
                    color: 'var(--text, #1d2129)',
                  }}
                >
                  <span
                    className="w-[18px] h-[18px] rounded-full flex items-center justify-center text-[9.5px] shrink-0 font-medium"
                    style={{
                      background: st === 'done' ? 'rgba(47,178,123,.12)' : active ? 'rgba(120,160,205,.18)' : 'var(--surface-3, #ececec)',
                      color: st === 'done' ? '#7fc8a3' : active ? '#6a8fb8' : 'var(--text-faint, #bdbdbd)',
                      fontWeight: active ? 600 : 500,
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
                  className="inline-flex items-center gap-1 px-2.5 py-[3px] rounded-full text-[11px]"
                  style={{ background: '#f5f5f5', color: '#5a5a5a', border: '1px solid rgba(0,0,0,.05)' }}
                >
                  {meta.icon} {meta.label}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* 底部操作条（Kimi 真机评审 P0：按钮层级——主按钮 6-8px 圆角品牌色，
          次级按钮 ghost；底部 padding 增加） */}
      <div
        className="flex items-center justify-end gap-2 px-4 py-2.5"
        style={{ borderTop: '1px solid var(--border-subtle, #eceef1)' }}
      >
        {waiting ? (
          <>
            <button
              onClick={() => onResolve('modify')}
              className="px-3 py-[6px] rounded-[6px] text-[12px] font-medium cursor-pointer hover:opacity-80"
              style={{ background: 'none', color: 'var(--text-muted, #6b7280)', border: '1px solid var(--border, #e0e3e8)' }}
            >
              修改计划
            </button>
            <button
              onClick={() => onResolve('cancel')}
              className="px-3 py-[6px] rounded-full text-[12px] font-medium cursor-pointer hover:bg-[#f2f2f2] transition-colors"
              style={{ background: 'none', color: '#8a8a8a' }}
            >
              跳过
            </button>
            <button
              onClick={() => onResolve('confirm')}
              className="px-5 py-[6px] rounded-full text-[12px] font-semibold cursor-pointer hover:bg-[#000] transition-colors shadow-sm"
              style={{ background: '#1f1f1f', color: '#fff', border: 'none' }}
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
            {effectiveOpen ? '收起详情 ▴' : '展开详情 ▾'}
          </button>
        )}
      </div>
    </div>
  );
}
