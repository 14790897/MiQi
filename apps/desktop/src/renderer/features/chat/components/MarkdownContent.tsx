import { useState, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChevronRight } from 'lucide-react';
import { cn } from '../../../lib/utils';
import { splitThink } from './splitThink';

function ThinkBlock({ value }: { value: string }) {
  const [open, setOpen] = useState(false);
  const trimmed = value.trim();
  if (!trimmed) return null;
  return (
    <div
      className="my-2 rounded-lg border text-xs"
      style={{ borderColor: 'var(--border-subtle)', background: 'var(--surface-muted)' }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 px-3 py-1.5 text-left"
        style={{ color: 'var(--text-muted)' }}
        aria-expanded={open}
      >
        <ChevronRight
          size={12}
          className={cn('shrink-0 transition-transform', open && 'rotate-90')}
        />
        <span className="font-medium">{open ? '思考（已展开）' : '思考'}</span>
      </button>
      {open && (
        <div
          className="px-3 pb-2.5 pt-0 leading-relaxed whitespace-pre-wrap"
          style={{ color: 'var(--text-muted)' }}
        >
          {trimmed}
        </div>
      )}
    </div>
  );
}

export function MarkdownContent({ content }: { content: string }) {
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  const segments = useMemo(() => splitThink(content), [content]);
  // Only the non-think text needs markdown; think blocks render as plain
  // collapsible disclosure. Skip empty text segments so we don't emit empty
  // markdown wrappers between consecutive think blocks.
  const textSegments = useMemo(
    () => segments.filter((s) => s.type === 'text' && s.value.length > 0),
    [segments]
  );
  const hasThink = useMemo(
    () => segments.some((s) => s.type === 'think' && s.value.trim().length > 0),
    [segments]
  );

  const handleCopyCode = (code: string) => {
    navigator.clipboard.writeText(code);
    setCopiedCode(code);
    setTimeout(() => setCopiedCode(null), 2000);
  };

  const components = useMemo(
    () => ({
      p: ({ children }: any) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
      h1: ({ children }: any) => <h1 className="text-base font-bold mt-3 mb-1.5 first:mt-0">{children}</h1>,
      h2: ({ children }: any) => <h2 className="text-sm font-bold mt-3 mb-1 first:mt-0">{children}</h2>,
      h3: ({ children }: any) => <h3 className="text-sm font-semibold mt-2 mb-0.5 first:mt-0">{children}</h3>,
      ul: ({ children }: any) => <ul className="list-disc pl-5 my-1.5 space-y-0.5">{children}</ul>,
      ol: ({ children }: any) => <ol className="list-decimal pl-5 my-1.5 space-y-0.5">{children}</ol>,
      li: ({ children }: any) => <li className="leading-relaxed">{children}</li>,
      blockquote: ({ children }: any) => (
        <blockquote className="border-l-2 pl-3 my-2 italic" style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}>{children}</blockquote>
      ),
      strong: ({ children }: any) => <strong className="font-semibold">{children}</strong>,
      em: ({ children }: any) => <em className="italic">{children}</em>,
      hr: () => <hr className="my-3" style={{ borderColor: 'var(--border-subtle)' }} />,
      a: ({ href, children }: any) => (
        <a href={href} className="underline cursor-pointer" style={{ color: 'var(--accent)' }}
           onClick={(e) => { e.preventDefault(); if (href) window.open(href, '_blank'); }}>{children}</a>
      ),
      table: ({ children }: any) => <div className="overflow-x-auto my-2"><table className="text-xs w-full border-collapse">{children}</table></div>,
      th: ({ children }: any) => <th className="border px-2 py-1.5 text-left font-medium" style={{ borderColor: 'var(--border)', background: 'var(--surface-muted)' }}>{children}</th>,
      td: ({ children }: any) => <td className="border px-2 py-1.5" style={{ borderColor: 'var(--border-subtle)' }}>{children}</td>,
      pre: ({ children }: any) => <pre className="relative group my-2 rounded-lg overflow-x-auto" style={{ background: 'rgba(0,0,0,0.06)' }}>{children}</pre>,
      code: ({ className, children, ...props }: any) => {
        const codeStr = String(children);
        if (codeStr.endsWith('\n')) {
          const code = codeStr.replace(/\n$/, '');
          return (
            <code className={cn('block text-xs font-mono p-3', className)} {...props}>
              <button
                onClick={() => handleCopyCode(code)}
                className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity rounded px-1.5 py-0.5 text-[10px] leading-none"
                style={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text-muted)' }}
              >
                {copiedCode === code ? 'Copied' : 'Copy'}
              </button>
              {code}
            </code>
          );
        }
        return <code className="text-xs font-mono px-1.5 py-0.5 rounded" style={{ background: 'rgba(0,0,0,0.08)' }} {...props}>{children}</code>;
      },
    }),
    [copiedCode]
  );

  return (
    <div className="think-rendered">
      {hasThink || textSegments.length > 0 ? (
        segments.map((seg, i) =>
          seg.type === 'think' ? (
            <ThinkBlock key={`think-${i}`} value={seg.value} />
          ) : seg.value.length > 0 ? (
            <ReactMarkdown key={`text-${i}`} remarkPlugins={[remarkGfm]} components={components}>
              {seg.value}
            </ReactMarkdown>
          ) : null
        )
      ) : (
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{content}</ReactMarkdown>
      )}
    </div>
  );
}
