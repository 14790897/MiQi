import { useState } from 'react';
import type { UserInputCardRequest } from '../../../../shared/ipc';

export interface TimelineEntry {
  title: string;
  goal: string;
  steps: { name: string; tools?: string[] }[];
  permissions: string[];
  phase?: string;
  stepStatus?: Record<string, string>;
  todoItems?: { id: string; title: string; status: string }[];
  todoRevision?: number;
}

const PERM_META: Record<string, { icon: string; label: string }> = {
  network_read: { icon: '🌐', label: '网络访问' },
  workspace_write: { icon: '📄', label: '创建/修改文件' },
  exec: { icon: '⚙️', label: '执行命令' },
  external_upload: { icon: '⬆️', label: '外部上传' },
};

export function Timeline({ entry }: { entry: TimelineEntry }) {
  const [collapsed, setCollapsed] = useState(false);
  const running = entry.phase !== 'completed' && entry.phase !== 'cancelled';

  const items = entry.todoItems
    ? entry.todoItems.map((t) => ({ key: t.id, title: t.title, status: t.status, tools: [] as string[] }))
    : entry.steps.map((s) => ({ key: s.name, title: s.name, status: entry.stepStatus?.[s.name] ?? 'pending', tools: s.tools ?? [] }));

  const statusOf = (status: string) => {
    const s = status.toLowerCase();
    if (s === 'completed' || s === 'done') return 'done';
    if (s === 'in_progress' || s === 'running') return 'active';
    if (s === 'blocked') return 'blocked';
    if (s === 'cancelled') return 'cancelled';
    return 'pending';
  };

  return (
    <div
      data-testid="timeline"
      className="my-2 max-w-[520px] overflow-hidden rounded-[18px] border border-[#eceef1] bg-white shadow-[0_8px_24px_rgba(30,41,59,0.06)]"
    >
      {/* Header */}
      <div className="flex items-start gap-3 px-5 pt-4 pb-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-[#f4f5f6] text-[14px]">
          📋
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[14px] font-semibold leading-tight text-[#1f1f1f]">
            {entry.title}
          </div>
          {entry.goal && (
            <div className="mt-1 truncate text-[12px] text-[#8e95a0]">
              {entry.goal}
            </div>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1.5 rounded-full bg-[#1f1f1f] px-2.5 py-1 text-[11px] font-medium text-white">
          <span
            className="h-1.5 w-1.5 rounded-full bg-white"
            style={{ opacity: running ? 1 : 0.7 }}
          />
          {running ? '执行中' : '已完成'}
        </div>
      </div>

      {/* Task list */}
      {!collapsed && (
        <div className="px-5 pb-3">
          <div className="flex flex-col">
            {items.map((item, i) => {
              const st = statusOf(item.status);
              const isDone = st === 'done';
              const isActive = st === 'active';
              const isBlocked = st === 'blocked';
              const isCancelled = st === 'cancelled';

              const dotColor = isDone
                ? '#34c77b'
                : isActive
                ? '#2a7de1'
                : isBlocked
                ? '#f59e0b'
                : isCancelled
                ? '#ef4444'
                : '#d0d5dd';

              const textColor = isDone || isCancelled ? '#9aa0a8' : '#1f1f1f';
              const fontWeight = isActive ? 600 : 400;

              return (
                <div key={item.key || i} className="relative flex items-start gap-3 py-2">
                  {i < items.length - 1 && (
                    <span
                      className="absolute top-[22px] left-[5px] h-[calc(100%-12px)] w-[1.5px] bg-[#eceef1]"
                    />
                  )}
                  <span className="relative z-[1] mt-[5px] flex h-[12px] w-[12px] shrink-0 items-center justify-center rounded-full border"
                    style={{
                      borderColor: isDone ? 'transparent' : isActive ? '#2a7de1' : dotColor,
                      backgroundColor: isDone ? '#34c77b' : isActive ? '#2a7de1' : 'transparent',
                      boxShadow: isActive ? '0 0 0 3px rgba(42,125,225,0.12)' : 'none',
                    }}
                  >
                    {isDone && (
                      <svg width="7" height="7" viewBox="0 0 10 8" fill="none">
                        <path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    )}
                    {isActive && (
                      <span className="h-2 w-2 animate-pulse rounded-full bg-white" />
                    )}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div
                      className="text-[13px] leading-snug"
                      style={{ color: textColor, fontWeight }}
                    >
                      {item.title}
                    </div>
                    {item.tools && item.tools.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {item.tools.map((tool) => (
                          <span
                            key={tool}
                            className="text-[10px] text-[#9aa0a8] rounded bg-[#f4f5f6] px-1.5 py-[2px]"
                          >
                            {tool}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  {item.tools && item.tools.length > 0 && (
                    <span className="mt-1 text-[11px] text-[#c4c9d0]">›</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between gap-3 border-t border-[#f2f3f5] px-5 py-3">
        <div className="flex flex-wrap items-center gap-1.5">
          {entry.permissions.map((p) => {
            const meta = PERM_META[p];
            if (!meta) return null;
            return (
              <span
                key={p}
                className="inline-flex items-center gap-1 rounded-md bg-[#f4f5f6] px-2 py-1 text-[11px] text-[#6b7280]"
              >
                {meta.icon}
                <span>{meta.label}</span>
              </span>
            );
          })}
        </div>
        <button
          type="button"
          onClick={() => setCollapsed((v)