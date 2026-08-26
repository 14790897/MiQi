import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Check, Copy, Maximize, RefreshCw, X, ZoomIn, ZoomOut } from 'lucide-react';
import { useZoomPan } from '../../../hooks/useZoomPan';

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
        className="group/zoomable relative my-2 overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface)] p-3 cursor-zoom-in select-none max-w-full"
        style={{ boxShadow: '0 1px 6px rgba(0,0,0,0.06)' }}
        onClick={() => setZoom(true)}
        title="点击放大"
      >
        <div className="[&_svg]:mx-auto [&_svg]:w-full [&_svg]:h-auto [&_svg]:max-h-[33vh] [&_svg]:pointer-events-none">
          {svgInline}
        </div>
        {/* 悬停时右上角展开提示（对齐 Hermes Zoomable 的 affordance） */}
        <span
          aria-hidden
          className="pointer-events-none absolute right-2 top-2 grid size-7 place-items-center rounded-full border border-[var(--border)] bg-[var(--surface)]/80 text-[var(--text-muted)] opacity-0 shadow-sm transition-opacity group-hover/zoomable:opacity-100"
        >
          <Maximize size={14} />
        </span>
      </div>

      {/* 放大查看：全屏 overlay + 缩放/平移 + 复制 PNG */}
      {zoom && (
        <ZoomPanViewer
          onCopy={() => copySvgAsPng(svg)}
          onClose={() => setZoom(false)}
          svg={svg}
        />
      )}
    </>
  );
}

function ZoomPanViewer({ svg, onClose, onCopy }: { svg: string; onClose: () => void; onCopy: () => Promise<boolean> }) {
  const { panning, reset, stageProps, style, zoomIn, zoomOut } = useZoomPan();
  const [copiedPng, setCopiedPng] = useState(false);

  // Escape 关闭 + 打开时重置缩放
  useEffect(() => {
    reset();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-6"
      onClick={onClose}
    >
      <div
        className="relative h-[85vh] w-[90vw] max-w-[90vw] overflow-hidden rounded-2xl bg-[var(--surface-elevated)] shadow-xl"
        style={{ border: '1px solid var(--border-subtle)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className={`relative flex-1 h-full touch-none select-none overflow-hidden ${panning ? 'cursor-grabbing' : 'cursor-grab'}`}
          {...stageProps}
        >
          <div className="absolute inset-0 grid place-items-center">
            <div className="origin-center" style={style}>
              <div className="[&_svg]:h-auto [&_svg]:max-h-[75vh] [&_svg]:max-w-[82vw] [&_svg]:pointer-events-none">
                <div dangerouslySetInnerHTML={{ __html: svg }} />
              </div>
            </div>
          </div>
        </div>
        {/* 底部工具栏（对齐 Hermes ZoomPanViewer Toolbar） */}
        <div
          className="absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-1 rounded-full border border-[var(--border)] bg-[var(--surface)]/90 p-1 shadow-sm"
          style={{ backdropFilter: 'blur(8px)' }}
        >
          <ToolbarButton label="缩小" onClick={zoomOut}><ZoomOut size={15} /></ToolbarButton>
          <ToolbarButton label="重置" onClick={reset}><RefreshCw size={15} /></ToolbarButton>
          <ToolbarButton label="放大" onClick={zoomIn}><ZoomIn size={15} /></ToolbarButton>
          <Divider />
          <ToolbarButton
            label={copiedPng ? '已复制' : '复制 PNG'}
            onClick={async () => {
              const ok = await onCopy();
              if (ok) {
                setCopiedPng(true);
                setTimeout(() => setCopiedPng(false), 1500);
              }
            }}
          >
            {copiedPng ? <Check size={15} /> : <Copy size={15} />}
          </ToolbarButton>
          <Divider />
          <ToolbarButton label="关闭" onClick={onClose}><X size={15} /></ToolbarButton>
        </div>
      </div>
    </div>
  );
}

function Divider() {
  return <span className="mx-0.5 h-5 w-px" style={{ background: 'var(--border-subtle)' }} />;
}

function ToolbarButton({ children, label, onClick }: { children: ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      aria-label={label}
      title={label}
      className="grid size-8 place-items-center rounded-full text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-muted)] hover:text-[var(--text)]"
      onClick={onClick}
      type="button"
    >
      {children}
    </button>
  );
}
