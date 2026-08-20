/**
 * Timeline — Auto 模式非阻塞任务进度展示（#646-v2 GPT P0-3）。
 *
 * 与 PlanCard 的区别：**无按钮、不等待用户**——只展示任务计划与执行进度。
 * Auto 模式复杂任务触发（should_show_timeline），简单任务不展示（工具行覆盖）。
 *
 * 布局与 PlanCard 同构（payload 相同）——复用渲染心智：标题/目标/步骤/权限。
 */
import { useState } from 'react';
import type { UserInputCardRequest } from '../../../../shared/ipc';

export interface TimelineEntry {
  title: string;
  goal: string;
  steps: { name: string; tools?: string[] }[];
  permissions: string[];
  phase?: string;
  stepStatus?: Record<string, string>;
  /** v3.3：TodoState 投影数据（display=todo_state）——有则优先渲染 */
  todoItems?: { id: string; title: string; status: string }[];
  todoRevision?: number;
}

const PERM_META: Record<string, { icon: string; label: string }> = {
  network_read: { icon: '🌐', label: '网络访问' },
  workspace_write: { icon: '📄', label: '创建/修改文件' },
  exec: { icon: '⚙️', label: '执行命令' },
  external_upload: { icon: '⬆️', label: '外部上传' },
};

export function Timeline({
  entry,
}: {
  entry: TimelineEntry;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const running = entry.phase !== 'completed' && entry.phase !== 'cancelled';

  return (
    <div
      className="rounded-[20px] my-2 w-full max-w-full overflow-hidden"
      data-testid="timeline"
      style={{
        background: 'var(--surface, #ffffff)',
        border: '1px solid rgba(0,0,0,.04)',
        boxShadow: '0 2px 12px rgba(0,0,0,.04)',
      }}
    >
      {/* 标题行 */}
      <div className="flex items-center gap-2.5 px-4 pt-3.5 pb-3">
        <span
          className="w-7 h-7 rounded-[8px] flex items-center justify-center text-[13px] shrink-0"
          style={{ background: 'var(--surface-3, #f1f2f4)', color: 'var(--text-muted, #6b7280)' }}
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
        {/* Kimi 评审 P0：执行中徽章——呼吸灯点 + 靠近标题 */}
        <span
          className="inline-flex items-center gap-1.5 px-2 py-[3px] rounded-full text-[10px] font-medium shrink-0"
          style={{ background: 'var(--surface-3, #f1f2f4)', color: 'var(--text-muted, #6b7280)' }}
        >
          <span
            style={{
              width: 6, height: 6, borderRadius: '50%', background: 'var(--accent, #2a7de1)',
              animation: 'turn-pulse 1.2s ease-in-out infinite',
            }}
          />
          {running ? '执行中' : '已完成'}
        </span>
      </div>

      {/* 步骤列表（Kimi P0：左侧时间轴竖线 + 当前步骤蓝色强调/完成灰对勾）
          v3.3：有 todoItems → Todo 投影（模型 todo_write / harness observed）；无 → 旧 steps */}
      {!collapsed && (entry.todoItems ? (
        <div className="px-3.5 pb-1.5">
          <div className="flex flex-col gap-0.5 px-2.5 py-1.5">
            {entry.todoItems.map((t, i) => {
              const isDone = t.status === 'completed';
              const isActive = t.status === 'in_progress';
              const isBlocked = t.status === 'blocked';
              const isCancelled = t.status === 'cancelled';
              const mark = isDone ? '✓' : isActive ? '⟳' : isBlocked ? '⏸' : isCancelled ? '✕' : String(i + 1).padStart(2, '0');
              const bg = isDone ? 'rgba(47,178,123,.12)' : isActive ? 'rgba(120,160,205,.18)' : isBlocked ? 'rgba(180,150,90,.15)' : 'var(--surface-3, #ececec)';
              const color = isDone ? '#7fc8a3' : isActive ? '#6a8fb8' : isBlocked ? '#b8a06a' : isCancelled ? 'var(--text-faint, #bdbdbd)' : 'var(--text-faint, #bdbdbd)';
              return (
                <div key={t.id || i} className="flex items-center gap-2.5 py-[4px] text-[12.5px] relative">
                  {i < entry.todoItems!.length - 1 && (
                    <span
                      className="absolute left-[8.5px] top-[20px] bottom-[-6px] w-[1.5px]"
                      style={{ background: isDone ? 'rgba(52,199,123,.4)' : 'var(--border-subtle, #eceef1)' }}
                    />
                  )}
                  <span
                    className="w-[18px] h-[18px] rounded-full flex items-center justify-center text-[9.5px] shrink-0 font-medium z-[1]"
                    style={{ background: bg, color, boxShadow: isActive ? '0 0 0 3px color-mix(in srgb, var(--accent, #2a7de1) 18%, transparent)' : 'none' }}
                  >
                    {mark}
                  </span>
                  <span
                    style={{
                      color: isActive ? 'var(--text, #1d2129)' : isDone || isCancelled ? 'var(--text-faint, #9aa0a8)' : 'var(--text, #1d2129)',
                      fontWeight: isActive ? 600 : 400,
                    }}
                  >
                    {t.title}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="px-3.5 pb-1.5">
          <div className="flex flex-col gap-0.5 px-2.5 py-1.5">
            {entry.steps.map((s, i) => {
              const st = entry.stepStatus?.[s.name];
              const isDone = st === 'done';
              const isActive = st === 'running';
              return (
                <div key={i} className="flex items-center gap-2.5 py-[4px] text-[12.5px] relative">
                  {/* 时间轴竖线（连接序号） */}
                  {i < entry.steps.length - 1 && (
                    <span
                      className="absolute left-[8.5px] top-[20px] bottom-[-6px] w-[1.5px]"
                      style={{ background: isDone ? 'rgba(52,199,123,.4)' : 'var(--border-subtle, #eceef1)' }}
                    />
                  )}
                  <span
                    className="w-[18px] h-[18px] rounded-full flex items-center justify-center text-[9.5px] shrink-0 font-medium z-[1]"
                    style={{
                      background: isDone ? 'rgba(52,199,123,.15)' : isActive ? 'var(--accent, #2a7de1)' : 'var(--surface-3, #e8eaed)',
                      color: isDone ? '#2fb27b' : isActive ? '#fff' : 'var(--text-faint, #a0a6b0)',
                      boxShadow: isActive ? '0 0 0 3px color-mix(in srgb, var(--accent, #2a7de1) 18%, transparent)' : 'none',
                    }}
                  >
                    {isDone ? '✓' : isActive ? '⟳' : String(i + 1).padStart(2, '0')}
                  </span>
                  <span
                    style={{
                      color: isActive ? 'var(--text, #1d2129)' : isDone ? 'var(--text-faint, #9aa0a8)' : 'var(--text, #1d2129)',
                      fontWeight: isActive ? 600 : 400,
                    }}
                  >
                    {s.name}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* 底部：权限 + 折叠 */}
      <div
        className="flex items-center justify-between px-4 py-2"
        style={{ borderTop: '1px solid var(--border-subtle, #eceef1)' }}
      >
        <div className="flex items-center gap-1.5">
          {entry.permissions.map((p) => {
            const meta = PERM_META[p];
            if (!meta) return null;
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
        <button
          onClick={() => setCollapsed((v) => !v)}
          className="text-[11px] cursor-pointer hover:opacity-80"
          style={{ background: 'none', border: 'none', color: 'var(--text-faint, #9aa0a8)' }}
        >
          {collapsed ? '展开详情 ▾' : '收起详情 ▴'}
        </button>
      </div>
    </div>
  );
}

/** 载荷判定（ConfirmCardArea 复用）——与 PlanCard 同构但 display=timeline。 */
export function isTimelineRequest(data: UserInputCardRequest | undefined): data is UserInputCardRequest {
  return Boolean(data && (data as any).display === 'timeline');
}
