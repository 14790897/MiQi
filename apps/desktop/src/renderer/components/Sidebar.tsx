import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { cn } from '../lib/utils';
import { Plus, ListChecks, Settings, Play, Clock, Eye, CheckCircle2, RotateCcw, Archive, Trash2, FolderOpen, Pencil } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { MiQiLogo } from './MiQiLogo';
import { ContextMenu } from './ContextMenu';
import { InputDialog } from './shared/InputDialog';
import { useSessionStatus, type SessionStatus } from '../hooks/useSessionStatus';
import type { SessionInfo } from '../../shared/ipc';

type FilterTab = 'ALL' | 'IN-PROGRESS' | 'REVIEW' | 'COMPLETED';

const MIN_WIDTH = 180;
const MAX_WIDTH = 480;

import { usePanelResize } from '../hooks/usePanelResize';

import { formatRelativeTime, formatShortDateTime } from '../lib/formatTime';

interface SidebarProps {
  currentSession?: string;
  onSessionSelect?: (key: string) => void;
  onNavChange?: (id: string) => void;
  refreshKey?: number;
  onNewSession?: () => void;
  /** Called after a successful rename so the parent can refresh the active
   *  chat header (which reads the title from the backend on reload). */
  onRenamed?: () => void;
}

const STATUS_ICONS: Record<SessionStatus, LucideIcon> = {
  'IN-PROGRESS': Play,
  'PENDING': Clock,
  'REVIEW': Eye,
  'COMPLETED': CheckCircle2,
  'CC': Eye,
};

function formatWorkspace(workspace?: string): string | null {
  if (!workspace) return null;
  const home = (typeof process !== 'undefined' ? process.env?.HOME : null) ?? '';
  let display = workspace;
  if (home && workspace.startsWith(home)) {
    display = '~' + workspace.slice(home.length);
  }
  if (display.length > 28) {
    display = '...' + display.slice(display.length - 25);
  }
  return display;
}

