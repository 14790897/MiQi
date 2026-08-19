import React, { useState, useRef, useEffect } from 'react';

export type ReasoningMode = 'fast' | 'think';

interface ReasoningModeSwitchProps {
  mode: ReasoningMode;
  onChange: (mode: ReasoningMode) => void;
}

const ITEMS: { key: ReasoningMode; label: string; desc: string; color: string; dot: string }[] = [
  { key: 'fast', label: '极速回答', desc: '30 秒内作答', color: '#fbbf24', dot: '#fbbf24' },
  { key: 'think', label: '深度研究', desc: 'AI 自由发挥', color: '#a855f7', dot: '#a855f7' },
];
const LABELS: Record<string, string> = Object.fromEntries(ITEMS.map((i) => [i.key, i.label]));

/** 极速回答 / 深度研究 菜单选择器（issue #680）。
 * 交互与 ExecutionPolicySelector 一致：按钮显示当前模式，点击弹出两个选项。 */
export const ReasoningModeSwitch: React.FC<ReasoningModeSwitchProps> = ({ mode, onChange }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const cur = ITEMS.find((i) => i.key === mode)!;

  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={[
          'flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium transition-colors',
          'outline-none focus-visible:ring-0 select-none cursor-pointer',
        ].join(' ')}
        style={{ color: cur.color }}
        title="回答模式"
        aria-label="回答模式"
        aria-expanded={open}
      >
        <span
          aria-hidden
          className="inline-block w-1.5 h-1.5 rounded-full"
          style={{ background: cur.dot }}
        />
        <span>{cur.label}</span>
        <span aria-hidden className="text-[9px] opacity-60">▾</span>
      </button>

      {open && (
        <div
          className="absolute bottom-full left-0 mb-1 min-w-[150px] rounded-lg overflow-hidden z-50"
          style={{ background: 'var(--surface2)', border: '1px solid var(--border)', boxShadow: '0 8px 24px rgba(0,0,0,.4)' }}
        >
          {ITEMS.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => {
                onChange(item.key);
                setOpen(false);
              }}
              className={[
                'flex items-center gap-2 w-full text-left px-3 py-2 text-xs transition-colors cursor-pointer',
                'outline-none focus-visible:ring-0',
                item.key === mode ? 'bg-[var(--surface)]' : 'hover:bg-[var(--surface)]',
              ].join(' ')}
              style={{ color: item.key === mode ? item.color : 'var(--text-muted)' }}
            >
              <span
                aria-hidden
                className="inline-block w-1.5 h-1.5 rounded-full shrink-0"
                style={{ background: item.dot, opacity: item.key === mode ? 1 : 0.35 }}
              />
              <span className="font-medium">{item.label}</span>
              <span className="text-[10px] text-[var(--text-faint)]">{item.desc}</span>
              {item.key === mode && <span className="ml-auto text-[10px]">✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
