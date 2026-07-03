import { useState, useEffect, useCallback } from 'react';
import { cn } from '../lib/utils';
import { Plus, Archive, ListChecks, Circle } from 'lucide-react';
import type { SessionInfo } from '../../shared/ipc';

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

/** Derive a status tag color from the session index (simple demo heuristic). */
function statusForIndex(idx: number): { label: string; bg: string; color: string } {
  if (idx === 0) return { label: 'IN PROGRESS', bg: '#dceeff', color: '#1848a0' };
  if (idx === 1) return { label: 'COMPLETED', bg: '#d4f0e0', color: '#1a6030' };
  return { label: 'PENDING', bg: '#f0f0ec', color: '#888' };
}

interface SidebarProps {
  currentSession?: string;
  onSessionSelect?: (key: string) => void;
  refreshKey?: number;
  onNewSession?: () => void;
}

export function Sidebar({
  currentSession,
  onSessionSelect,
  refreshKey,
  onNewSession,
}: SidebarProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [initialLoading, setInitialLoading] = useState(true);

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

  return (
    <div
      className="flex flex-col shrink-0 border-r"
      style={{
        width: 260,
        background: 'var(--sidebar-bg)',
        borderColor: 'var(--sidebar-border)',
      }}
    >
      {/* Tasks header */}
      <div className="flex items-center justify-between px-4 pt-3 pb-2 shrink-0">
        <span
          className="text-xs font-semibold uppercase tracking-wider"
          style={{ color: 'var(--text-muted)' }}
        >
          Tasks
        </span>
        <button
          onClick={onNewSession}
          className="w-5 h-5 rounded flex items-center justify-center transition-colors hover:bg-[var(--surface-muted)]"
          title="New Session"
        >
          <Plus size={13} style={{ color: 'var(--text-faint)' }} />
        </button>
      </div>

      {/* Session list — wide cards with description */}
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
            {sessions.slice(0, 20).map((s, idx) => {
              const isActive = currentSession === s.key;
              const displayName = s.title || formatTimestampKey(s.key);
              const status = statusForIndex(idx);
              return (
                <button
                  key={s.key}
                  onClick={() => onSessionSelect?.(s.key)}
                  className={cn(
                    'w-full text-left rounded-xl px-3 py-3 transition-colors',
                    isActive
                      ? 'bg-[var(--surface-muted)]'
                      : 'hover:bg-[var(--surface-elevated)]',
                  )}
                >
                  {/* Status row */}
                  <div className="flex items-center gap-1.5 mb-1.5">
                    <Circle
                      size={8}
                      style={{ fill: status.color, color: status.color }}
                    />
                    <span
                      className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded"
                      style={{ background: status.bg, color: status.color }}
                    >
                      {status.label}
                    </span>
                    <span
                      className="text-[10px] ml-auto"
                      style={{ color: 'var(--text-faint)' }}
                    >
                      {relativeTime(s.updated_at)}
                    </span>
                  </div>
                  {/* Title */}
                  <p
                    className="text-sm font-medium truncate mb-0.5"
                    style={{ color: 'var(--text)' }}
                    title={displayName}
                  >
                    {displayName}
                  </p>
                  {/* Description / subtitle */}
                  <p
                    className="text-xs truncate"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    {s.message_count != null
                      ? `${s.message_count} messages`
                      : 'No description'}
                  </p>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Bottom — settings + version */}
      <div
        className="shrink-0 px-4 py-2.5 border-t flex items-center justify-between"
        style={{ borderColor: 'var(--sidebar-border)' }}
      >
        <span
          className="text-[11px] cursor-pointer hover:text-[var(--text)] transition-colors"
          style={{ color: 'var(--text-faint)' }}
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
