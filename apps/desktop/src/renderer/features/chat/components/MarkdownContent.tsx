import { useState, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '../../../lib/utils';
import { MermaidBlock } from './MermaidBlock';

/** Strip <think>...</think> reasoning blocks before rendering. */
function stripThinkBlocks(text: string): string {
  let result = text.replace(/<\/?think>/gi, '');
  return result.trim();
}

export function MarkdownContent({ content, streaming }: { content: string; streaming?: boolean }) {
  const [copiedCode, setCopiedCode] = useState<string | null>(null);
  const displayContent = stripThinkBlocks(content);

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
      img: ({ src, alt }: any) => (
        <img src={src} alt={alt ?? ''} className='max-w-full h-auto rounded-lg my-2' />
      ),
      a: ({ href, children }: any) => (
        <a href={href} className="underline cursor-pointer break-words" style={{ color: 'var(--accent)' }}
           onClick={(e) => { e.preventDefault(); if (href) window.open(href, '_blank'); }}>{children}</a>
      ),
      table: ({ children }: any) => <div className="overflow-x-auto my-2"><table className="text-xs w-full border-collapse">{children}</table></div>,
      th: ({ children }: any) => <th className="border px-2 py-1.5 text-left font-medium" style={{ borderColor: 'var(--border)', background: 'var(--surface-muted)' }}>{children}</th>,
      td: ({ children }: any) => <td className="border px-2 py-1.5" style={{ borderColor: 'var(--border-subtle)' }}>{children}</td>,
      pre: ({ children }: any) => <pre className="relative group my-2 rounded-lg overflow-x-auto max-w-full" style={{ background: 'rgba(0,0,0,0.06)' }}>{children}</pre>,
      code: ({ className, children, ...props }: any) => {
        const codeStr = String(children);
        // #671：mermaid 代码块 → 流程图组件（streaming 时占位符，final 后渲染）
        const lang = /language-(\w+)/.exec(className || '')?.[1];
        if (lang === 'mermaid') {
          return <MermaidBlock source={codeStr.replace(/\n$/, '')} streaming={streaming} />;
        }
        if (codeStr.endsWith('\n')) {
          const code = codeStr.replace(/\n$/, '');
          return (
            <code className={cn('block text-xs font-mono p-3', className)} {...props}>
              <button
                onClick={() => handleCopyCode(code)}
                className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity rounded px-1.5 py-0.5 text-size-2xs leading-none"
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
    <div className="min-w-0 break-words" style={{ overflowWrap: 'anywhere' }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {displayContent}
      </ReactMarkdown>
    </div>
  );
}
