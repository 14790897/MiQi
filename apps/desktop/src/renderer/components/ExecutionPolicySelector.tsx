import { useState, useRef, useEffect, useCallback } from 'react';
import { cn } from '../lib/utils';

export type ExecutionPolicy = 'plan' | 'manual' | 'accept_edits' | 'bypass';

const POLICIES: Record<ExecutionPolicy, { label: string; desc: string }> = {
  plan:          { label: '规划', desc: '只分析不修改' },
  manual:        { label: '手动', desc: '每次修改需确认' },
  accept_edits:  { label: '接受编辑', desc: '自动修改文件，危险操作仍需确认' },
  bypass:        { label: '绕过权限', desc: '完全自主 ⚠' },
};

const COLORS: Record<ExecutionPolicy, string> = {
  plan:          '#a855f7',
  manual:        '#9ca3af',
  accept_edits:  '#3b82f6',
  bypass:        '#f59e0b',
};

interface Props {
  policy: ExecutionPolicy;
  onChange: (p: ExecutionPolicy) => void;
  disabled?: boolean;
}

export function ExecutionPolicySelector({ policy, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const cfg = POLICIES[policy];
  const color = COLORS[policy];

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
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
          'group flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium',
          'transition-all duration-150',
          'hover:bg-[var(--surface-muted)] active:scale-[0.97]',
          'disabled:opacity-50 disabled:cursor-not-allowed',
        )}
        style={{ color: 'var(--text-muted)' }}
      >
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: color }} />
        <span>{cfg.label}</span>
        <svg
          className={cn('w-2.5 h-2.5 transition-transform duration-150', open && 'rotate-180')}
          viewBox="0 0 10 6" fill="none" stroke="currentColor" strokeWidth="1.5"
        >
          <path d="M1 1l4 4 4-4" />
        </svg>
      </button>

      <div
        className={cn(
          'absolute left-0 bottom-full mb-1.5 w-56 origin-bottom-left',
          'rounded-xl shadow-lg backdrop-blur z-50 overflow-hidden',
          'transition-all duration-150',
          open
            ? 'opacity-100 scale-100 translate-y-0 pointer-events-auto'
            : 'opacity-0 scale-95 translate-y-1 pointer-events-none',
        )}
        style={{
          background: 'color-mix(in srgb, var(--surface) 96%, var(--surface-muted))',
          border: '1px solid var(--border-subtle)',
          boxShadow: '0 12px 40px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06)',
        }}
      >
        <div className="px-3.5 pt-3 pb-1.5">
          <span className="text-[10px] font-medium tracking-wider text-[var(--text-faint)] uppercase">
            执行策略
          </span>
        </div>
        {(Object.entries(POLICIES) as [ExecutionPolicy, typeof POLICIES['plan']][]).map(([key, c]) => {
          const active = policy === key;
          const cColor = COLORS[key];
          return (
            <button
              key={key}
              type="button"
              onClick={() => select(key)}
              disabled={active}
              className={cn(
                'flex items-start gap-3 w-full px-3.5 py-2.5 text-left transition-colors duration-100',
                active
                  ? 'cursor-default'
                  : 'cursor-pointer hover:bg-[var(--surface-muted)]',
              )}
              style={active ? { background: `${cColor}12` } : undefined}
            >
              <span
                className="w-1.5 h-1.5 rounded-full shrink-0 mt-1.5"
                style={{ background: cColor, opacity: active ? 1 : 0.6 }}
              />
              <span className="flex-1 min-w-0">
                <span
                  className="block text-xs font-medium"
                  style={{ color: active ? 'var(--text)' : 'var(--text-muted)' }}
                >
                  {c.label}
                </span>
                <span className="block text-[10px] leading-snug mt-0.5 text-[var(--text-faint)]">
                  {c.desc}
                </span>
              </span>
              {active && (
                <span className="text-[10px] mt-1 shrink-0" style={{ color: cColor }}>✓</span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
