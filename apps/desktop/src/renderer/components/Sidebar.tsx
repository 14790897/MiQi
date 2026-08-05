import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { cn } from '../lib/utils';
import {
  Plus,
  ListChecks,
  Settings,
  Play,
  Clock,
  Eye,
  CheckCircle2,
  RotateCcw,
  Archive,
  Trash2,
  FolderKanban,
  MessageSquare,
  ChevronDown,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { MiQiLogo } from './MiQiLogo';
import { ContextMenu } from './ContextMenu';
import { useSessionStatus, type SessionStatus } from '../hooks/useSessionStatus';
import { useRuntime } from '../contexts/RuntimeContext';
import type { SessionInfo } from '../../shared/ipc';

type FilterTab = 'ALL' | 'IN-PROGRESS' | 'REVIEW' | 'COMPLETED';

const MIN_WIDTH = 180;
const MAX_WIDTH = 480;

import { usePanelResize } from '../hooks/usePanelResize';

import { formatRelativeTime } from '../lib/formatTime';

function formatSessionGroup(timestamp?: string | number): string {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfYesterday = startOfToday - 24 * 60 * 60 * 1000;
  const startOfWeek = startOfToday - 6 * 24 * 60 * 60 * 1000;
  const ts =
    typeof timestamp === 'number'
      ? timestamp
      : timestamp
        ? new Date(timestamp).getTime()
        : Date.now();
  if (ts >= startOfToday) return '今天';
  if (ts >= startOfYesterday) return '昨天';
  if (ts >= startOfWeek) return '本周';
  return '更早';
}

interface SidebarProps {
  currentSession?: string;
  onSessionSelect?: (key: string) => void;
  onNavChange?: (id: string) => void;
  activeNav?: string;
  refreshKey?: number;
  onNewSession?: () => void;
}

const STATUS_ICONS: Record<SessionStatus, LucideIcon> = {
  'IN-PROGRESS': Play,
  'PENDING': Clock,
  'REVIEW': Eye,
  'COMPLETED': CheckCircle2,
  'CC': Eye,
};

interface NavItem {
  id: string;
  label: string;
  icon: LucideIcon;
}

const NAV_ITEMS: NavItem[] = [
  { id: 'chat', label: '对话', icon: MessageSquare },
  { id: 'workspace', label: '工作区', icon: FolderKanban },
  { id: 'settings', label: '设置', icon: Settings },
];

export function Sidebar({
  currentSession,
  onSessionSelect,
  onNavChange,
  activeNav = 'chat',
  refreshKey,
  onNewSession,
}: SidebarProps) {
  const { status: runtimeStatus } = useRuntime();
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [initialLoading, setInitialLoading] = useState(true);
  const [filter, setFilter] = useState<FilterTab>('ALL');
  const { width: sidebarWidth, containerRef: sidebarRef, handleMouseDown } = usePanelResize({
    minWidth: MIN_WIDTH,
    maxWidth: MAX_WIDTH,
    defaultWidth: 240,
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

  const groupedSessions = useMemo(() => {
    const groups = new Map<string, SessionInfo[]>();
    for (const s of filteredSessions.slice(0, displayCount)) {
      const key = formatSessionGroup(s.updated_at);
      const list = groups.get(key);
      if (list) list.push(s);
      else groups.set(key, [s]);
    }
    return Array.from(groups.entries());
  }, [filteredSessions, displayCount]);

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
        background: 'var(--sidebar-dark-bg)',
        borderColor: 'var(--sidebar-dark-border)',
      }}
    >
      {/* Resize handle */}
      <div
        onMouseDown={handleMouseDown}
        className="absolute top-0 right-0 w-1.5 h-full cursor-col-resize hover:bg-[var(--accent)]/30 transition-colors z-10"
        style={{ marginRight: -2 }}
      />
      {/* Brand */}
      <div className="flex items-center gap-2.5 px-4 pt-3 pb-2 shrink-0">
        <MiQiLogo size={28} />
        <div className="min-w-0 leading-tight">
          <div className="text-[14px] font-semibold text-text" data-testid="sidebar-brand">
            MiQi
          </div>
          <div className="text-[11px] text-text-faint">Desktop</div>
        </div>
      </div>

      {/* Workspace switcher */}
      <button
        onClick={() => onNavChange?.('workspace')}
        className={cn(
          'mx-3 mb-2 flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-left transition-colors',
          activeNav === 'workspace' ? 'bg-[var(--sidebar-dark-2)]' : 'hover:bg-[var(--sidebar-dark-2)]'
        )}
        style={{ border: '1px solid var(--sidebar-dark-border)' }}
      >
        <FolderKanban size={16} style={{ color: 'var(--accent)' }} />
        <span className="min-w-0 flex-1 leading-tight">
          <span className="block text-[13px] font-medium text-text">MiQi 工作区</span>
          <span className="block text-[11px] text-text-faint">desktop:default</span>
        </span>
        <ChevronDown size={14} style={{ color: 'var(--sidebar-dark-faint)' }} />
      </button>

      {/* Navigation */}
      <nav
        className="shrink-0 flex flex-col gap-0.5 px-2.5 pb-2 border-b"
        style={{ borderColor: 'var(--sidebar-dark-border)' }}
      >
        {NAV_ITEMS.map((item) => {
          const isActive = activeNav === item.id;
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              onClick={() => onNavChange?.(item.id)}
              className={cn(
                'flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[12px] font-medium transition-colors w-full text-left min-w-0',
                isActive ? 'bg-[var(--sidebar-dark-2)]' : 'hover:bg-[var(--sidebar-dark-2)]'
              )}
              style={{ color: isActive ? 'var(--sidebar-dark-text)' : 'var(--sidebar-dark-muted)' }}
            >
              <Icon size={14} className="shrink-0" style={{ color: isActive ? 'var(--accent)' : 'var(--sidebar-dark-faint)' }} />
              <span className="truncate">{item.label}</span>
            </button>
          );
        })}
      </nav>
      {/* Session header */}
      <div className="flex items-center justify-between px-4 pt-2.5 pb-1.5 shrink-0">
        <span className="text-label font-semibold text-text" data-testid="nav-tasks-title">
          工作区
        </span>
        <button
          onClick={onNewSession}
          className="w-6 h-6 rounded flex items-center justify-center transition-colors hover:bg-[var(--sidebar-dark-2)]"
          title="新建会话"
          data-testid="nav-new-session"
        >
          <Plus size={14} style={{ color: 'var(--sidebar-dark-faint)' }} />
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
                'relative flex-1 flex items-center justify-center gap-1 py-2 text-[12px] font-medium transition duration-150 rounded-md',
                'hover:bg-[var(--sidebar-dark-2)]',
                isActive
                  ? 'text-[var(--sidebar-dark-text)] font-semibold'
                  : 'text-[var(--sidebar-dark-faint)] hover:text-[var(--sidebar-dark-muted)]',
              )}
            >
              {tab.label}
              {count > 0 && (
                <span
                  className={cn(
                    'inline-flex items-center justify-center min-w-[16px] h-[16px] px-1 rounded-full text-label font-medium leading-none',
                    isActive
                      ? 'text-[var(--accent)]'
                      : 'text-[var(--sidebar-dark-faint)]',
                  )}
                  style={isActive ? { background: 'color-mix(in srgb, var(--accent) 18%, transparent)' } : { background: 'var(--sidebar-dark-2)' }}
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
                {({ onContextMenu }) => React.cloneElement<any>(tabButton, { onContextMenu })}
              </ContextMenu>
            );
          }
          return tabButton;
        })}
        </div>
      </div>

      {/* Session list — grouped rows with status and metadata */}
      <div ref={listContainerRef} className="flex-1 overflow-y-auto px-2 pt-1 pb-2">
        {initialLoading && sessions.length === 0 ? (
          <div className="flex items-center justify-center py-6">
            <div className="w-4 h-4 border-2 border-[var(--border)] border-t-[var(--accent)] rounded-full animate-spin" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <ListChecks size={20} style={{ color: 'var(--sidebar-dark-faint)', opacity: 0.4 }} />
            <p className="text-caption text-text-faint">
              暂无工作区
            </p>
          </div>
        ) : (
          <div className="space-y-2.5">
            {groupedSessions.map(([groupLabel, groupSessions]) => (
              <div key={groupLabel} className="space-y-0.5">
                <div className="px-2.5 pt-1 pb-0.5 text-label uppercase text-text-faint">
                  {groupLabel}
                </div>
                {groupSessions.map((s) => {
              const isActive = currentSession === s.key;
              const displayName = s.title || '未命名工作区';
              const sessionStatus = getStatus(s.key);
              const status = getStatusDisplay(sessionStatus);
              const StatusIcon = STATUS_ICONS[sessionStatus];
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
                      label: '删除工作区',
                      icon: <Trash2 size={13} />,
                      danger: true,
                      onSelect: async () => {
                        if (!window.confirm(`删除工作区「${s.title || s.key}」？此操作不可撤销。`)) return;
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
                      data-testid="session-row"
                      className={cn(
                        'group w-full text-left rounded-xl px-2.5 py-2 transition duration-150',
                        isActive
                          ? 'bg-[var(--surface-elevated)]'
                          : 'hover:bg-[var(--sidebar-dark-2)]'
                      )}
                      style={{ background: isActive ? status.cardBg : 'transparent' }}
                    >
                      {/* Top row: status icon + label left · time right */}
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-1.5">
                          <span
                            className="shrink-0 flex items-center justify-center w-4 h-4 rounded"
                            style={{ background: status.bg, color: status.color }}
                          >
                            <StatusIcon size={10} strokeWidth={2.5} />
                          </span>
                          <span className="text-[12px] font-medium" style={{ color: sessionStatus === 'IN-PROGRESS' ? status.bg : status.color }}>
                            {status.label}
                          </span>
                        </div>
                        <span className="text-[12px] text-text-faint">
                          {formatRelativeTime(s.updated_at)}
                        </span>
                      </div>
                      {/* Title — large bold, one line */}
                      <p
                        className="text-[13px] font-semibold truncate mb-0.5 text-text"
                        title={displayName}
                      >
                        {displayName}
                      </p>
                      {/* Description — small gray, multi-line */}
                      <p
                        className="text-[12px] leading-snug text-text-muted truncate"
                      >
                        {s.message_count != null
                          ? `${s.message_count} 条消息`
                          : '暂无描述'}
                      </p>
                    </button>
                  )}
                </ContextMenu>
              );
                })}
              </div>
            ))}
            {/* Sentinel element for lazy-load intersection detection */}
            {displayCount < filteredSessions.length && (
              <div ref={sentinelRef} className="h-1" />
            )}
          </div>
        )}
      </div>

      {/* Profile footer */}
      <div
        className="shrink-0 px-4 py-3 border-t"
        style={{ borderColor: 'var(--sidebar-dark-border)' }}
      >
        <div className="flex items-center gap-2.5">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center text-[12px] font-bold text-white shrink-0"
            style={{ background: 'var(--avatar-dark)' }}
          >
            M
          </div>
          <div className="min-w-0 flex-1 leading-tight">
            <div className="text-[13px] font-medium text-text">MiQi 智能体</div>
            <div className="text-[11px] text-text-faint">
              {runtimeStatus.state === 'running' ? '本地模式 · 在线' : '本地模式 · 离线'}
            </div>
          </div>
          <button
            onClick={() => onNavChange?.('settings')}
            className="h-7 px-2 rounded-md flex items-center gap-1.5 transition-colors hover:bg-[var(--sidebar-dark-2)]"
            data-testid="nav-system-settings"
            title="设置"
          >
            <Settings size={14} style={{ color: 'var(--sidebar-dark-faint)' }} />
            <span className="text-[11px] text-text-faint">系统设置</span>
          </button>
        </div>
      </div>

      {/* Version footer */}
      <div
        className="shrink-0 px-4 py-2 border-t flex items-center justify-end"
        style={{ borderColor: 'var(--sidebar-dark-border)' }}
      >
        <span className="text-[10px] font-mono text-text-faint">
          PRO v{typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : 'dev'}
        </span>
      </div>
    </div>
  );
}
