import { useState, useRef, useEffect, useCallback } from 'react';
import { cn } from '../lib/utils';

export type ExecutionPolicy = 'plan' | 'manual' | 'accept_edits' | 'bypass';

const POLICIES = [
  { key: 'plan',         label: '规划',      desc: '只分析不修改',                              color: '#a855f7', shortcut: '1' },
  { key: 'manual',       label: '手动',      desc: '每次修改需确认',                            color: '#9ca3af', shortcut: '2' },
  { key: 'accept_edits', label: '接受编辑',  desc: '自动修改文件，危险操作仍需确认',              color: '#3b82f6', shortcut: '3' },
  { key: 'bypass',       label: '绕过权限',  desc: '完全自主——跳过所有审批检查',                  color: '#f59e0b', shortcut: '4' },
] as const;

const LABEL_MAP: Record<string, string> = Object.fromEntries(POLICIES.map(p => [p.key, p.label]));

interface Props {
  policy: ExecutionPolicy;
  onChange: (p: ExecutionPolicy) => void;
  disabled?: boolean;
}

export function ExecutionPolicySelector({ policy, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [bypassConfirm, setBypassConfirm] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const toastTimer = useRef(0);

  const current = POLICIES.find(p => p.key === policy)!;

  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [open]);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 2000) as unknown as number;
  }, []);

  useEffect(() => () => { if (toastTimer.current) window.clearTimeout(toastTimer.current); }, []);

  const select = useCallback((p: ExecutionPolicy) => {
    if (p === 'bypass') {
      setBypassConfirm(true);
      setOpen(false);
      return;
    }
    onChange(p);
    setOpen(false);
    showToast(`✓ ${LABEL_MAP[p]} 已启用`);
  }, [onChange, showToast]);

  const confirmBypass = useCallback(() => {
    onChange('bypass');
    setBypassConfirm(false);
    showToast('✓ 绕过权限 已启用 — Agent 可完全自主执行');
  }, [onChange, showToast]);

  return (
    <>
      {/* ── Trigger ── */}
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
          <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: current.color }} />
          <span className="hidden sm:inline">{current.label}</span>
          {/* on mobile: just the dot, on desktop: dot + label */}
          {current.key === 'bypass' && <span className="text-[10px] leading-none">⚠</span>}
          <svg
            className={cn('w-2.5 h-2.5 transition-transform duration-150', open && 'rotate-180')}
            viewBox="0 0 10 6" fill="none" stroke="currentColor" strokeWidth="1.5"
          ><path d="M1 1l4 4 4-4" /></svg>
        </button>

        {/* ── Dropdown ── */}
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
            <span className="text-[10px] font-medium tracking-wider text-[var(--text-faint)] uppercase">执行策略</span>
          </div>

          {POLICIES.map(p => {
            const active = policy === p.key;
            return (
              <button
                key={p.key}
                type="button"
                onClick={() => select(p.key as ExecutionPolicy)}
                disabled={active}
                className={cn(
                  'flex items-start gap-3 w-full px-3.5 py-2.5 text-left transition-colors duration-100',
                  active ? 'cursor-default' : 'cursor-pointer hover:bg-[var(--surface-muted)]',
                )}
                style={active ? { background: `${p.color}12` } : undefined}
              >
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0 mt-1.5"
                  style={{ background: p.color, opacity: active ? 1 : 0.6 }}
                />
                <span className="flex-1 min-w-0">
                  <span className="block text-xs font-medium" style={{ color: active ? 'var(--text)' : 'var(--text-muted)' }}>
                    {p.label}
                  </span>
                  <span className="block text-[10px] leading-snug mt-0.5 text-[var(--text-faint)]">{p.desc}</span>
                </span>
                {active && <span className="text-[10px] mt-1 shrink-0" style={{ color: p.color }}>✓</span>}
              </button>
            );
          })}

          {/* ── Autonomy gradient bar ── */}
          <div className="px-3.5 py-2 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-[9px] text-[var(--text-faint)]">低自主</span>
              <div className="flex-1 h-1 rounded-full" style={{
                background: 'linear-gradient(to right, #a855f7, #9ca3af, #3b82f6, #f59e0b)',
              }} />
              <span className="text-[9px] text-[var(--text-faint)]">高自主</span>
            </div>
          </div>
        </div>
      </div>

      {/* ── Bypass confirmation dialog ── */}
      {bypassConfirm && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)' }}>
          <div
            className="rounded-2xl w-[340px] max-w-[90vw] overflow-hidden"
            style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
            onClick={e => e.stopPropagation()}
          >
            <div className="px-5 py-4">
              <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: '#f59e0b' }}>
                ⚠ 开启绕过权限？
              </h3>
              <p className="text-xs text-[var(--text-muted)] mt-2">Agent 将获得完全自主权：</p>
              <ul className="mt-2 space-y-1.5 text-xs text-[var(--text-muted)]">
                {['无需确认直接修改文件', '自由执行 Shell 命令', '跳过所有审批弹窗'].map(s => (
                  <li key={s} className="flex items-center gap-2"><span style={{ color: '#f59e0b' }}>✓</span>{s}</li>
                ))}
              </ul>
              <p className="text-[10px] text-[var(--text-faint)] mt-3">仅在你完全信任当前任务时启用。</p>
            </div>
            <div className="flex gap-2 px-5 py-3 justify-end" style={{ borderTop: '1px solid var(--border-subtle)' }}>
              <button
                onClick={() => setBypassConfirm(false)}
                className="px-4 py-1.5 rounded-lg text-xs font-medium transition-colors hover:bg-[var(--surface-muted)]"
                style={{ color: 'var(--text-muted)' }}
              >取消</button>
              <button
                onClick={confirmBypass}
                className="px-4 py-1.5 rounded-lg text-xs font-semibold transition-colors"
                style={{ background: '#f59e0b', color: '#fff' }}
              >启用</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Toast ── */}
      <div
        className={cn(
          'fixed bottom-20 left-1/2 -translate-x-1/2 z-[150] px-4 py-2 rounded-full text-[11px] font-medium whitespace-nowrap',
          'transition-all duration-200',
          toast ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2 pointer-events-none',
        )}
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          boxShadow: '0 4px 20px rgba(0,0,0,0.12)',
          color: 'var(--text)',
        }}
      >{toast}</div>
    </>
  );
}
