import { useState, useEffect, useCallback } from 'react';
import { cn } from '../lib/utils';
import {
  MessageSquare,
  Clock,
  FolderOpen,
  BookOpen,
  Wrench,
  Settings,
  Plus,
  Plug,
  Archive,
  Cpu,
  Bot,
  ListChecks,
  Shield,
  Package,
  CheckSquare,
  ChevronDown,
  ChevronRight,
  Circle,
  type LucideIcon,
} from 'lucide-react';
import type { SessionInfo } from '../../shared/ipc';

interface NavItem {
  id: string;
  label: string;
  icon: LucideIcon;
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    title: '核心功能',
    items: [
      { id: 'chat', label: '对话', icon: MessageSquare },
      { id: 'workspace', label: '文件', icon: FolderOpen },
    ],
  },
  {
    title: '业务流程',
    items: [
      { id: 'approvals', label: '审批', icon: CheckSquare },
      { id: 'cron', label: '定时任务', icon: Clock },
    ],
  },
  {
    title: 'AI能力',
    items: [
      { id: 'agents', label: 'Agents', icon: Bot },
      { id: 'plan', label: 'Plan', icon: ListChecks },
      { id: 'memory', label: '记忆', icon: BookOpen },
      { id: 'experience', label: '经验', icon: BookOpen },
      { id: 'skills', label: '技能', icon: Wrench },
      { id: 'mcps', label: 'MCPs', icon: Plug },
    ],
  },
  {
    title: '系统管理',
    items: [
      { id: 'settings', label: '设置', icon: Settings },
      { id: 'wsl', label: 'WSL', icon: Cpu },
      { id: 'permissions', label: 'Permissions', icon: Shield },
      { id: 'plugins', label: 'Plugins', icon: Package },
    ],
  },
];

function formatTimestampKey(key: string): string {
  const ts = parseInt(key, 10);
  if (isNaN(ts)) return key;
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
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
  activeNav: string;
  onNavChange: (id: string) => void;
  currentSession?: string;
  onSessionSelect?: (key: string) => void;
  refreshKey?: number;
  onNewSession?: () => void;
  runtimeState?: string; // 'running' | 'stopped'
}

