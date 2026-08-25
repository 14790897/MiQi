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
 */
export function ConfirmCardArea() {
  const { pending, timelines, resolve, timeoutCard } = useUserInput();

  const pendingIds = Object.keys(pending);

  if (pendingIds.length === 0 && Object.keys(timelines).length === 0) return null;

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
                    resolve(id, choiceId, choiceId === 'confirm' ? '确认' : '取消', rememberMode !== null, rememberMode ?? 'session')
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
                    resolve(id, choiceId, choiceId === 'confirm' ? '确认' : '取消', rememberMode !== null, rememberMode ?? 'session')
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
    </div>
  );
}

