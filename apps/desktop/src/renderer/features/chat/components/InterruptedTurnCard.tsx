import { useState } from 'react';
import { ThinkBlock } from './ThinkBlock';

/**
 * #740: 中断的 turn —— 极简恢复形态。
 *
 * 参考 Hermes / LibreChat / ChatGPT：不画卡片框、不写"任务被中断"标题、
 * 不展示 token 统计——被打断的半截内容**直接显示**在消息流里（像正常
 * 回答一样），操作按钮（继续执行 / 重新开始）紧跟内容正下方。
 *
 * 布局顺序：思考块（有则显示）→ 半截回答 → 按钮行。
 */
export function InterruptedTurnCard({
  meta,
  reasoning,
  content,
  onResume,
  onRestart,
}: {
  meta: {
    turnId: string;
    status: string;
    tokenEstimate?: number;
  };
  reasoning?: string;
  content: string;
  onResume?: () => void;
  onRestart?: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [confirmingRestart, setConfirmingRestart] = useState(false);

  const handleResume = () => {
    if (busy) return;
    setBusy(true);
    onResume?.();
    setTimeout(() => setBusy(false), 1500);
  };

  const handleRestart = () => {
    if (confirmingRestart) {
      onRestart?.();
      setConfirmingRestart(false);
    } else {
      setConfirmingRestart(true);
      setTimeout(() => setConfirmingRestart(false), 2500);
    }
  };

  const hasHalf = !!(content || reasoning);

  return (
    <div className="my-1 min-w-0">
      {/* 思考块（有则显示，可展开）——像正常消息流里的思考 */}
      {reasoning ? (
        <div className="mb-1">
          <ThinkBlock reasoning={reasoning} defaultOpen={false} elapsedSeconds={1} />
        </div>
      ) : null}

      {/* 半截回答——直接显示，无框（像正常回答被卡住的样子） */}
      {content ? (
        <div
          className="text-[13.5px] leading-relaxed whitespace-pre-wrap break-words"
          style={{ color: 'var(--text)' }}
        >
          {content}
          <span
            className="ml-0.5 inline-block h-[14px] w-[2px] animate-pulse rounded-sm align-[-2px]"
            style={{ background: 'var(--accent)' }}
          />
        </div>
      ) : null}

      {/* 操作行——内容正下方 */}
      <div className="mt-2 flex items-center gap-2">
        {hasHalf ? (
          <button
            className="btn-resume inline-flex items-center gap-1.5 rounded-lg px-3 py-1 text-[12px] font-semibold text-white disabled:opacity-55"
            style={{ background: 'var(--accent)' }}
            onClick={handleResume}
            disabled={busy}
          >
            {busy ? (
              <>
                <span
                  className="inline-block h-[11px] w-[11px] rounded-full border-2 border-white/40 border-t-white"
                  style={{ animation: 'turn-spin .8s linear infinite' }}
                />
                继续中…
              </>
            ) : (
              <>▶ 继续执行</>
            )}
          </button>
        ) : (
          <span className="text-[12px]" style={{ color: 'var(--text-faint)' }}>
            回答已中断
          </span>
        )}
        <button
          className="inline-flex items-center rounded-lg border px-3 py-1 text-[12px] font-semibold"
          style={{
            background: 'var(--surface-muted)',
            color: 'var(--text-muted)',
            borderColor: 'var(--border-subtle)',
          }}
          onClick={handleRestart}
        >
          {confirmingRestart ? '确认重新开始？再点一次' : '重新开始'}
        </button>
      </div>
      <style>{`@keyframes turn-spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
