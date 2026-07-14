import { useState, useEffect, useCallback, useRef } from 'react';
import { cn } from '../lib/utils';
import { Plus, ListChecks, Settings, Play, Clock, Eye, CheckCircle2, RotateCcw, Archive } from 'lucide-react';
import { MiQiLogo } from './MiQiLogo';
import { ContextMenu } from './ContextMenu';
import { useSessionStatus, type SessionStatus } from '../hooks/useSessionStatus';
import type { SessionInfo } from '../../shared/ipc';

type FilterTab = 'ALL' | 'IN-PROGRESS' | 'REVIEW' | 'COMPLETED';

const MIN_WIDTH = 180;
const MAX_WIDTH = 480;
const DEFAULT_WIDTH = 260;

function formatTimestampKey(key: string): string {
  const ts = parseInt(key, 10);
  if (isNaN(ts)) return key;
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(ts));
}

function relativeTime(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  if (diff < 60_000) return '刚刚';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
  if (diff < 2 * 86_400_000) return '昨天';
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

interface SidebarProps {
  currentSession?: string;
  onSessionSelect?: (key: string) => void;
  onNavChange?: (id: string) => void;
  refreshKey?: number;
  onNewSession?: () => void;
}

export function Sidebar({
  currentSession,
  onSessionSelect,
  onNavChange,
  refreshKey,
  onNewSession,
}: SidebarProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [initialLoading, setInitialLoading] = useState(true);
  const [filter, setFilter] = useState<FilterTab>('ALL');
  const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_WIDTH);
  const isResizing = useRef(false);
  const sidebarRef = useRef<HTMLDivElement>(null);

  const { getStatus, getStatusDisplay, setStatus, clearStatus } = useSessionStatus();

  // Resize handler
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isResizing.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing.current) return;
      const newWidth = e.clientX - (sidebarRef.current?.getBoundingClientRect().left ?? 0);
      setSidebarWidth(Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, newWidth)));
    };
    const handleMouseUp = () => {
      if (isResizing.current) {
        isResizing.current = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      // cleanup if unmounted during drag
      isResizing.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, []);

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
    { value: 'REVIEW', label: '审阅' },
    { value: 'COMPLETED', label: '已完成' },
  ];

  const filteredSessions = sessions.filter((s) => {
    if (filter === 'ALL') return true;
    const status = getStatus(s.key);
    if (filter === 'IN-PROGRESS') return status === 'IN-PROGRESS';
    if (filter === 'REVIEW') return status === 'REVIEW';
    if (filter === 'COMPLETED') return status === 'COMPLETED';
    return true;
  });

  return (
    <div
      ref={sidebarRef}
      className="flex flex-col shrink-0 border-r relative"
      style={{
        width: sidebarWidth,
        background: 'var(--sidebar-bg)',
        borderColor: 'var(--sidebar-border)',
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
        <span className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
          任务
        </span>
        <button
          onClick={onNewSession}
          className="ml-auto w-6 h-6 rounded flex items-center justify-center transition-colors hover:bg-[var(--surface-muted)]"
          title="新建会话"
        >
          <Plus size={14} style={{ color: 'var(--text-faint)' }} />
        </button>
      </div>

      {/* Filter tabs */}
      <div className="min-w-0 max-w-full shrink-0 overflow-x-auto overflow-y-hidden px-3 pb-3">
        <div className="inline-flex w-max flex-nowrap items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-1">
        {FILTER_TABS.map((tab) => {
          const isActive = filter === tab.value;
          return (
            <button
              key={tab.value}
              onClick={() => setFilter(tab.value)}
              className={cn(
                'shrink-0 whitespace-nowrap rounded-md px-2.5 py-1.5 text-[11px] font-medium leading-none transition-colors',
                isActive
                  ? 'bg-[var(--surface)] text-[var(--text)] shadow-sm'
                  : 'text-[var(--text-muted)] hover:bg-[var(--surface)] hover:text-[var(--text)]',
              )}
            >
              {tab.label}
            </button>
          );
        })}
        </div>
      </div>

      {/* Session list — card style with left border + description */}
      <div className="flex-1 overflow-y-auto px-3 pb-2">
        {initialLoading && sessions.length === 0 ? (
          <div className="flex items-center justify-center py-6">
            <div className="w-4 h-4 border-2 border-[var(--border)] border-t-[var(--accent)] rounded-full animate-spin" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <ListChecks size={20} style={{ color: 'var(--text-faint)', opacity: 0.4 }} />
            <p className="text-xs" style={{ color: 'var(--text-faint)' }}>
              暂无任务
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {filteredSessions.slice(0, 20).map((s) => {
              const isActive = currentSession === s.key;
              const displayName = s.title || formatTimestampKey(s.key);
              const status = getStatusDisplay(getStatus(s.key));
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
                      label: '标记为审阅',
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
                  ]}
                >
                  {({ onContextMenu }) => (
                    <button
                      onClick={() => onSessionSelect?.(s.key)}
                      onContextMenu={onContextMenu}
                      className="w-full text-left rounded-xl px-3 py-3 transition-colors"
                      style={{
                        background: status.cardBg,
                        border: `1px solid ${isActive ? status.color : status.cardBorder}`,
                      }}
                    >
                      {/* Top row: pill status label left · time right */}
                      <div className="flex items-center justify-between mb-2">
                        <span
                          className="shrink-0 whitespace-nowrap rounded-full px-2.5 py-1 text-[10px] font-semibold leading-none"
                          style={{ background: status.bg, color: status.color }}
                        >
                          {status.label}
                        </span>
                        <span className="text-[10px]" style={{ color: 'var(--text-faint)' }}>
                          {relativeTime(s.updated_at)}
                        </span>
                      </div>
                      {/* Title — large bold, one line */}
                      <p
                        className="text-[13px] font-bold truncate mb-1"
                        style={{ color: 'var(--text)' }}
                        title={displayName}
                      >
                        {displayName}
                      </p>
                      {/* Description — small gray, multi-line */}
                      <p
                        className="text-[11px] leading-relaxed"
                        style={{ color: 'var(--text-muted)' }}
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
        )}
      </div>

      {/* Bottom bar */}
      <div
        className="shrink-0 px-4 py-2.5 border-t flex items-center justify-between"
        style={{ borderColor: 'var(--sidebar-border)' }}
      >
        <button
          className="flex items-center gap-1.5 text-[11px] cursor-pointer transition-all duration-150 hover:text-[var(--text)]"
          style={{ color: 'var(--text-faint)' }}
          onClick={() => onNavChange?.('settings')}
        >
          <Settings size={13} />
          <span>系统设置</span>
        </button>
        <span
          className="text-[10px] font-mono"
          style={{ color: 'var(--text-faint)' }}
        >
          PRO v{typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : 'dev'}
        </span>
      </div>
    </div>
  );
}