export function Sidebar({
  currentSession,
  onSessionSelect,
  onNavChange,
  refreshKey,
  onNewSession,
  onRenamed,
}: SidebarProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [initialLoading, setInitialLoading] = useState(true);
  const [filter, setFilter] = useState<FilterTab>('ALL');
  const [renameTarget, setRenameTarget] = useState<SessionInfo | null>(null);
  const { width: sidebarWidth, containerRef: sidebarRef, handleMouseDown } = usePanelResize({
    minWidth: MIN_WIDTH,
    maxWidth: MAX_WIDTH,
    defaultWidth: 260,
    computeWidth: (e, rect) => e.clientX - rect.left,
  });

  const { getStatus, getStatusDisplay, setStatus, clearStatus } = useSessionStatus();

  // ── Lazy rendering ──────────────────────────────────────────────────
  const PER_PAGE = 20;
  const [displayCount, setDisplayCount] = useState(PER_PAGE);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const listContainerRef = useRef<HTMLDivElement>(null);

  // Reset display count when sessions list or filter changes
  useEffect(() => {
    setDisplayCount(PER_PAGE);
  }, [sessions, filter]);

  const loadSessions = useCallback(async () => {
    try {
      const r = await window.miqi.sessions.list();
      setSessions(r?.sessions ?? []);
    } catch { /* Bridge not available */ }
    setInitialLoading(false);
  }, []);

  const handleRenameConfirm = useCallback(async (title: string) => {
    if (!renameTarget) return;
    // Cap at 100 chars and trim whitespace so the IPC validator (min 1, max 100)
    // can't reject an overlong/blank title and cause a silent no-op.
    const cleaned = title.trim().slice(0, 100);
    if (!cleaned) return;
    try {
      await window.miqi.sessions.rename(renameTarget.key, cleaned);
    } catch { /* ignore */ }
    setRenameTarget(null);
    onRenamed?.();
    loadSessions();
  }, [renameTarget, loadSessions, onRenamed]);

  useEffect(() => { loadSessions(); }, [loadSessions, refreshKey]);

  useEffect(() => {
    const unsub = window.miqi.runtime.onStateChange((status) => {
      if (status.state === 'running') loadSessions();
    });
    return () => { unsub(); };
  }, [loadSessions]);

  const FILTER_TABS: Array<{ value: FilterTab; label: string }> = [
    { value: 'ALL', label: '全部' },
    { value: 'IN-PROGRESS', label: '进行中' },
    { value: 'REVIEW', label: '待审阅' },
    { value: 'COMPLETED', label: '已完成' },
  ];

  // Single-pass: count per filter + compute filtered list (Copilot optimization)
  const { filterCounts, filteredSessions } = useMemo(() => {
    const counts: Record<FilterTab, number> = { ALL: 0, 'IN-PROGRESS': 0, REVIEW: 0, COMPLETED: 0 };
    const filtered: SessionInfo[] = [];
    for (const s of sessions) {
      counts.ALL++;
      const status = getStatus(s.key);
      if (status === 'IN-PROGRESS') counts['IN-PROGRESS']++;
      else if (status === 'REVIEW') counts.REVIEW++;
      else if (status === 'COMPLETED') counts.COMPLETED++;
      if (filter === 'ALL' || status === filter) filtered.push(s);
    }
    return { filterCounts: counts, filteredSessions: filtered };
  }, [sessions, filter, getStatus]);

  // IntersectionObserver: load next page when sentinel enters viewport
  useEffect(() => {
    const sentinel = sentinelRef.current;
    const container = listContainerRef.current;
    if (!sentinel || !container) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setDisplayCount((prev) => {
            const next = prev + PER_PAGE;
            return next > filteredSessions.length ? filteredSessions.length : next;
          });
        }
      },
      {
        root: container,
        rootMargin: '300px',
        threshold: 0,
      }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [filteredSessions.length]);

  return (
    <div
      ref={sidebarRef}
      className="sidebar-shell flex flex-col shrink-0 border-r relative"
      style={{
        width: sidebarWidth,
      }}
    >
      {/* Resize handle */}
      <div
        onMouseDown={handleMouseDown}
        className="absolute top-0 right-0 w-1.5 h-full cursor-col-resize hover:bg-[var(--accent)]/30 transition-colors z-10"
        style={{ marginRight: -2 }}
      />
      {/* Header: glitch M logo + Tasks title */}
      <div className="flex items-center gap-2.5 px-4 py-3 shrink-0">
        <MiQiLogo size={28} />
        <span className="text-sm font-semibold text-text" data-testid="nav-tasks-title">
          任务
        </span>
        <button
          onClick={onNewSession}
          className="ml-auto w-6 h-6 rounded flex items-center justify-center transition-colors hover:bg-[var(--surface-muted)]"
          title="新建会话"
          data-testid="nav-new-session"
        >
          <Plus size={14} style={{ color: 'var(--text-faint)' }} />
        </button>
      </div>

      {/* Filter tabs — underline style */}
      <div className="shrink-0 overflow-x-auto px-3 pb-2">
        <div className="flex items-stretch justify-between min-w-max" role="tablist">
        {FILTER_TABS.map((tab) => {
          const isActive = filter === tab.value;
          const count = filterCounts[tab.value];
          const tabButton = (
            <button
              key={tab.value}
              role="tab"
              aria-selected={isActive}
              onClick={() => setFilter(tab.value)}
              className={cn(
                'relative flex-1 flex items-center justify-center gap-1 py-2 text-xs font-medium transition duration-150 rounded-md',
                'hover:bg-black/[0.04]',
                isActive
                  ? 'text-[var(--text)] font-semibold'
                  : 'text-[var(--text-faint)] hover:text-[var(--text-muted)]',
              )}
            >
              {tab.label}
              {count > 0 && (
                <span
                  className={cn(
                    'inline-flex items-center justify-center min-w-[16px] h-[16px] px-1 rounded-full text-size-2xs font-medium leading-none',
                    isActive
                      ? 'text-[var(--accent)]'
                      : 'text-[var(--text-faint)]',
                  )}
                  style={isActive ? { background: 'color-mix(in srgb, var(--accent) 18%, transparent)' } : { background: 'var(--surface-muted)' }}
                >
                  {count}
                </span>
              )}
              {isActive && (
                <span className="absolute bottom-0 left-2 right-2 h-[2px] rounded-full bg-[var(--accent)]/70" />
              )}
            </button>
          );
          // Right-click on the 全部 tab: bulk delete / archive all
          if (tab.value === 'ALL') {
            return (
              <ContextMenu
                key={tab.value}
                items={[
                  {
                    label: '删除全部任务',
                    icon: <Trash2 size={13} />,
                    danger: true,
                    onSelect: async () => {
                      if (!window.confirm(`确认删除全部 ${count} 个任务？此操作不可撤销。`)) return;
                      for (const s of sessions) {
                        try { await window.miqi.sessions.delete(s.key); } catch { /* ignore */ }
                      }
                      loadSessions();
                    },
                  },
                  {
                    label: '归档全部任务',
                    icon: <Archive size={13} />,
                    onSelect: async () => {
                      for (const s of sessions) {
                        try { await window.miqi.sessions.archive(s.key); } catch { /* ignore */ }
                      }
                      loadSessions();
                    },
                  },
                ]}
              >
                {({ onContextMenu }) =>
                  React.cloneElement(
                    tabButton as React.ReactElement<{ onContextMenu?: (e: React.MouseEvent) => void }>,
                    { onContextMenu }
                  )
                }
              </ContextMenu>
            );
          }
          return tabButton;
        })}
        </div>
      </div>

      {/* Session list — card style with left border + description */}
      <div ref={listContainerRef} className="flex-1 overflow-y-auto px-3 pt-1 pb-2">
        {initialLoading && sessions.length === 0 ? (
          <div className="flex items-center justify-center py-6">
            <div className="w-4 h-4 border-2 border-[var(--border)] border-t-[var(--accent)] rounded-full animate-spin" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <ListChecks size={20} style={{ color: 'var(--text-faint)', opacity: 0.4 }} />
            <p className="text-xs text-text-faint">
              暂无任务
            </p>
          </div>
        ) : (
          /* Kimi 主导设计（WorkBuddy 学习）：卡片 → 扁平列表行
             彩色状态点（运行青/完成绿/审阅靛/等待灰）+ 一行一任务 + 细分割线 */
          <div className="divide-y divide-[var(--border)]/60">
            {filteredSessions.slice(0, displayCount).map((s) => {
              const isActive = currentSession === s.key;
              const displayName = s.title || formatShortDateTime(parseInt(s.key, 10));
              const wsPath = formatWorkspace(s.workspace);
              const sessionStatus = getStatus(s.key);
              const dotColor =
                sessionStatus === 'IN-PROGRESS' ? '#06b6d4' :
                sessionStatus === 'COMPLETED' ? '#10b981' :
                sessionStatus === 'REVIEW' ? '#6366f1' : '#94a3b8';
              return (
                <ContextMenu
                  key={s.key}
                  items={[
                    {
                      label: '标记为进行中',
                      icon: <Play size={13} />,
                      onSelect: () => setStatus(s.key, 'IN-PROGRESS'),
                    },
                    {
                      label: '标记为待处理',
                      icon: <Clock size={13} />,
                      onSelect: () => setStatus(s.key, 'PENDING'),
                    },
                    {
                      label: '标记为待审阅',
                      icon: <Eye size={13} />,
                      onSelect: () => setStatus(s.key, 'REVIEW'),
                    },
                    {
                      label: '标记为已完成',
                      icon: <CheckCircle2 size={13} />,
                      divider: true,
                      onSelect: () => setStatus(s.key, 'COMPLETED'),
                    },
                    ...(s.workspace ? [{
                      label: '在文件管理器中打开',
                      icon: <FolderOpen size={13} />,
                      onSelect: () => window.miqi.files.openContainingFolder(s.workspace!),
                    }] : []),
                    {
                      label: '重命名',
                      icon: <Pencil size={13} />,
                      onSelect: () => setRenameTarget(s),
                    },
                    {
                      label: '重置状态',
                      icon: <RotateCcw size={13} />,
                      danger: true,
                      onSelect: () => clearStatus(s.key),
                    },
                    {
                      label: '归档',
                      icon: <Archive size={13} />,
                      divider: true,
                      onSelect: async () => {
                        try {
                          await window.miqi.sessions.archive(s.key);
                          loadSessions();
                        } catch { /* ignore */ }
                      },
                    },
                    {
                      label: '删除对话',
                      icon: <Trash2 size={13} />,
                      danger: true,
                      onSelect: async () => {
                        if (!window.confirm(`删除对话「${s.title || s.key}」？此操作不可撤销。`)) return;
                        try {
                          await window.miqi.sessions.delete(s.key);
                          loadSessions();
                        } catch { /* ignore */ }
                      },
                    },
                  ]}
                >
                  {({ onContextMenu }) => (
                    <button
                      onClick={() => onSessionSelect?.(s.key)}
                      onContextMenu={onContextMenu}
                      className={cn(
                        'group w-full text-left rounded-lg px-3 py-2.5 transition-colors duration-150',
                        isActive ? 'bg-[var(--surface-muted)]' : 'hover:bg-black/[0.03]',
                      )}
                    >
                      {/* 一行：状态点 + 标题 + 时间（Kimi 设计：不堆砌） */}
                      <div className="flex items-center gap-3">
                        <span className="relative flex shrink-0 items-center justify-center">
                          <span
                            className="block rounded-full"
                            style={{
                              width: 8,
                              height: 8,
                              backgroundColor: dotColor,
                              ...(sessionStatus === 'IN-PROGRESS' ? { animation: 'turn-pulse 1.2s ease-in-out infinite' } : {}),
                            }}
                          />
                          {sessionStatus === 'IN-PROGRESS' && (
                            <span
                              className="absolute inline-flex h-full w-full rounded-full opacity-60 animate-ping"
                              style={{ backgroundColor: dotColor }}
                            />
                          )}
                        </span>
                        <p
                          className="flex-1 min-w-0 text-sm font-medium truncate text-text"
                          title={displayName}
                        >
                          {displayName}
                        </p>
                        <span className="shrink-0 text-[11px] text-text-faint tabular-nums">
                          {formatRelativeTime(s.updated_at)}
                        </span>
                      </div>
                      {/* 工作区路径——hover 显示（保持信息可及但不堆砌） */}
                      {wsPath && (
                        <p
                          className="mt-1 pl-[20px] text-[10px] truncate text-text-faint opacity-0 group-hover:opacity-100 transition-opacity"
                          title={s.workspace}
                        >
                          {wsPath}
                        </p>
                      )}
                    </button>
                  )}
                </ContextMenu>
              );
            })}
            {/* Sentinel element for lazy-load intersection detection */}
            {displayCount < filteredSessions.length && (
              <div ref={sentinelRef} className="h-1" />
            )}
          </div>
        )}
      </div>

      {/* Bottom bar */}
      <div
        className="shrink-0 px-4 py-2.5 border-t flex items-center justify-between"
        style={{ borderColor: 'var(--sidebar-border)' }}
      >
        <button
          className="flex items-center gap-1.5 text-size-2xs cursor-pointer transition duration-150 hover:scale-110 hover:text-[var(--text)] origin-left text-text-faint"
          onClick={() => onNavChange?.('settings')}
          data-testid="nav-system-settings"
        >
          <Settings size={13} />
          <span>系统设置</span>
        </button>
        <span
          className="text-size-2xs font-mono text-text-faint"
        >
          PRO v{typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : 'dev'}
        </span>
      </div>

      {/* Rename dialog */}
      <InputDialog
        open={renameTarget != null}
        onOpenChange={(open) => { if (!open) setRenameTarget(null); }}
        title="重命名会话"
        label="输入新的会话标题"
        defaultValue={renameTarget?.title ?? ''}
        onConfirm={handleRenameConfirm}
      />
    </div>
  );
}
