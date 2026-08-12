import { useEffect, useRef, useState } from 'react';
import type { ConfirmChoice, ConfirmStep, UserInputCardRequest } from '../../../../shared/ipc';
import type { UserInputCardEntry } from '../../../contexts/UserInputContext';

/**
 * ConfirmCard — AI-initiated human-in-the-loop card (issue #646).
 *
 * Rendered inline in the message flow (NOT a modal). The model calls
 * ask_user_confirm_card → the card appears in WAITING state and the turn
 * pauses; the user picks a choice → the choice is returned to the backend as
 * a tool result → the card stays in the flow as a resolved record.
 *
 * States follow the v5 prototype semantics:
 *   pending   → blue accent, choices + remember + countdown (strongest)
 *   confirmed → light green, "已选择「xxx」· time" (medium)
 *   cancelled → grey, neutral end state, NOT an error (weakest)
 */
export function ConfirmCard({
  entry,
  onResolve,
  nowFn = () => new Date().toLocaleTimeString('zh-CN', { hour12: false }),
}: {
  entry: UserInputCardEntry;
  onResolve: (choiceId: string, choiceLabel: string) => void;
  nowFn?: () => string;
}) {
  const req = entry.request;
  const state = entry.state;
  const isWaiting = state === 'pending';

  const choices: ConfirmChoice[] =
    req.choices && req.choices.length > 0 ? req.choices : DEFAULT_CHOICES;
  const steps: ConfirmStep[] = req.steps ?? [];

  // ── countdown (pending only) ────────────────────────────────────
  const timeout = req.timeout_seconds ?? 120;
  const [remaining, setRemaining] = useState(timeout);
  const [countdownDone, setCountdownDone] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (!isWaiting) return;
    setRemaining(timeout);
    setCountdownDone(false);
    timerRef.current = setInterval(() => {
      setRemaining((r) => {
        const next = Math.max(0, r - 1);
        if (next <= 0) {
          if (timerRef.current) clearInterval(timerRef.current);
          setCountdownDone(true);
        }
        return next;
      });
    }, 1000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isWaiting, timeout]);

  // ── remember choice (pending only) ──────────────────────────────
  const [remember, setRemember] = useState(false);

  // ── steps collapse: >4 steps show "展开全部" (issue #646 review) ─
  const MAX_VISIBLE_STEPS = 4;
  const [stepsExpanded, setStepsExpanded] = useState(false);
  const stepsCollapsed = steps.length > MAX_VISIBLE_STEPS && !stepsExpanded;
  const visibleSteps = stepsCollapsed ? steps.slice(0, MAX_VISIBLE_STEPS) : steps;

  const badgeStyle =
    state === 'pending'
      ? { background: 'var(--accent-soft)', color: 'var(--accent-hover)' }
      : state === 'confirmed'
        ? { background: 'var(--success-bg)', color: 'var(--success-text)' }
        : { background: 'var(--surface-3)', color: 'var(--text-muted)' };
  const borderClass = isWaiting
    ? { borderColor: 'var(--accent)', boxShadow: '0 0 0 3px rgba(51,156,255,.16)' }
    : state === 'confirmed'
      ? { borderColor: 'var(--border-subtle)', boxShadow: 'none' }
      : { borderColor: 'var(--border-subtle)', boxShadow: 'none', background: 'var(--surface-muted)', opacity: 0.9 };

  return (
    <div
      className="rounded-xl p-4 max-w-[600px] relative overflow-hidden"
      style={{ border: '1px solid var(--border-subtle)', ...borderClass, transition: 'all .35s cubic-bezier(.22,.8,.32,1)' }}
    >
      {/* top accent line */}
      <div
        className="absolute top-0 left-0 right-0"
        style={{
          height: 3,
          background:
            state === 'pending'
              ? 'linear-gradient(90deg, var(--accent), transparent)'
              : state === 'confirmed'
                ? 'linear-gradient(90deg, var(--success), transparent)'
                : 'none',
        }}
      />
      {/* head */}
      <div className="flex items-center gap-2.5 mb-2.5">
        <span
          className="w-[26px] h-[26px] rounded-lg flex items-center justify-center text-sm shrink-0"
          style={{
            background: isWaiting
              ? 'var(--accent-soft)'
              : state === 'confirmed'
                ? 'var(--success-bg)'
                : 'var(--surface-3)',
            color: isWaiting
              ? 'var(--accent-hover)'
              : state === 'confirmed'
                ? 'var(--success-text)'
                : 'var(--text-faint)',
          }}
        >
          {req.title?.includes('上传') ? '📤' : req.title?.includes('补充') ? '❓' : '📋'}
        </span>
        <span className="text-[14.5px] font-semibold tracking-[.01em]">{req.title}</span>
        <span className="ml-auto text-[11px] font-semibold rounded-full px-2.5 py-0.5 whitespace-nowrap" style={badgeStyle}>
          {state === 'pending' ? '等待你的选择' : state === 'confirmed' ? '✓ 已确认' : '已取消'}
        </span>
      </div>

      {/* message */}
      <div className="text-[13px] mb-3" style={{ color: 'var(--text-muted)' }}>
        {req.message}
      </div>

      {/* steps */}
      {steps.length > 0 && (
        <div className="flex flex-col gap-1.5 mb-3">
          {visibleSteps.map((s, i) => (
            <div key={s.id} className="flex gap-2.5 items-baseline text-[13px] py-0.5">
              <span
                className="w-[18px] h-[18px] rounded-full flex items-center justify-center text-[10.5px] font-semibold shrink-0"
                style={{ background: 'var(--surface-3)', color: 'var(--text-faint)' }}
              >
                {i + 1}
              </span>
              <span className="flex-1">{s.title}</span>
            </div>
          ))}
          {stepsCollapsed && (
            <button
              onClick={() => setStepsExpanded(true)}
              className="text-[11.5px] cursor-pointer hover:underline self-center mt-1"
              style={{ color: 'var(--accent-hover)', background: 'none', border: 'none', fontFamily: 'inherit' }}
            >
              展开全部 {steps.length} 个步骤
            </button>
          )}
        </div>
      )}

      {/* pending-only: choices */}
      {isWaiting && (
        <div className="flex gap-2 flex-wrap">
          {choices.map((c) => (
            <button
              key={c.id}
              onClick={() => onResolve(c.id, c.label)}
              className="text-[13px] font-medium rounded-lg px-4 py-1.5 cursor-pointer transition-all"
              style={
                c.id === 'cancel'
                  ? { border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--danger)' }
                  : { border: '1px solid var(--accent)', background: 'var(--accent)', color: '#fff', boxShadow: '0 2px 8px rgba(51,156,255,.35)' }
              }
              onMouseEnter={(e) => {
                if (c.id === 'cancel') e.currentTarget.style.background = 'var(--danger-bg)';
                else e.currentTarget.style.background = 'var(--accent-hover)';
              }}
              onMouseLeave={(e) => {
                if (c.id === 'cancel') e.currentTarget.style.background = 'var(--surface)';
                else e.currentTarget.style.background = 'var(--accent)';
              }}
            >
              {c.label}
            </button>
          ))}
        </div>
      )}

      {/* pending-only: remember + countdown */}
      {isWaiting && (
        <div className="flex items-center gap-3.5 mt-3 text-xs flex-wrap" style={{ color: 'var(--text-faint)' }}>
          {req.allow_remember_choice && (
            <label className="flex items-center gap-1.5 cursor-pointer select-none" style={{ color: 'var(--text-muted)' }}>
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
              本次会话不再询问
            </label>
          )}
          <div className="flex items-center gap-2 flex-1 min-w-[140px]">
            <div className="flex-1 h-1 rounded-sm overflow-hidden" style={{ background: 'var(--surface-3)' }}>
              <div
                className="h-full rounded-sm"
                style={{
                  width: `${(remaining / timeout) * 100}%`,
                  background: remaining <= 5 ? 'var(--danger)' : 'var(--accent)',
                  transition: 'width 1s linear',
                }}
              />
            </div>
            <span className="text-[11px] tabular-nums w-[30px] text-right" style={{ color: remaining <= 5 ? 'var(--danger)' : 'var(--text-muted)' }}>
              {remaining}s
            </span>
          </div>
        </div>
      )}

      {/* resolved: what the user actually picked (chip, v5-style) */}
      {!isWaiting && (
        <div
          className="flex items-center gap-2.5 mt-3 pt-3"
          style={{ borderTop: '1px dashed var(--border-subtle)', animation: 'msgIn .3s cubic-bezier(.22,.8,.32,1)' }}
        >
          <span
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1 text-[12px] font-semibold"
            style={{
              background: state === 'confirmed' ? 'var(--success-bg)' : 'var(--surface-3)',
              color: state === 'confirmed' ? 'var(--success-text)' : 'var(--text-muted)',
            }}
          >
            <span style={{ fontSize: 11 }}>{state === 'confirmed' ? '✓' : '○'}</span>
            已选择「{entry.choiceLabel ?? (state === 'cancelled' ? '取消' : '确认')}」
          </span>
          <span className="text-[11px] tabular-nums" style={{ color: 'var(--text-faint)' }}>
            {entry.resolvedAt ? new Date(entry.resolvedAt).toLocaleTimeString('zh-CN', { hour12: false }) : nowFn()}
          </span>
        </div>
      )}
    </div>
  );
}

const DEFAULT_CHOICES: ConfirmChoice[] = [
  { id: 'confirm', label: '确认执行' },
  { id: 'adjust', label: '调整方案' },
  { id: 'cancel', label: '取消' },
];
