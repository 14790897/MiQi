/**
 * MermaidBlock — 流程图渲染（issue #671 决策：final 后渲染，不污染流式）。
 *
 * - streaming=true（流式中）：显示占位符，绝不渲染残缺语法
 * - streaming=false（消息完成/历史重载）：mermaid.render() → SVG
 * - 失败：降级为原始代码块 + "⚠ 流程图渲染失败"（不影响正文）
 * - 缓存：source → SVG（历史重载命中缓存不重渲染）
 */
import { useEffect, useRef, useState } from 'react';

const svgCache = new Map<string, string>();

type Status = 'pending' | 'rendering' | 'ready' | 'error';

export function MermaidBlock({ source, streaming }: { source: string; streaming?: boolean }) {
  const [status, setStatus] = useState<Status>(streaming ? 'pending' : 'ready');
  const [svg, setSvg] = useState<string>(() => svgCache.get(source) ?? '');
  const [error, setError] = useState<string>('');
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (streaming) {
      setStatus('pending');
      return;
    }
    // 缓存命中
    const cached = svgCache.get(source);
    if (cached) {
      setSvg(cached);
      setStatus('ready');
      return;
    }
    let cancelled = false;
    setStatus('rendering');
    (async () => {
      try {
        const mermaid = (await import('mermaid')).default;
        mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' });
        const id = `mermaid-${Math.random().toString(36).slice(2, 10)}`;
        const { svg: rendered } = await mermaid.render(id, source);
        if (cancelled || !mountedRef.current) return;
        svgCache.set(source, rendered);
        setSvg(rendered);
        setStatus('ready');
      } catch (e) {
        if (cancelled || !mountedRef.current) return;
        setError(String(e));
        setStatus('error');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [source, streaming]);

  // 流式中 / 待渲染 → 占位符
  if (status === 'pending' || status === 'rendering') {
    return (
      <div
        className="my-2 rounded-lg px-4 py-3 text-[12.5px] flex items-center gap-2"
        style={{ background: 'var(--surface-muted)', border: '1px dashed var(--border)', color: 'var(--text-faint)' }}
      >
        <span style={{ animation: 'turnPulse 1.2s ease-in-out infinite' }}>📊</span>
        流程图生成中…
      </div>
    );
  }

  // 失败 → 降级代码块（保留原文可读）
  if (status === 'error') {
    return (
      <div className="my-2 rounded-lg overflow-hidden" style={{ border: '1px solid var(--border-subtle)' }}>
        <div className="px-3 py-1.5 text-[11.5px] flex items-center gap-1.5" style={{ background: 'var(--warning-bg)', color: 'var(--approval-warning)' }}>
          <span>⚠</span> 流程图渲染失败，已显示原始代码
        </div>
        <pre className="m-0 p-3 text-xs font-mono overflow-x-auto" style={{ background: 'rgba(0,0,0,0.06)' }}>{source}</pre>
      </div>
    );
  }

  // 成功 → SVG
  return (
    <div
      className="my-2 rounded-lg overflow-x-auto"
      style={{ background: 'var(--surface)', border: '1px solid var(--border-subtle)' }}
      // mermaid 输出的 SVG 是受控字符串；securityLevel: strict 下无脚本注入
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