export function Sidebar({
  activeNav,
  onNavChange,
  currentSession,
  onSessionSelect,
  refreshKey,
  onNewSession,
  runtimeState,
}: SidebarProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [initialLoading, setInitialLoading] = useState(true);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(
    new Set(['核心功能'])
  );

  const toggleGroup = (groupTitle: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupTitle)) {
        next.delete(groupTitle);
      } else {
        next.add(groupTitle);
      }
      return next;
    });
  };

  const loadSessions = useCallback(async () => {
    try {
      const r = await window.miqi.sessions.list();
      setSessions(r?.sessions ?? []);
    } catch {
      /* Bridge not available */
    }
    setInitialLoading(false);
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions, refreshKey]);

  // Re-load when bridge becomes running (app startup race condition)
  useEffect(() => {
    const unsub = window.miqi.runtime.onStateChange((status) => {
      if (status.state === 'running') loadSessions();
    });
    return () => {
      unsub();
    };
  }, [loadSessions]);

  const displayStatus = runtimeState || 'running';
  const statusLabel = displayStatus === 'running' ? '运行中' : '已停止';
  const statusColor = displayStatus === 'running' ? 'var(--success)' : 'var(--text-faint)';

  return (
    <div
      className="flex flex-col shrink-0 border-r"
      style={{
        width: 240,
        background: 'var(--sidebar-bg)',
        borderColor: 'var(--sidebar-border)',
      }}
    >
      {/* Logo + title — single text logo with gradient accent */}
      <div
        className="flex items-center gap-2 px-4 h-12 border-b shrink-0"
        style={{ borderColor: 'var(--sidebar-border)' }}
      >
        <span
          className="text-sm font-bold"
          style={{
            background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}
        >
          M
        </span>
        <span className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
          MiQi Workbench
        </span>
      </div>

      {/* Nav items */}
      <nav
        className="px-2 py-2 flex flex-col shrink-0"
        style={{ borderColor: 'var(--sidebar-border)' }}
      >
        {NAV_GROUPS.map((group) => {
          const isExpanded = expandedGroups.has(group.title);
          return (
            <div key={group.title} className="mb-1">
              <button
                onClick={() => toggleGroup(group.title)}
                className="flex items-center gap-1 px-3 py-1 w-full text-left"
              >
                {isExpanded ? (
                  <ChevronDown size={12} style={{ color: 'var(--text-faint)' }} />
                ) : (
                  <ChevronRight size={12} style={{ color: 'var(--text-faint)' }} />
                )}
                <span
                  className="text-xs font-semibold uppercase tracking-wider"
                  style={{ color: 'var(--text-faint)' }}
                >
                  {group.title}
                </span>
              </button>
              {isExpanded && (
                <div className="flex flex-col gap-0.5">
                  {group.items.map((item) => {
                    const isActive = activeNav === item.id;
                    const Icon = item.icon;
                    return (
                      <button
                        key={item.id}
                        onClick={() => onNavChange(item.id)}
                        className={cn(
                          'flex items-center gap-2.5 px-3 py-1.5 rounded-r-lg text-sm transition-colors text-left w-full relative',
                          isActive
                            ? 'font-medium'
                            : 'hover:bg-[var(--surface-muted)]'
                        )}
                        style={{
                          background: isActive ? 'var(--surface-muted)' : undefined,
                          color: isActive ? 'var(--text)' : 'var(--text-muted)',
                          borderLeft: isActive
                            ? '3px solid var(--sidebar-active-border)'
                            : '3px solid transparent',
                          borderRadius: isActive ? '0 8px 8px 0' : undefined,
                          paddingLeft: isActive ? '9px' : '12px',
                        }}
                      >
                        <Icon size={15} />
                        {item.label}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* Sessions header */}
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

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
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
          <div className="space-y-1">
            {sessions.slice(0, 20).map((s, idx) => {
              const isActive = currentSession === s.key;
              const displayName = s.title || formatTimestampKey(s.key);
              // Status dot: first 3 items get green (in-progress), rest get gray
              const dotColor = idx < 3 ? 'var(--success)' : 'var(--text-faint)';
              return (
                <div
                  key={s.key}
                  className={cn(
                    'w-full flex items-start gap-2 px-2 py-1.5 rounded text-left transition-colors group',
                    isActive
                      ? 'bg-[var(--surface-muted)]'
                      : 'hover:bg-[var(--surface-elevated)]'
                  )}
                >
                  <button
                    className="flex-1 flex items-start gap-2 min-w-0"
                    onClick={() => {
                      onNavChange('chat');
                      onSessionSelect?.(s.key);
                    }}
                  >
                    <Circle
                      size={8}
                      className="flex-shrink-0 mt-1.5"
                      style={{ fill: dotColor, color: dotColor }}
                    />
                    <div className="flex-1 min-w-0 text-left">
                      <p
                        className="text-sm truncate text-left"
                        style={{ color: 'var(--text)' }}
                        title={displayName}
                      >
                        {displayName}
                      </p>
                      <p className="text-xs text-left" style={{ color: 'var(--text-muted)' }}>
                        {relativeTime(s.updated_at)}
                      </p>
                    </div>
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (!window.confirm(`归档对话「${displayName}」？归档后可在设置中找回。`))
                        return;
                      window.miqi.sessions.archive(s.key).then(() => {
                        loadSessions();
                        if (currentSession === s.key) onNewSession?.();
                      });
                    }}
                    className="shrink-0 w-5 h-5 rounded flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-[var(--surface-muted)]"
                    style={{ color: 'var(--text-faint)' }}
                    title="归档对话"
                  >
                    <Archive size={12} />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Bottom status + System Settings */}
      <div
        className="shrink-0 px-4 py-2 border-t"
        style={{ borderColor: 'var(--sidebar-border)' }}
      >
        <div className="flex items-center gap-1.5 mb-1">
          <Circle
            size={6}
            style={{ fill: statusColor, color: statusColor }}
          />
          <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            {statusLabel}
          </span>
        </div>
        <button
          onClick={() => onNavChange('settings')}
          className="text-[11px] hover:text-[var(--text)] transition-colors text-left w-full"
          style={{ color: 'var(--text-faint)' }}
        >
          System Settings
        </button>
      </div>
    </div>
  );
}
