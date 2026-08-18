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
      className="rounded-[14px] my-2 max-w-[520px] overflow-hidden"
      data-testid="timeline"
      style={{
        background: 'var(--surface, #ffffff)',
        border: '1px solid var(--border-subtle, #eceef1)',
        boxShadow: '0 8px 24px rgba(30,41,59,.08), 0 2px 6px rgba(30,41,59,.04)',
      }}
    >
      {/* 标题行 */}
      <div className="flex items-center gap-2.5 px-4 pt-3.5 pb-2.5">
        <span
          className="w-7 h-7 rounded-[8px] flex items-center justify-center text-[13px] shrink-0"
          style={{ background: 'color-mix(in srgb, var(--accent, #2a7de1) 10%, transparent)', color: 'var(--accent, #2a7de1)' }}
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
        <span
          className="px-2 py-[2px] rounded-full text-[10px] font-medium shrink-0"
          style={{ background: 'color-mix(in srgb, var(--accent, #2a7de1) 10%, transparent)', color: 'var(--accent, #2a7de1)' }}
        >
          {running ? '执行中' : '已完成'}
        </span>
      </div>

      {/* 步骤列表 */}
      {!collapsed && (
        <div className="px-3.5 pb-1.5">
          <div className="flex flex-col gap-0.5 rounded-[10px] px-2.5 py-2" style={{ background: 'var(--surface-3, #f6f7f8)' }}>
            {entry.steps.map((s, i) => {
              const st = entry.stepStatus?.[s.name];
              return (
                <div key={i} className="flex items-center gap-2 py-[3px] text-[12.5px]">
                  <span
                    className="w-[18px] h-[18px] rounded-full flex items-center justify-center text-[9.5px] shrink-0 font-medium"
                    style={{
                      background: st === 'done' ? 'rgba(52,199,123,.15)' : st === 'running' ? 'rgba(42,125,225,.14)' : 'var(--surface-3, #f1f2f4)',
                      color: st === 'done' ? '#2fb27b' : st === 'running' ? 'var(--accent, #2a7de1)' : 'var(--text-faint, #a0a6b0)',
                    }}
                  >
                    {st === 'done' ? '✓' : st === 'running' ? '⟳' : String(i + 1).padStart(2, '0')}
                  </span>
                  <span style={{ color: 'var(--text, #1d2129)' }}>{s.name}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

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
