import { useEffect, useRef, useState, type ReactNode } from 'react';

/**
 * Mermaid 流程图渲染（issue #671 可视化流程图）。
 * 懒加载 mermaid（不增加首屏 bundle）；渲染失败时降级为原始代码块，
 * 不影响正文阅读。
 */
interface MermaidBlockProps {
  code: string;
  /** 渲染失败时的降级内容（通常是原代码块） */
  fallback: ReactNode;
}

let mermaidPromise: Promise<typeof import('mermaid')> | null = null;

function loadMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid');
  }
  return mermaidPromise;
}

export function MermaidBlock({ code, fallback }: MermaidBlockProps) {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const idRef = useRef(`mermaid-${Math.random().toString(36).slice(2, 10)}`);

  useEffect(() => {
    let alive = true;
    setSvg(null);
    setFailed(false);
    (async () => {
      try {
        const mod = await loadMermaid();
        const mermaid = mod.default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: 'strict',
          theme: 'default',
        });
        const { svg: rendered } = await mermaid.render(idRef.current, code);
        if (alive) setSvg(rendered);
      } catch {
        if (alive) setFailed(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, [code]);

  if (failed) return <>{fallback}</>;
  if (!svg) {
    return (
      <div className="my-2 text-xs text-[var(--text-faint)] select-none">
        正在渲染流程图…
      </div>
    );
  }
  return (
    <div
      className="my-2 overflow-x-auto"
      // mermaid.render 输出为 sanitized SVG（securityLevel: 'strict'），
      // 此处直接注入渲染结果
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
