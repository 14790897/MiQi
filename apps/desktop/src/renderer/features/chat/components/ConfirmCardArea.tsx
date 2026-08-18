import { useState } from 'react';
import { useUserInput } from '../../../contexts/UserInputContext';
import { ActionCard } from './ActionCard';
import { ConfirmCard } from './ConfirmCard';
import { PlanCard } from './PlanCard';
import { Timeline } from './Timeline';

/** #646-v2: 判定是否为任务计划卡（ask_user_plan_confirm 载荷带 goal/permissions） */
function isPlanCard(entry: { request: { goal?: string; permissions?: string[] } }): boolean {
  return typeof entry.request.goal === 'string' || (entry.request.permissions?.length ?? 0) > 0;
}

/** #646-v2: 判定是否为危险动作卡（request_action_confirmation 载荷带 action/target） */
function isActionCard(entry: { request: { action?: string; target?: string } }): boolean {
  return typeof entry.request.action === 'string' && typeof entry.request.target === 'string';
}

/**
 * ConfirmCardArea — renders ask_user_confirm_card cards at the tail of the
 * message flow, right above the composer (issue #646).
 *
 * - The pending card (blue, strongest) blocks the turn until the user picks.
 * - Resolved cards stay in the flow, de-emphasized, as a traceable record of
 *   what the user confirmed/cancelled (v5 semantics: cancelled is a neutral
 *   end state, NOT an error).
 * - Resolved history collapses beyond 3 entries ("已处理 N 张确认卡") to avoid
 *   stacking noise during adjust loops.
 */
export function ConfirmCardArea() {
  const { pending, resolved, timelines, resolve, timeoutCard } = useUserInput();
  const [historyExpanded, setHistoryExpanded] = useState(false);

  const pendingIds = Object.keys(pending);
  const resolvedIds = Object.keys(resolved);

  const MAX_VISIBLE_RESOLVED = 3;
  const collapsed = resolvedIds.length > MAX_VISIBLE_RESOLVED && !historyExpanded;
  const visibleResolved = collapsed ? resolvedIds.slice(-MAX_VISIBLE_RESOLVED) : resolvedIds;

  if (pendingIds.length === 0 && resolvedIds.length === 0) return null;

  return (
    <div className="w-full flex flex-col gap-2" data-testid="confirm-card-area">
      {/* #646-v2 Auto Timeline（非阻塞展示）——keyed by turnId */}
      {Object.entries(timelines).map(([turnId, tl]) => (
        <div key={turnId} className="flex gap-2.5">
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
          <div className="min-w-0 flex-1">
            <Timeline entry={tl} />
          </div>
        </div>
      ))}
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
              {isActionCard(entry) ? (
                <ActionCard
                  entry={{
                    action: entry.request.action ?? 'external',
                    target: entry.request.target ?? '',
                    fileName: entry.request.file_name,
                    sizeBytes: entry.request.size_bytes,
                    sha256: entry.request.sha256,
                    description: entry.request.message || entry.request.description,
                  }}
                  onResolve={(choiceId) => resolve(id, choiceId, choiceId === 'confirm' ? '确认' : '取消', false)}
                />
              ) : isPlanCard(entry) ? (
                <PlanCard
                  entry={{
                    title: entry.request.title,
                    goal: entry.request.goal ?? '',
                    // 兼容两种 steps 结构：ask_user_plan_confirm 用 name、
                    // ask_user_confirm_card 旧载荷用 title（实测：name 映射丢失渲染空）
                    steps: (entry.request.steps ?? []).map((s) => ({
                      name: (s as { name?: string }).name ?? (s as { title?: string }).title ?? '',
                      tools: [],
                    })),
                    permissions: entry.request.permissions ?? [],
                    phase: 'wait_confirm',
                  }}
                  onResolve={(choiceId) => resolve(id, choiceId, choiceId === 'confirm' ? '开始执行' : '取消', false)}
                />
              ) : (
                <ConfirmCard
                  entry={entry}
                  onResolve={(choiceId, choiceLabel, remember) => resolve(id, choiceId, choiceLabel, remember)}
                  onTimeout={() => timeoutCard(id)}
                />
              )}
            </div>
          </div>
        );
      })}

      {/* Resolved history — compact, de-emphasized, collapses beyond 3 */}
      {resolvedIds.length > 0 && (
        <div className="flex flex-col gap-1.5 mt-1" data-testid="confirm-card-resolved">
          {collapsed && (
            <button
              onClick={() => setHistoryExpanded(true)}
              className="text-[11.5px] cursor-pointer hover:underline self-start px-1"
              style={{ color: 'var(--text-faint)', background: 'none', border: 'none', fontFamily: 'inherit' }}
            >
              已处理 {resolvedIds.length} 张确认卡（点击展开）
            </button>
          )}
          {visibleResolved.map((id) => {
            const entry = resolved[id];
            const cancelled = entry.state === 'cancelled';
            const timedOut = entry.timedOut;
            // Kimi 评审（红框反馈）：通栏横条 → 轻量胶囊（融入卡片区，
            // 不占整行、不打断对话流）——确认绿 / 取消灰
            return (
              <div
                key={id}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11.5px] w-fit max-w-[560px]"
                style={{
                  border: `1px solid ${
                    cancelled || timedOut ? 'var(--border-subtle)' : 'rgba(47,178,123,.22)'
                  }`,
                  background: cancelled || timedOut ? 'var(--surface-muted)' : 'color-mix(in srgb, #2fb27b 7%, transparent)',
                }}
              >
                <span className="shrink-0 text-[11px]">
                  {entry.backendReleased ? '⏹' : entry.timedOut ? '⏱' : cancelled ? '○' : '✓'}
                </span>
                <span className="font-medium truncate" style={{ color: 'var(--text-muted)' }}>
                  {entry.request.title}
                </span>
                <span
                  className="font-semibold shrink-0"
                  style={{ color: cancelled ? 'var(--text-muted)' : 'var(--success-text)' }}
                >
                  {entry.backendReleased
                    ? '已关闭（后端已释放）'
                    : entry.timedOut
                      ? '已超时'
                      : cancelled
                        ? '已取消'
                        : `已选择「${entry.choiceLabel ?? '确认'}」`}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
