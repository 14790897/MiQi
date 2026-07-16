import { useState, useRef, useEffect } from 'react';
import { Plus, FileEdit, ClipboardList, MessageCircle } from 'lucide-react';
import { cn } from '../../lib/utils';

export type ThreadMode = 'edit' | 'plan' | 'ask';

interface ModeConfig {
  label: string;
  icon: typeof FileEdit;
  shortcut: string;
  description: string;
}

const MODES: Record<ThreadMode, ModeConfig> = {
  edit: {
    label: 'Edit',
    icon: FileEdit,
    shortcut: '⌘E',
    description: 'Full tool access — diagnose and fix directly',
  },
  plan: {
    label: 'Plan',
    icon: ClipboardList,
    shortcut: '⌘P',
    description: 'Analyze first, present a plan, wait for confirmation',
  },
  ask: {
    label: 'Ask',
    icon: MessageCircle,
    shortcut: '⌘A',
    description: 'Read-only — questions, analysis, search, no file changes',
  },
};

interface Props {
  mode: ThreadMode;
  onChange: (mode: ThreadMode) => void;
  disabled?: boolean;
}

export function ModeSelector({ mode, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const current = MODES[mode];
  const Icon = current.icon;

  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [open]);

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        onClick={() => setOpen(!open)}
        disabled={disabled}
        className={cn(
          'flex items-center gap-1.5 rounded-lg p-1.5 text-xs transition-colors',
          'hover:bg-[var(--surface-muted)] disabled:opacity-50',
          open && 'bg-[var(--surface-muted)]',
        )}
        aria-label="Select agent mode"
        aria-expanded={open}
      >
        <Plus size={14} />
        <Icon size={13} className="text-[var(--text-muted)]" />
        <span className="text-[var(--text-muted)]">{current.label}</span>
      </button>

      {open && (
        <div
          className="absolute bottom-full left-0 mb-1.5 w-56 rounded-xl shadow-lg z-50 overflow-hidden"
          style={{ background: 'var(--surface)', border: '1px solid var(--border-subtle)' }}
        >
          {(Object.entries(MODES) as [ThreadMode, ModeConfig][]).map(([key, cfg]) => {
            const active = mode === key;
            const CfgIcon = cfg.icon;
            return (
              <button
                key={key}
                onClick={() => { onChange(key); setOpen(false); }}
                className={cn(
                  'flex items-start gap-3 w-full px-3.5 py-2.5 text-left transition-colors',
                  active
                    ? 'bg-[var(--accent)]/10'
                    : 'hover:bg-[var(--surface-muted)]',
                )}
              >
                <CfgIcon size={15} className="mt-0.5 shrink-0 text-[var(--text-muted)]" />
                <div className="min-w-0">
                  <div className="text-sm font-medium">{cfg.label}</div>
                  <div className="text-[11px] text-[var(--text-muted)] leading-snug">{cfg.description}</div>
                </div>
                <span className="text-[10px] text-[var(--text-faint)] ml-auto shrink-0 mt-0.5">{cfg.shortcut}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
