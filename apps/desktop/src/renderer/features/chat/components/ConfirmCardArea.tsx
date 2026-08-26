import { useState } from 'react';
import { useUserInput } from '../../../contexts/UserInputContext';
import { Timeline } from './Timeline';
import { PlanCard } from './PlanCard';
import { ActionCard } from './ActionCard';
import { ConfirmCard } from './ConfirmCard';

const MAX_VISIBLE_RESOLVED = 3;

/** #646-v2: 判定是否为任务计划卡——显式判别器优先（toolName），
 *  goal/permissions 启发式仅作 legacy 兜底（CodeRabbit）。 */
function isPlanCard(entry: { request: { goal?: string; permissions?: string[]; toolName?: string } }): boolean {
  if (entry.request.toolName === 'ask_user_plan_confirm') return true;
  if (entry.request.toolName === 'ask_user_confirm_card') return false;
  return typeof entry.request.goal === 'string' || (entry.request.permissions?.length ?? 0) > 0;
}

/** #646-v2: 判定是否为危险动作卡（request_action_confirmation 载荷带 action/target） */
function isActionCard(entry: { request: { action?: string; target?: string } }): boolean {
  return typeof entry.request.action === 'string' && typeof entry.request.target === 'string';
}

/**
 * ConfirmCardArea — 确认卡 + Timeline 渲染区（Hermes 式：一个对话流——
 * 确认卡内联在消息流（工具行下）；确认后无残留（无"已选择"堆积）。
 * 用户明确：不要两个对话框（消息流 + 底部卡）——只有一个对话流。
 *
 * Resolved 历史：默认折叠为"已处理 N 张确认卡（点击查看）"入口（可追溯不丢），
 * 展开明细限高 140px 滚动（2026-08-24 用户：确认历史不得越叠越高）。
 * 胶囊状态文字中性化（已确认/已取消/已超时）——不留"已选择「xxx」"残留行
 * （2026-08-25 用户批评 68fdb0e0）。
 */
export function ConfirmCardArea() {
  const { pending, resolved, timelines, resolve, timeoutCard } = useUserInput();
  const [historyExpanded, setHistoryExpanded] = useState(false);

  const pendingIds = Object.keys(pending);
  const resolvedIds = Object.keys(resolved);

  const visibleResolved = historyExpanded
    ? resolvedIds
    : resolvedIds.slice(-MAX_VISIBLE_RESOLVED);

  if (pendingIds.length === 0 && resolvedIds.length === 0 && Object.keys(timelines).length === 0) return null;

  return (
    <div className="w-full flex flex-col gap-2" data-testid="confirm-card-area">
      {/* #646-v2 Auto Timeline（非阻塞展示）——keyed by turnId */}
      {Object.entries(timelines).map(([turnId, tl]) => (
        <div key={turnId} className="flex flex-col items-start w-full">
          <div className="min-w-0 w-full">
            <Timeline entry={tl as never} />
          </div>
        </div>
      ))}
      {/* Active card(s) — 确认卡（消息流内联——Hermes 式） */}
      {pendingIds.map((id) => {
        const entry = pending[id];
        return (
          <div key={id} className="flex flex-col items-start w-full animate-[msgIn_.35s_cubic-bezier(.22,.8,.32,1)]">
            <div className="min-w-0 w-full">
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
                  onResolve={(choiceId, rememberMode) =>
                    resolve(
                      id,
                      choiceId,
                      choiceId === 'confirm' ? '确认' : choiceId === 'modify' ? '修改计划' : '取消',
                      rememberMode !== null,
                      rememberMode ?? 'session',
                    )
                  }
                />
              ) : isPlanCard(entry) ? (
                <PlanCard
                  entry={{
                    title: entry.request.title,
                    goal: entry.request.goal ?? '',
                    steps: (entry.request.steps ?? []).map((s) => ({
                      name: (s as { name?: string }).name ?? (s as { title?: string }).title ?? '',
                      tools: [],
                    })),
                    permissions: entry.request.permissions ?? [],
                    phase: 'wait_confirm',
                  }}
                  onResolve={(choiceId, rememberMode) =>
                    resolve(
                      id,
                      choiceId,
                      choiceId === 'confirm' ? '确认' : choiceId === 'modify' ? '修改计划' : '取消',
                      rememberMode !== null,
                      rememberMode ?? 'session',
                    )
                  }
                />
              ) : (
                <ConfirmCard
                  entry={entry}
                  onResolve={(choiceId, choiceLabel, remember) =>
                    resolve(id, choiceId, choiceLabel, remember, 'session')
                  }
                  onTimeout={timeoutCard}
                />
              )}
            </div>
          </div>
        );
      })}
      {/* Resolved history — WorkBuddy/Hermes 风格：确认即关闭，默认不占对话流；
          仅显式展开历史时显示（可追溯不丢）；展开明细限高滚动 */}
      {resolvedIds.length > 0 && (
        <div
          className="flex flex-col gap-1.5 mt-1"
          data-testid="confirm-card-resolved"
          // 用户（2026-08-24）：确认历史不得越叠越高——展开明细限高滚动
          style={historyExpanded ? { maxHeight: 140, overflowY: 'auto' } : undefined}
        >
          {!historyExpanded && (
            <button
              onClick={() => setHistoryExpanded(true)}
              className="text-[11px] cursor-pointer hover:underline self-start px-1"
              style={{ color: 'var(--text-faint)', background: 'none', border: 'none', fontFamily: 'inherit' }}
            >
              已处理 {resolvedIds.length} 张确认卡（点击查看）
            </button>
          )}
          {historyExpanded && (
            <button
              onClick={() => setHistoryExpanded(false)}
              className="text-[11px] cursor-pointer hover:underline self-start px-1"
              style={{ color: 'var(--text-faint)', background: 'none', border: 'none', fontFamily: 'inherit' }}
            >
              收起历史 ▴
            </button>
          )}
          {visibleResolved.map((id) => {
            const entry = resolved[id];
            const cancelled = entry.state === 'cancelled';
            const timedOut = entry.timedOut;
            // 轻量胶囊（融入卡片区，不占整行、不打断对话流）——确认绿 / 取消灰
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
                        : '已确认'}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
