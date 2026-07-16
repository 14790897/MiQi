import { useState, useCallback } from 'react';
import { cn } from '../lib/utils';

export type ExecutionPolicy = 'plan' | 'manual' | 'accept_edits' | 'bypass';

interface ChipDef {
  key: ExecutionPolicy;
  label: string;
  hint: string;
  color: string;
  shortcut: string;
}

const CHIPS: ChipDef[] = [
  { key: 'plan',         label: 'Plan',      hint: 'Read & plan only, no changes',                    color: '#a855f7', shortcut: '1' },
  { key: 'manual',       label: 'Manual',    hint: 'All modifications require confirmation',          color: '#9ca3af', shortcut: '2' },
  { key: 'accept_edits', label: 'Accept',    hint: 'Auto-apply file edits, risky ops need approval',  color: '#3b82f6', shortcut: '3' },
  { key: 'bypass',       label: 'Bypass',    hint: 'Skip all approvals — full autonomy',               color: '#f59e0b', shortcut: '4' },
];

interface Props {
  policy: ExecutionPolicy;
  onChange: (p: ExecutionPolicy) => void;
  /** Optional status bar items: { label, value, onClick? } */
  status?: { label: string; value: string; onClick?: () => void }[];
  disabled?: boolean;
}

export function ExecutionPolicySelector({ policy, onChange, status, disabled }: Props) {
  const [toast, setToast] = useState<string | null>(null);
  const [bypassConfirm, setBypassConfirm] = useState(false);
  const toastTimer = useState<ReturnType<typeof setTimeout> | null>(null)[1];

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    const id = setTimeout(() => setToast(null), 2000);
    toastTimer(id);
  }, []);

  const select = useCallback((p: ExecutionPolicy) => {
    if (p === 'bypass') { setBypassConfirm(true); return; }
    const label = CHIPS.find(c => c.key === p)!.label;
    onChange(p);
    showToast(`✓ ${label} enabled`);
  }, [onChange, showToast]);

  return (
    <>
      {/* ── Policy chips + status bar ── */}
      <div className="flex flex-col gap-1.5 w-full" style={{ marginTop: 2 }}>
        <div className="flex items-center gap-1.5 flex-wrap">
          {(CHIPS).map(c => {
            const active = policy === c.key;
            return (
              <button
                key={c.key}
                type="button"
                onClick={() => select(c.key)}
                disabled={disabled || active}
                title={c.hint}
                className={cn(
                  'flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium',
                  'transition-all duration-150 border',
                  active
                    ? 'cursor-default'
                    : 'cursor-pointer hover:bg-[var(--surface-muted)] text-[var(--text-muted)] border-transparent',
                  disabled && !active && 'opacity-40 cursor-not-allowed',
                )}
                style={active ? {
                  borderColor: c.color,
                  background: `${c.color}14`,
                  color: 'var(--text)',
                } : undefined}
              >
                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: c.color }} />
                <span>{c.label}</span>
                {c.key === 'bypass' && <span className="text-[10px] leading-none ml-0.5">⚠</span>}
              </button>
            );
          })}
        </div>

        {status && status.length > 0 && (
          <div className="flex items-center gap-2 text-[10px] text-[var(--text-faint)] flex-wrap">
            {status.map((s, i) => (
              <span key={i} className="flex items-center gap-1.5">
                {i > 0 && <span className="opacity-30">·</span>}
                <span className="opacity-50">{s.label}</span>
                {s.onClick ? (
                  <button
                    type="button"
                    onClick={s.onClick}
                    className="hover:text-[var(--text-muted)] transition-colors cursor-pointer"
                  >{s.value}</button>
                ) : (
                  <span className="text-[var(--text-muted)]">{s.value}</span>
                )}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* ── Bypass confirmation dialog ── */}
      {bypassConfirm && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)' }} onClick={() => setBypassConfirm(false)}>
          <div
            className="rounded-2xl w-[340px] max-w-[90vw] overflow-hidden"
            style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
            onClick={e => e.stopPropagation()}
          >
            <div className="px-5 py-4">
              <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: '#f59e0b' }}>⚠ Enable Bypass?</h3>
              <p className="text-xs text-[var(--text-muted)] mt-2">Agent gains full autonomy:</p>
              <ul className="mt-2 space-y-1.5 text-xs text-[var(--text-muted)]">
                {['Modify files without asking','Execute shell commands freely','Skip all approval dialogs'].map(s => (
                  <li key={s} className="flex items-center gap-2"><span style={{ color: '#f59e0b' }}>✓</span>{s}</li>
                ))}
              </ul>
              <p className="text-[10px] text-[var(--text-faint)] mt-3">Only enable for fully trusted tasks.</p>
            </div>
            <div className="flex gap-2 px-5 py-3 justify-end" style={{ borderTop: '1px solid var(--border-subtle)' }}>
              <button onClick={() => setBypassConfirm(false)} className="px-4 py-1.5 rounded-lg text-xs font-medium transition-colors hover:bg-[var(--surface-muted)]" style={{ color: 'var(--text-muted)' }}>Cancel</button>
              <button onClick={() => { onChange('bypass'); setBypassConfirm(false); showToast('✓ Bypass enabled'); }} className="px-4 py-1.5 rounded-lg text-xs font-semibold text-white" style={{ background: '#f59e0b' }}>Enable</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Toast ── */}
      <div
        className={cn(
          'fixed bottom-24 left-1/2 -translate-x-1/2 z-[150] px-4 py-2 rounded-full text-[11px] font-medium whitespace-nowrap',
          'transition-all duration-200',
          toast ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2 pointer-events-none',
        )}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', boxShadow: '0 4px 20px rgba(0,0,0,0.12)', color: 'var(--text)' }}
      >{toast}</div>
    </>
  );
}
