import { useState, useEffect, useCallback, useRef } from 'react';
import { cn } from '../lib/utils';
import { Plus, ListChecks } from 'lucide-react';
import { MiQiLogo } from './MiQiLogo';
import { ContextMenu } from './ContextMenu';
import { useSessionStatus, type SessionStatus } from '../hooks/useSessionStatus';
import type { SessionInfo } from '../../shared/ipc';

type FilterTab = 'ALL' | 'IN-PROGRESS' | 'REVIEW' | 'CC';

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
  if (diff < 60_000) return 'Just now';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} mins ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} hours ago`;
  if (diff < 2 * 86_400_000) return 'Yesterday';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
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

  const FILTER_TABS: FilterTab[] = ['ALL', 'IN-PROGRESS', 'REVIEW', 'CC'];

  const filteredSessions = sessions.filter((s, idx) => {
    if (filter === 'ALL') return true;
    const status = getStatus(s.key, idx);
    if (filter === 'IN-PROGRESS') return status === 'IN-PROGRESS';
    if (filter === 'REVIEW') return status === 'REVIEW' || status === 'PENDING'; // REVIEW maps to PENDING in demo
    if (filter === 'CC') return status === 'CC';
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
          Tasks
        </span>
        <button
          onClick={onNewSession}
          className="ml-auto w-6 h-6 rounded flex items-center justify-center transition-colors hover:bg-[var(--surface-muted)]"
          title="New Session"
        >
          <Plus size={14} style={{ color: 'var(--text-faint)' }} />
        </button>
      </div>

      {/* Filter tabs: ALL / IN PROGRESS / REVIEW / CC */}
      <div className="flex gap-1 px-4 pb-3 shrink-0">
        {FILTER_TABS.map((tab) => {
          const isActive = filter === tab;
          return (
            <button
              key={tab}
              onClick={() => setFilter(tab)}
              className={cn(
                'px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors',
                isActive
                  ? 'text-[var(--text)]'
                  : 'text-[var(--text-faint)] hover:text-[var(--text-muted)]',
              )}
              style={{
                background: isActive ? 'var(--surface-muted)' : 'transparent',
              }}
            >
              {tab}
            </button>
          );
        })}
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
              No active tasks
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {filteredSessions.slice(0, 20).map((s, idx) => {
              const isActive = currentSession === s.key;
              const displayName = s.title || formatTimestampKey(s.key);
              const status = getStatusDisplay(getStatus(s.key, idx));
              return (
                <ContextMenu
                  key={s.key}
                  items={[
                    {
                      label: 'Mark as In Progress',
                      onSelect: () => setStatus(s.key, 'IN-PROGRESS'),
                    },
                    {
                      label: 'Mark as Pending',
                      onSelect: () => setStatus(s.key, 'PENDING'),
                    },
                    {
                      label: 'Mark as Review',
                      onSelect: () => setStatus(s.key, 'REVIEW'),
                    },
                    {
                      label: 'Mark as Completed',
                      divider: true,
                      onSelect: () => setStatus(s.key, 'COMPLETED'),
                    },
                    {
                      label: 'Mark as CC',
                      onSelect: () => setStatus(s.key, 'CC'),
                    },
                    {
                      label: 'Reset to Default',
                      danger: true,
                      onSelect: () => clearStatus(s.key),
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
                          className="text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full"
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
                          ? `${s.message_count} messages`
                          : 'No description'}
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
        <span
          className="text-[11px] cursor-pointer hover:text-[var(--text)] transition-colors"
          style={{ color: 'var(--text-faint)' }}
          onClick={() => onNavChange?.('settings')}
        >
          System Settings
        </span>
        <span
          className="text-[10px] font-mono"
          style={{ color: 'var(--text-faint)' }}
        >
          PRO v0.4.29
        </span>
      </div>
    </div>
  );
}
