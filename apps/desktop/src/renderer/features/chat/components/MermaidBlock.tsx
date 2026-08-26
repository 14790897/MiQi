import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Copy, X } from 'lucide-react';

/**
 * Mermaid 流程图渲染（issue #671）。
 * 核心逻辑对齐 Hermes Desktop 的 mermaid-embed（apps/desktop/src/components/
 * assistant-ui/embeds/mermaid-embed.tsx）：
 * - streaming 期间不渲染（流式输出的部分语法必然解析失败），显示源码；
 * - 首次使用/主题切换才 initialize（模块级缓存）；
 * - securityLevel: 'strict' 安全渲染；失败降级为源码；
 * - SVG 尺寸规范化（% 宽度 → viewBox 像素，防止缩放容器塌陷）；
 * - 点击放大查看 + 复制为 PNG。
 * UI 样式保持 MiQroForge 自己的风格。
 */

let lastTheme: 'dark' | 'default' | null = null;
let mermaidPromise: Promise<typeof import('mermaid')> | null = null;

function loadMermaid() {
  if (!mermaidPromise) mermaidPromise = import('mermaid');
  return mermaidPromise;
}

function detectDark(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const t = localStorage.getItem('miqi-theme');
    if (t === 'dark') return true;
    if (t === 'light') return false;
  } catch {
    /* noop */
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function useIsDark(): boolean {
  const [dark, setDark] = useState(detectDark);
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const update = () => setDark(detectDark());
    update();
    mq.addEventListener('change', update);
    window.addEventListener('storage', update);
    return () => {
      mq.removeEventListener('change', update);
      window.removeEventListener('storage', update);
    };
  }, []);
  return dark;
}

// ── SVG 工具（逻辑照抄 Hermes lib/svg-image.ts）──────────────────────────
// Mermaid 输出 width="100%" + viewBox；百分比不是固有尺寸，缩放容器会塌陷。
// 用 viewBox 像素替换百分比宽高；无百分比时原样返回。
function normalizeSvgSize(svg: string): string {
  const el = new DOMParser().parseFromString(svg, 'image/svg+xml').documentElement;
  if (el.tagName !== 'svg') return svg;
  const width = el.getAttribute('width');
  const height = el.getAttribute('height');
  const widthPct = Boolean(width?.trim().endsWith('%'));
  const heightPct = Boolean(height?.trim().endsWith('%'));
  if (!widthPct && !heightPct) return svg;
  const [, , vbW, vbH] = (el.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
  if (!(vbW > 0 && vbH > 0)) return svg;
  if (widthPct) el.setAttribute('width', String(vbW));
  if (heightPct || (widthPct && !height)) el.setAttribute('height', String(vbH));
  return new XMLSerializer().serializeToString(el);
}

function svgSize(svg: string): { height: number; width: number } {
  const el = new DOMParser().parseFromString(svg, 'image/svg+xml').documentElement;
  const w = Number.parseFloat(el.getAttribute('width') || '');
  const h = Number.parseFloat(el.getAttribute('height') || '');
  if (Number.isFinite(w) && Number.isFinite(h) && w > 0 && h > 0) return { height: h, width: w };
  const [, , vbW, vbH] = (el.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
  return vbW > 0 && vbH > 0 ? { height: vbH, width: vbW } : { height: 600, width: 800 };
}

async function copySvgAsPng(svg: string): Promise<boolean> {
  try {
    const { height, width } = svgSize(svg);
    const blob = await new Promise<Blob>((resolve, reject) => {
      const image = new Image();
      image.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(width * 2));
        canvas.height = Math.max(1, Math.round(height * 2));
        const ctx = canvas.getContext('2d');
        if (!ctx) return reject(new Error('no 2d context'));
        ctx.scale(2, 2);
        ctx.drawImage(image, 0, 0, width, height);
        canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('toBlob failed'))), 'image/png');
      };
      image.onerror = () => reject(new Error('svg load failed'));
      image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
    });
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
    return true;
  } catch {
    try {
      await navigator.clipboard.writeText(svg);
      return true;
    } catch {
      return false;
    }
  }
}

