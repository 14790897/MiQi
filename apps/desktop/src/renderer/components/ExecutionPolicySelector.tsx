import { useState, useRef, useEffect, useCallback } from 'react';
import { cn } from '../lib/utils';

export type ExecutionPolicy = 'plan' | 'manual' | 'accept_edits' | 'bypass';

const POLICIES = [
  { key: 'plan',         label: '规划',      desc: '只分析不修改',                              color: '#a855f7' },
  { key: 'manual',       label: '手动',      desc: '每次修改需确认',                            color: '#9ca3af' },
  { key: 'accept_edits', label: '接受编辑',  desc: '自动修改文件，危险操作仍需确认',              color: '#3b82f6' },
  { key: 'bypass',       label: '绕过权限',  desc: '完全自主——跳过所有审批检查',                  color: '#f59e0b' },
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
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
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
    if (p === 'bypass') { setBypassConfirm(true); setOpen(false); return; }
    onChange(p); setOpen(false);
    showToast(`✓ ${LABEL_MAP[p]} 已启用`);
  }, [onChange, showToast]);

  const confirmBypass = useCallback(() => {
    onChange('bypass'); setBypassConfirm(false);
    showToast('✓ 绕过权限 已启用');
  }, [onChange, showToast]);

  return (
    <>
      <div ref={ref} className="relative shrink-0">
        {/* ── Trigger: matches mockup ── */}
        <button
          type="button" onClick={() => setOpen(!open)} disabled={disabled}
          className={cn(
            'flex items-center gap-1.5 rounded-[7px] px-2.5 py-1 text-xs font-semibold',
            'transition-all duration-150 border',
            'hover:bg-[var(--surface-muted)] active:scale-[0.97]',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            policy === 'bypass' && 'border-[#f59e0b]',
          )}
          style={{ background: 'var(--surface)', borderColor: policy === 'bypass' ? undefined : 'var(--border)', color: 'var(--text)' }}
        >
          <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: current.color }} />
          <span>{current.label}</span>
          <span className="text-[8px] opacity-30">▾</span>
          {current.key === 'bypass' && <span className="text-[11px] leading-none">⚠</span>}
        </button>

        {/* ── Dropdown: matches mockup spacing ── */}
        <div
          className={cn(
            'absolute left-0 bottom-full mb-1 w-60 origin-bottom-left rounded-xl shadow-lg z-50 overflow-hidden',
            'transition-all duration-150',
            open ? 'opacity-100 scale-100 translate-y-0' : 'opacity-0 scale-95 translate-y-1 pointer-events-none',
          )}
          style={{ background: 'var(--surface)', border: '1px solid var(--border)', boxShadow: '0 8px 30px rgba(0,0,0,0.12)' }}
        >
          <div style={{ padding: '8px 14px 4px' }}>
            <span className="text-[11px] font-medium tracking-wider text-[var(--text-faint)]">执行策略</span>
          </div>
          {POLICIES.map(p => {
            const active = policy === p.key;
            return (
              <button
                key={p.key} type="button" onClick={() => select(p.key as ExecutionPolicy)} disabled={active}
                className={cn(
                  'flex items-center gap-2.5 w-full px-3.5 py-2 text-left transition-colors duration-100',
                  active ? 'cursor-default font-medium' : 'cursor-pointer hover:bg-[var(--surface-muted)] text-[var(--text-muted)]',
                )}
                style={active ? { background: `${p.color}1A`, color: 'var(--text)' } : undefined}
              >
                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: p.color, opacity: active ? 1 : 0.6 }} />
                <span className="flex-1 min-w-0 text-xs">
                  <span className="block">{p.label}</span>
                  <span className="text-[10px] text-[var(--text-faint)]">{p.desc}</span>
                </span>
                {active && <span className="text-[10px] shrink-0" style={{ color: p.color }}>✓</span>}
              </button>
            );
          })}
          {/* gradient */}
          <div className="px-3.5 py-2 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="flex items-center gap-2">
              <span className="text-[9px] text-[var(--text-faint)]">低自主</span>
              <div className="flex-1 h-1 rounded-full" style={{ background: 'linear-gradient(to right, #a855f7, #9ca3af, #3b82f6, #f59e0b)' }} />
              <span className="text-[9px] text-[var(--text-faint)]">高自主</span>
            </div>
          </div>
        </div>
      </div>

      {/* ── Bypass dialog ── */}
      {bypassConfirm && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)' }} onClick={() => setBypassConfirm(false)}>
          <div className="rounded-2xl w-[340px] max-w-[90vw] overflow-hidden" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }} onClick={e => e.stopPropagation()}>
            <div className="px-5 py-4">
              <h3 className="text-[15px] font-semibold flex items-center gap-2" style={{ color: '#f59e0b' }}>⚠ 开启绕过权限？</h3>
              <p className="text-xs text-[var(--text-muted)] mt-2">Agent 将获得完全自主权：</p>
              <ul className="mt-2 space-y-1.5 text-xs text-[var(--text-muted)]">
                {['无需确认直接修改文件','自由执行 Shell 命令','跳过所有审批弹窗'].map(s => (
                  <li key={s} className="flex items-center gap-2"><span style={{ color:'#f59e0b' }}>✓</span>{s}</li>
                ))}
              </ul>
              <p className="text-[10px] text-[var(--text-faint)] mt-3">仅在你完全信任当前任务时启用。</p>
            </div>
            <div className="flex gap-2 px-5 py-3 justify-end" style={{ borderTop:'1px solid var(--border-subtle)' }}>
              <button onClick={() => setBypassConfirm(false)} className="px-4 py-1.5 rounded-lg text-xs font-medium hover:bg-[var(--surface-muted)]" style={{ color:'var(--text-muted)' }}>取消</button>
              <button onClick={confirmBypass} className="px-4 py-1.5 rounded-lg text-xs font-semibold text-white" style={{ background:'#f59e0b' }}>启用</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Toast ── */}
      <div className={cn('fixed bottom-24 left-1/2 -translate-x-1/2 z-[150] px-4 py-2 rounded-full text-[11px] font-medium whitespace-nowrap transition-all duration-200', toast ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2 pointer-events-none')} style={{ background:'var(--surface)', border:'1px solid var(--border)', boxShadow:'0 4px 20px rgba(0,0,0,0.12)', color:'var(--text)' }}>{toast}</div>
    </>
  );
}
