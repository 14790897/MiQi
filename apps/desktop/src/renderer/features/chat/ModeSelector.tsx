import { FileEdit, ClipboardList, MessageCircle } from 'lucide-react';
import { cn } from '../../lib/utils';
import { Tooltip } from '../../components/ui/Tooltip';

/* ─── Types ──────────────────────────────────────────────────────────── */

export type ThreadMode = 'edit' | 'plan' | 'ask';

interface ModeConfig {
  label: string;
  icon: typeof FileEdit;
  shortcut: string;
  description: string;
  emoji: string;
}

const MODE_CONFIG: Record<ThreadMode, ModeConfig> = {
  edit: {
    label: 'Edit',
    icon: FileEdit,
    shortcut: 'Ctrl+E',
    description: 'Default — full tool access, diagnose and fix directly',
    emoji: '✏️',
  },
  plan: {
    label: 'Plan',
    icon: ClipboardList,
    shortcut: 'Ctrl+P',
    description: 'Analyze first, present a plan, wait for confirmation before executing',
    emoji: '📋',
  },
  ask: {
    label: 'Ask',
    icon: MessageCircle,
    shortcut: 'Ctrl+A',
    description: 'Read-only — ask questions, analyze code, search, no file changes',
    emoji: '💬',
  },
};

/* ─── Props ──────────────────────────────────────────────────────────── */

interface ModeSelectorProps {
  mode: ThreadMode;
  onChange: (mode: ThreadMode) => void;
  disabled?: boolean;
}

/* ─── Component ──────────────────────────────────────────────────────── */

export function ModeSelector({ mode, onChange, disabled }: ModeSelectorProps) {
  return (
    <div
      className="inline-flex items-center gap-0.5 rounded-lg p-0.5"
      style={{
        background: 'var(--surface-muted)',
        border: '1px solid var(--border-subtle)',
      }}
      role="radiogroup"
      aria-label="Agent working mode"
    >
      {(Object.entries(MODE_CONFIG) as [ThreadMode, ModeConfig][]).map(([key, cfg]) => {
        const isActive = mode === key;
        const Icon = cfg.icon;

        return (
          <Tooltip
            key={key}
            content={`${cfg.emoji} ${cfg.label} mode — ${cfg.description} (${cfg.shortcut})`}
          >
            <button
              role="radio"
              aria-checked={isActive}
              disabled={disabled}
              onClick={() => onChange(key)}
              className={cn(
                'mode-selector-btn flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium',
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/40',
                'disabled:opacity-40 disabled:cursor-not-allowed',
                isActive
                  ? 'text-[var(--accent-text)] shadow-sm'
                  : 'text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface)]/60'
              )}
              style={isActive ? { background: 'var(--accent)' } : undefined}
            >
              <Icon size={13} />
              <span className="hidden sm:inline">{cfg.label}</span>
            </button>
          </Tooltip>
        );
      })}
    </div>
  );
}
