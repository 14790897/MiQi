import { useState, useRef, useEffect, useCallback } from 'react';
import { cn } from '../lib/utils';

export type ExecutionPolicy = 'plan' | 'manual' | 'accept_edits' | 'bypass';

type P = { key: ExecutionPolicy; label: string; desc: string; color: string };
const ITEMS: P[] = [
  { key: 'plan',         label: '规划',      desc: '只规划不修改',                            color: '#a855f7' },
  { key: 'manual',       label: '手动',      desc: '每次修改需确认',                          color: '#9ca3af' },
  { key: 'accept_edits', label: '接受编辑',  desc: '自动修改文件，危险操作仍需确认',          color: '#3b82f6' },
  { key: 'bypass',       label: '绕过权限',  desc: '完全自主——跳过所有审批检查',              color: '#f59e0b' },
];
const LABELS: Record<string, string> = Object.fromEntries(ITEMS.map(p => [p.key, p.label]));

interface Props { policy: ExecutionPolicy; onChange: (p: ExecutionPolicy) => void; disabled?: boolean }

export function ExecutionPolicySelector({ policy, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const [bypass, setBypass] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const t = useRef(0);
  const cur = ITEMS.find(i => i.key === policy)!;

  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [open]);

  const toastFn = useCallback((msg: string) => {
    setToast(msg); if (t.current) clearTimeout(t.current);
    t.current = window.setTimeout(() => setToast(null), 2000);
  }, []);
  useEffect(() => () => clearTimeout(t.current), []);

  const pick = useCallback((p: ExecutionPolicy) => {
    if (p === 'bypass') { setBypass(true); setOpen(false); return; }
    onChange(p); setOpen(false); toastFn(`✓ ${LABELS[p]} 已启用`);
  }, [onChange, toastFn]);

  return (
    <>
      <div ref={ref} style={{ position: 'relative', flexShrink: 0 }}>
        <button
          type="button" onClick={() => setOpen(!open)} disabled={disabled}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '4px 10px', borderRadius: 7,
            fontSize: 11, fontWeight: 600, cursor: 'pointer',
            border: `1px solid ${policy === 'bypass' ? cur.color : 'var(--border)'}`,
            background: 'var(--surface)', color: 'var(--text)',
            transition: 'all .15s',
          }}
          onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-muted)'}
          onMouseLeave={e => e.currentTarget.style.background = 'var(--surface)'}
        >
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: cur.color }} />
          <span>{cur.label}</span>
          <span style={{ fontSize: 8, opacity: .3 }}>▾</span>
          {cur.key === 'bypass' && <span style={{ fontSize: 13 }}>⚠</span>}
        </button>

        <div
          className={cn(
            'absolute left-0 bottom-full mb-1 z-50 overflow-hidden',
            'transition-all duration-150',
            open ? 'opacity-100 scale-100 translate-y-0' : 'opacity-0 scale-95 translate-y-1 pointer-events-none',
          )}
          style={{
            minWidth: 220, background: 'var(--surface)',
            border: '1px solid var(--border)', borderRadius: 12,
            boxShadow: '0 8px 30px rgba(0,0,0,0.12)',
          }}
        >
          <div style={{ padding: '8px 14px 4px', fontSize: 10, color: 'var(--text-faint)', letterSpacing: .5, textTransform: 'uppercase' }}>
            执行策略
          </div>
          {ITEMS.map(p => {
            const active = policy === p.key;
            return (
              <button
                key={p.key} type="button" onClick={() => pick(p.key)} disabled={active}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '9px 14px', fontSize: 12, cursor: active ? 'default' : 'pointer',
                  width: '100%', textAlign: 'left', transition: 'background .12s',
                  color: active ? 'var(--text)' : 'var(--text-muted)',
                  fontWeight: active ? 500 : 400,
                  background: active ? `${p.color}1A` : 'transparent',
                }}
                onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--surface-muted)'; }}
                onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent'; }}
              >
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: p.color, opacity: active ? 1 : .6, flexShrink: 0 }} />
                <span style={{ flex: 1 }}>
                  <span style={{ display: 'block' }}>{p.label}</span>
                  <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>{p.desc}</span>
                </span>
                {active && <span style={{ fontSize: 10, color: p.color, flexShrink: 0 }}>✓</span>}
              </button>
            );
          })}
          <div style={{ padding: '8px 14px', borderTop: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 9, color: 'var(--text-faint)' }}>低自主</span>
              <div style={{ flex: 1, height: 4, borderRadius: 2, background: 'linear-gradient(to right, #a855f7, #9ca3af, #3b82f6, #f59e0b)' }} />
              <span style={{ fontSize: 9, color: 'var(--text-faint)' }}>高自主</span>
            </div>
          </div>
        </div>
      </div>

      {bypass && (
        <div onClick={() => setBypass(false)} style={{ position: 'fixed', inset: 0, zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.4)' }}>
          <div onClick={e => e.stopPropagation()} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16, padding: 24, maxWidth: 360, width: '90%' }}>
            <h3 style={{ fontSize: 15, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8, color: '#f59e0b' }}>⚠ 开启绕过权限？</h3>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}>Agent 将获得完全自主权：</p>
            <ul style={{ margin: '12px 0 20px', fontSize: 12, color: 'var(--text-muted)', lineHeight: 2, listStyle: 'none' }}>
              {['无需确认直接修改文件','自由执行 Shell 命令','跳过所有审批弹窗'].map(s => (
                <li key={s}><span style={{ color: '#f59e0b' }}>✓ </span>{s}</li>
              ))}
            </ul>
            <p style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 16 }}>仅在你完全信任当前任务时启用。</p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button onClick={() => setBypass(false)} style={{ padding: '7px 16px', borderRadius: 8, fontSize: 12, fontWeight: 500, cursor: 'pointer', border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)' }}>取消</button>
              <button onClick={() => { onChange('bypass'); setBypass(false); toastFn('✓ 绕过权限 已启用'); }} style={{ padding: '7px 16px', borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: 'pointer', border: 'none', background: '#f59e0b', color: '#fff' }}>启用</button>
            </div>
          </div>
        </div>
      )}

      <div className={cn('fixed bottom-24 left-1/2 -translate-x-1/2 z-[150] px-4 py-2 rounded-full text-[11px] font-medium whitespace-nowrap transition-all duration-200', toast ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2 pointer-events-none')} style={{ background: 'var(--surface)', border: '1px solid var(--border)', boxShadow: '0 4px 20px rgba(0,0,0,0.12)', color: 'var(--text)' }}>{toast}</div>
    </>
  );
}
