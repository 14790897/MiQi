import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';

interface ThinkBlockProps {
  /** The model's chain-of-thought text (markdown). */
  reasoning: string;
  /** When true the block starts expanded (e.g. live streaming). */
  defaultOpen?: boolean;
  /** Optional header override; defaults to "已深度思考". */
  header?: string;
  children?: ReactNode;
  /** Elapsed seconds for the "· X 秒" label (0 = omit). */
  elapsedSeconds?: number;
  /** Streaming state: adds a subtle pulse and defaults the label to 思考中…. */
  live?: boolean;
}

/**
 * Plain-text thinking block: no background, no border, no box. Just a quiet
 * colored header line and the reasoning body, with a smooth fold animation.
 */
export function ThinkBlock({
  reasoning,
  defaultOpen = false,
  header,
  children,
  elapsedSeconds,
  live = false,
}: ThinkBlockProps) {
  const [open, setOpen] = useState(defaultOpen);
  const wasLiveRef = useRef(live);
  const collapseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (wasLiveRef.current && !live && open) {
      collapseTimerRef.current = setTimeout(() => setOpen(false), 700);
      return () => {
        if (collapseTimerRef.current) clearTimeout(collapseTimerRef.current);
      };
    }
    wasLiveRef.current = live;
  }, [live, open]);

  const toggle = () => {
    if (collapseTimerRef.current) {
      clearTimeout(collapseTimerRef.current);
      collapseTimerRef.current = null;
    }
    setOpen((v) => !v);
  };

  if (!reasoning && !children) return null;

  const label =
    header ??
    (live
      ? '思考中…'
      : elapsedSeconds
        ? `已深度思考 · ${elapsedSeconds} 秒`
        : '已深度思考');

  return (
    <div className="my-0.5 min-w-0">
      <button
        type="button"
        onClick={toggle}
        className="flex items-center gap-1 py-0.5 pl-0.5 text-xs cursor-pointer select-none transition-opacity hover:opacity-75"
        style={{ color: 'var(--text-muted)' }}
        aria-expanded={open}
      >
        <span
          className={live ? 'text-[13px] leading-none animate-pulse' : 'text-[13px] leading-none'}
        >
          🧠
        </span>
        <span>{label}</span>
        <ChevronDown
          size={11}
          className="shrink-0 transition-transform opacity-60"
          style={{ transform: open ? 'none' : 'rotate(-90deg)' }}
        />
      </button>
      <div
        className="grid transition-[grid-template-rows] duration-300 ease-out"
        style={{ gridTemplateRows: open ? '1fr' : '0fr' }}
      >
        <div className="min-h-0 overflow-hidden">
          <div
            className="pl-0.5 text-xs leading-relaxed"
            style={{ color: 'var(--text-muted)' }}
          >
            {children ?? (
              <pre className="whitespace-pre-wrap break-words font-sans">{reasoning}</pre>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
