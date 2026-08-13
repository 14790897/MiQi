import { useUserInput } from '../../../contexts/UserInputContext';
import { ConfirmCard } from './ConfirmCard';

/**
 * ConfirmCardArea — renders ask_user_confirm_card cards at the tail of the
 * message flow, right above the composer (issue #646).
 *
 * - The pending card (blue, strongest) blocks the turn until the user picks.
 * - Resolved cards stay in the flow, de-emphasized, as a traceable record of
 *   what the user confirmed/cancelled (v5 semantics: cancelled is a neutral
 *   end state, NOT an error).
 */
export function ConfirmCardArea() {
  const { pending, resolved, resolve } = useUserInput();

  const pendingIds = Object.keys(pending);
  const resolvedIds = Object.keys(resolved);

  if (pendingIds.length === 0 && resolvedIds.length === 0) return null;

  return (
    <div className="w-full flex flex-col gap-2" data-testid="confirm-card-area">
      {/* Active card(s) — full interactive ConfirmCard */}
      {pendingIds.map((id) => {
        const entry = pending[id];
        return (
          <div key={id} className="flex gap-2.5 animate-[msgIn_.35s_cubic-bezier(.22,.8,.32,1)]">
            <span
              className="w-8 h-8 rounded-[9px] mt-0.5 flex items-center justify-center text-xs shrink-0"
              style={{
                background: 'linear-gradient(135deg,#4db2ff,#2a7de1)',
                color: '#fff',
                boxShadow: '0 1px 2px rgba(18,18,18,.04),0 2px 10px rgba(18,18,18,.06)',
              }}
            >
              AI
            </span>
            <div className="min-w-0">
              <ConfirmCard
                entry={entry}
                onResolve={(choiceId, choiceLabel, remember) => resolve(id, choiceId, choiceLabel, remember)}
              />
            </div>
          </div>
        );
      })}

      {/* Resolved history — compact, de-emphasized */}
      {resolvedIds.length > 0 && (
        <div className="flex flex-col gap-1.5 mt-1" data-testid="confirm-card-resolved">
          {resolvedIds.map((id) => {
            const entry = resolved[id];
            const cancelled = entry.state === 'cancelled';
            return (
              <div
                key={id}
                className="flex items-center gap-2 px-3 py-2 rounded-lg text-[12px] max-w-[560px]"
                style={{
                  border: '1px solid var(--border-subtle)',
                  background: 'var(--surface-muted)',
                  opacity: 0.85,
                }}
              >
                <span className="shrink-0 text-[11px]">
                  {cancelled ? '○' : '✓'}
                </span>
                <span className="font-medium truncate" style={{ color: 'var(--text-muted)' }}>
                  {entry.request.title}
                </span>
                <span
                  className="font-semibold ml-auto shrink-0"
                  style={{ color: cancelled ? 'var(--text-muted)' : 'var(--success-text)' }}
                >
                  {cancelled ? '已取消' : `已选择「${entry.choiceLabel ?? '确认'}」`}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