// ── 源码展示（流式中/加载中 muted；解析失败正常色）──────────────────────
function SourcePreview({ code, muted }: { code: string; muted?: boolean }) {
  return (
    <pre
      className="my-2 rounded-lg overflow-x-auto max-w-full px-3 py-2 text-xs font-mono leading-relaxed whitespace-pre-wrap break-words"
      style={{
        background: 'rgba(0,0,0,0.06)',
        color: muted ? 'var(--text-faint)' : 'var(--text-muted)',
      }}
    >
      {code}
    </pre>
  );
}

interface MermaidBlockProps {
  code: string;
  /** True while the surrounding message is still streaming —— 流式期间不渲染 */
  streaming?: boolean;
  /** 渲染失败时的降级内容（原代码块） */
  fallback: ReactNode;
}

export function MermaidBlock({ code, streaming, fallback }: MermaidBlockProps) {
  const isDark = useIsDark();
  const [svg, setSvg] = useState('');
  const [failed, setFailed] = useState(false);
  const [zoom, setZoom] = useState(false);
  const [copiedPng, setCopiedPng] = useState(false);

  // Escape 关闭放大视图
  useEffect(() => {
    if (!zoom) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setZoom(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [zoom]);

  useEffect(() => {
    if (streaming) return;
    let cancelled = false;
    setFailed(false);
    setSvg('');
    void (async () => {
      try {
        const mod = await loadMermaid();
        const theme = isDark ? 'dark' : 'default';
        if (theme !== lastTheme) {
          mod.default.initialize({ fontFamily: 'inherit', securityLevel: 'strict', startOnLoad: false, theme });
          lastTheme = theme;
        }
        const id = `mmd-${Math.random().toString(36).slice(2)}`;
        const result = await mod.default.render(id, code);
        if (!cancelled) setSvg(normalizeSvgSize(result.svg));
      } catch {
        if (!cancelled) {
          setFailed(true);
          setSvg('');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, isDark, streaming]);

  const svgInline = useMemo(
    () => (svg ? <div dangerouslySetInnerHTML={{ __html: svg }} /> : null),
    [svg]
  );

  if (streaming) return <SourcePreview code={code} muted />;
  if (failed) return <>{fallback}</>;
  if (!svg) return <SourcePreview code={code} muted />;

  return (
    <>
      {/* 内联渲染：限高，居中，可点击放大。
          注意：mermaid svg 固有像素宽度会撑开父容器导致 max-w-full 失效，
          必须强制 w-full 让 svg 收缩到卡片宽度（Hermes 气泡有固定 max-width
          所以没有这个问题，我们的消息容器没有） */}
      <div
        className="my-2 overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface)] p-3 cursor-zoom-in select-none max-w-full"
        style={{ boxShadow: '0 1px 6px rgba(0,0,0,0.06)' }}
        onClick={() => setZoom(true)}
        title="点击放大"
      >
        <div className="[&_svg]:mx-auto [&_svg]:w-full [&_svg]:h-auto [&_svg]:max-h-[33vh] [&_svg]:pointer-events-none">
          {svgInline}
        </div>
      </div>

      {/* 放大查看：全屏 overlay + 复制 PNG */}
      {zoom && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-6"
          onClick={() => setZoom(false)}
        >
          <div
            className="relative max-w-[90vw] max-h-[88vh] overflow-auto rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-xl"
            style={{ border: '1px solid var(--border-subtle)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-end gap-1 mb-2 sticky top-0 bg-[var(--surface-elevated)]">
              <button
                onClick={async () => {
                  const ok = await copySvgAsPng(svg);
                  setCopiedPng(ok);
                  setTimeout(() => setCopiedPng(false), 1500);
                }}
                className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-muted)] transition-colors"
                title="复制为 PNG"
              >
                <Copy size={13} />
                {copiedPng ? '已复制' : '复制 PNG'}
              </button>
              <button
                onClick={() => setZoom(false)}
                className="p-1.5 rounded-md text-[var(--text-faint)] hover:text-[var(--text)] hover:bg-[var(--surface-muted)] transition-colors"
                title="关闭"
              >
                <X size={15} />
              </button>
            </div>
            <div className="[&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-h-[75vh] [&_svg]:max-w-[82vw] [&_svg]:pointer-events-none">
              {svgInline}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
