import { useState, type ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';

interface ThinkBlockProps {
  /** The model's chain-of-thought text (markdown). */
  reasoning: string;
  /** When true the block starts expanded (e.g. live streaming). */
  defaultOpen?: boolean;
  /** Optional header override; defaults to "已深度思考". */
  header?: string;
  children?: ReactNode;
  /** Elapsed seconds for the "用时 X 秒" label (0 = omit). */
  elapsedSeconds?: number;
}

/**
 * DeepSeek style thinking block — a rounded, muted pill toggle
 * ("已深度思考（用时 X 秒）") with a left-rail reasoning body.
 */
export function ThinkBlock({
  reasoning,
  defaultOpen = false,
  header,
  children,
  elapsedSeconds,
}: ThinkBlockProps) {
  const [open, setOpen] = useState(defaultOpen);
  if (!reasoning && !children) return null;

  const label =
    header ?? (elapsedSeconds ? `已深度思考（用时 ${elapsedSeconds} 秒）` : '已深度思考');

  return (
    <div className="my-1">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium cursor-pointer select-none transition-colors hover:opacity-80"
        style={{
          background: 'var(--surface-muted)',
          color: 'var(--text)',
          border: '1px solid var(--border-subtle)',
        }}
        aria-expanded={open}
      >
        <ChevronDown
          size={14}
          className="shrink-0 transition-transform"
          style={{ transform: open ? 'none' : 'rotate(-90deg)' }}
        />
        <span>{label}</span>
      </button>
      {open && (
        <div
          className="mt-2 pl-3 pr-1 py-1 text-xs leading-relaxed border-l-2"
          style={{ color: 'var(--text-muted)', borderColor: 'var(--border)' }}
        >
          {children ?? <pre className="whitespace-pre-wrap break-words font-sans">{reasoning}</pre>}
        </div>
      )}
    </div>
  );
}
