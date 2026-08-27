import type { ReactNode } from 'react';
import { HermesConfirmBar, type HermesConfirmChoice } from './HermesConfirmBar';
import { HermesToolRow, TOOL_PRE_CLASS, type ToolRowStatus } from './HermesToolRow';

export interface PlanCardEntry {
  title: string;
  goal?: string;
  steps: { name: string; tools?: string[] }[];
  permissions: string[];
  phase: 'wait_confirm' | 'running' | 'completed' | 'cancelled' | 'wait_dangerous' | 'modified';
  stepStatus?: Record<string, 'pending' | 'running' | 'done' | 'failed'>;
}

const PERM_LABELS: Record<string, { icon: string; label: string }> = {
  network: { icon: '🌐', label: '网络访问' },
  network_read: { icon: '🌐', label: '网络访问' },
  file_write: { icon: '📄', label: '创建/修改文件' },
  workspace_write: { icon: '📄', label: '创建/修改文件' },
  shell: { icon: '⚡', label: '执行命令' },
  external_upload: { icon: '☁', label: '外部上传' },
  external_send: { icon: '💬', label: '对外发送' },
};

/**
 * PlanCard — 任务计划（Hermes 工具行结构，2026-08-26 用户"抄 Hermes"）。
 *
 * Hermes fallback.tsx ToolEntry：ScaffoldRow（14px 状态字形 + 小字标题 +
 * meta）+ 行下审批条 + 展开区。成功静默（success is silent）。
 */
export function PlanCard({
  entry,
  onResolve,
  initialExpanded,
}: {
  entry: PlanCardEntry;
  onResolve: (choiceId: string, rememberMode?: 'session' | 'always' | null) => void;
  initialExpanded?: boolean;
}) {
  const waiting = entry.phase === 'wait_confirm';
  const running = entry.phase === 'running';
  const done = entry.phase === 'completed';
  const cancelled = entry.phase === 'cancelled';
  const modified = entry.phase === 'modified';

  // Hermes 状态字形：waiting/running → spinner；成功 → 静默；取消/修改 → 静默
  const status: ToolRowStatus = waiting || running ? 'pending' : 'success';

  // meta：状态文字（Hermes meta 位——右侧灰字）
  const statusText = done ? '已完成' : cancelled ? '已取消' : modified ? '已修改' : running ? '执行中' : waiting ? '等待确认' : '';
  const metaColor = done ? '#2ea45f' : '#a0a6b0';

  const handleResolve = (choice: HermesConfirmChoice, rememberMode?: 'session' | 'always' | null) => {
    if (choice === 'deny') onResolve('cancel');
    else if (choice === 'session') onResolve('confirm', 'session');
    else if (choice === 'always') onResolve('confirm', 'always');
    else onResolve(choice, rememberMode ?? null);
  };

  // 展开内容：标题 + 步骤 + 权限（Hermes 展开区风格）
  const content: ReactNode = (
    <div className="w-full min-w-0 max-w-full">
      <div className="text-[12.5px] font-medium leading-snug break-words" style={{ color: '#1a1a1a' }}>
        {entry.title}
      </div>
      {entry.goal && (
        <div className="text-[11.5px] mt-0.5 break-words" style={{ color: '#6b7280' }}>
          {entry.goal}
        </div>
      )}
      <div className="mt-1.5 flex flex-col">
        {entry.steps.map((s, i) => {
          const st = running || done ? entry.stepStatus?.[s.name] ?? 'pending' : 'pending';
          const active = st === 'running';
          return (
            <div key={i} className="flex items-baseline gap-2 py-[2px] text-[12.5px]" style={{ color: '#333' }}>
              <span
                className="text-[11.5px] w-[16px] text-right shrink-0"
                style={{ color: st === 'done' ? '#2ea45f' : active ? '#1a1a1a' : '#b0b6bf' }}
              >
                {st === 'done' ? '✓' : active ? '⟳' : String(i + 1)}
              </span>
              <span className="break-words min-w-0">{s.name}</span>
              {s.tools && s.tools.length > 0 && (
                <span className="text-[10.5px] shrink-0 ml-auto" style={{ color: '#a0a6b0' }}>
                  {s.tools.join(' / ')}
                </span>
              )}
            </div>
          );
        })}
      </div>
      {waiting && entry.permissions.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {entry.permissions.map((p) => {
            const meta = PERM_LABELS[p] ?? { icon: '🔐', label: p };
            return (
              <span
                key={p}
                className="inline-flex items-center gap-1 px-1.5 py-[1px] rounded-full text-[10.5px]"
                style={{ background: '#f5f5f5', color: '#555', border: '1px solid #ebebeb' }}
              >
                {meta.icon} {meta.label}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );

  return (
    <HermesToolRow
      testid="plan-card"
      title="任务计划"
      status={status}
      meta={statusText ? <span style={{ color: metaColor }}>{statusText}</span> : undefined}
      defaultOpen={waiting || running || (initialExpanded ?? false)}
      approval={
        waiting ? (
          <div className="pl-5 pt-1">
            <HermesConfirmBar
              runLabel="开始执行"
              onResolve={handleResolve}
              allowModify
              description={`允许执行该计划？${entry.goal ? `\n\n${entry.goal}` : ''}`}
            />
          </div>
        ) : undefined
      }
    >
      {content}
    </HermesToolRow>
  );
}

// TOOL_PRE_CLASS re-export（保持引用完整性）
export { TOOL_PRE_CLASS };
