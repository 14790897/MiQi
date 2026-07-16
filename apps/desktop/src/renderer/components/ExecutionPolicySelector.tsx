import { useState, useRef, useEffect, useCallback } from 'react';
import { cn } from '../lib/utils';

export type ExecutionPolicy = 'plan' | 'manual' | 'accept_edits' | 'bypass';

interface PolicyConfig {
  label: string;
  shortcut: string;
  description: string;
}

const POLICIES: Record<ExecutionPolicy, PolicyConfig> = {
  plan:          { label: '规划', shortcut: '1', description: '只分析不修改' },
  manual:        { label: '手动', shortcut: '2', description: '每次修改需确认' },
  accept_edits:  { label: '接受编辑', shortcut: '3', description: '自动修改文件，危险操作仍需确认' },
  bypass:        { label: '绕过权限', shortcut: '4', description: '完全自主 ⚠' },
};

const COLORS: Record<ExecutionPolicy, string> = {
  plan:          '#a855f7',
  manual:        '#9ca3af',
  accept_edits:  '#3b82f6',
  bypass:        '#f59e0b',
};

interface Props {
  policy: ExecutionPolicy;
  onChange: (policy: ExecutionPolicy) => void;
  disabled?: boolean;
}

export function ExecutionPolicySelector({ policy, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const cfg = POLICIES[policy];
  const color = COLORS[policy];

  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [open]);

  const select = useCallback((p: ExecutionPolicy) => {
    onChange(p);
    setOpen(false);
  }, [onChange]);

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        disabled={disabled}
        className={cn(
          'flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors',
          'border hover:bg-[var(--surface-muted)] disabled:opacity-50',
          policy === 'bypass' && 'border-[var(--bypass)]',
        )}
        style={{
          background: 'var(--surface)',
          borderColor: open ? color : 'var(--border)',
          color: 'var(--text)',
        }}
        aria-label="执行策略"
        aria-expanded={open}
      >
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: color }} />
        <span>{cfg.label}</span>
        <span className="text-[8px] opacity-30 ml-0.5">▾</span>
        {policy === 'bypass' && <span className="text-[11px]">⚠</span>}
      </button>

      {open && (
        <div
          className="absolute top-full right-0 mt-1 min-w-[210px] rounded-xl shadow-lg z-50 overflow-hidden"
          style={{ background: 'var(--surface)', border: '1px solid var(--border-subtle)' }}
        >
          <div className="px-3.5 pt-2.5 pb-1 text-[10px] text-[var(--text-faint)] uppercase tracking-wide">
            执行策略
          </div>
          {(Object.entries(POLICIES) as [ExecutionPolicy, PolicyConfig][]).map(([key, c]) => {
            const active = policy === key;
            const cColor = COLORS[key];
            return (
              <button
                key={key}
                type="button"
                onClick={() => select(key)}
                className={cn(
                  'flex items-center gap-2.5 w-full px-3.5 py-2 text-left transition-colors text-xs',
                  active
                    ? 'font-medium'
                    : 'text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-muted)]',
                )}
                style={active ? { background: `${cColor}15`, color: 'var(--text)' } : undefined}
              >
                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: cColor }} />
                <span className="flex-1">
                  <span className="block">{c.label}</span>
                  <span className="text-[10px] text-[var(--text-faint)]">{c.description}</span>
                </span>
                <span
                  className="text-[10px] rounded px-1 shrink-0"
                  style={{ color: 'var(--text-faint)', border: '1px solid var(--border-subtle)' }}
                >
                  {c.shortcut}
                </span>
                {active && <span className="text-[10px] shrink-0" style={{ color: cColor }}>✓</span>}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
