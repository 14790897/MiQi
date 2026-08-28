import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react';
import { Check, Copy, Download, Maximize, RefreshCw, X, ZoomIn, ZoomOut } from 'lucide-react';
import { useZoomPan } from '../../../hooks/useZoomPan';
import { svgSize } from '../../../lib/svgImage';

/**
 * 统一图表容器（mermaid / svg embed 共用，对齐 Hermes mermaid-embed 的轻量嵌入）：
 * - 无卡片边框/背景/阴影——SVG 本身有颜色，透明嵌入消息流更雅（Hermes 式）；
 * - 图居中，尺寸适配：mermaid 大图限高 50vh，svg 原尺寸（超限缩放）；
 * - hover 右上角 Maximize 提示（Hermes Zoomable affordance）；
 * - 点击弹窗预览：缩放/平移/重置 + 复制 PNG + 下载 PNG + 关闭（Escape/遮罩）。
 */
interface DiagramCardProps {
  /** 已消毒的 SVG 字符串 */
  svg: string;
  /** 复制为 PNG 的动作（返回是否成功） */
  onCopy: () => Promise<boolean>;
  /** 下载为 PNG 文件（返回是否成功） */
  onDownload: () => Promise<boolean>;
}

export function DiagramCard({ svg, onCopy, onDownload }: DiagramCardProps) {
  const [zoom, setZoom] = useState(false);

  return (
    <>
      {/* 内联渲染：透明嵌入消息流（Hermes 式，无卡片），hover 显示展开提示。
          键盘可达（CodeRabbit）：role=button + tabIndex + Enter/Space 打开 */}
      <div
        className="group/zoomable relative my-2 w-full max-w-full cursor-zoom-in select-none"
        role="button"
        tabIndex={0}
        aria-label="打开流程图预览"
        onClick={() => setZoom(true)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setZoom(true);
          }
        }}
        title="点击放大"
      >
        <div className="overflow-hidden p-1 [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-h-[50vh] [&_svg]:max-w-full [&_svg]:pointer-events-none">
          <div dangerouslySetInnerHTML={{ __html: svg }} />
        </div>
        {/* 悬停时右上角展开提示（对齐 Hermes Zoomable 的 affordance） */}
        <span
          aria-hidden
          className="pointer-events-none absolute right-2 top-2 grid size-7 place-items-center rounded-full border border-[var(--border)] bg-[var(--surface)]/80 text-[var(--text-muted)] opacity-0 shadow-sm transition-opacity group-hover/zoomable:opacity-100"
        >
          <Maximize size={14} />
        </span>
      </div>

      {/* 放大弹窗预览：缩放/平移 + 复制 PNG + 下载 PNG */}
      {zoom && <ZoomPanViewer svg={svg} onClose={() => setZoom(false)} onCopy={onCopy} onDownload={onDownload} />}
    </>
  );
}

function ZoomPanViewer({ svg, onClose, onCopy, onDownload }: { svg: string; onClose: () => void; onCopy: () => Promise<boolean>; onDownload: () => Promise<boolean> }) {
  // 沉浸式查看器（对齐 YARL）：全屏深色背景，无白框，图 fit 居中，
  // 底部浮动工具栏；双击/滚轮/按钮缩放 + 拖拽平移（带边界 clamp）
  const stageRef = useRef<HTMLDivElement>(null);
  const [viewport, setViewport] = useState({ w: 0, h: 0 });

  // 测量 stage 视口（窗口变化/布局变化时更新）
  useEffect(() => {
    const measure = () => {
      const el = stageRef.current;
      if (!el) return;
      setViewport({ w: el.clientWidth, h: el.clientHeight });
    };
    measure();
    const ro = new ResizeObserver(measure);
    if (stageRef.current) ro.observe(stageRef.current);
    window.addEventListener('resize', measure);
    return () => {
      ro.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, []);

  const { height: sh, width: sw } = svgSize(svg);
  const fitScale = useMemo(() => {
    if (typeof window === 'undefined') return 1;
    const viewW = (viewport.w || window.innerWidth) - 8;
    const viewH = (viewport.h || window.innerHeight) - 88;
    return Math.min(1, viewW / sw, viewH / sh);
  }, [viewport.w, viewport.h, sw, sh]);

  // 内容布局尺寸（transform 前）：svg w-full 撑满 stage 宽，高按比例
  const content = useMemo(() => {
    const cw = viewport.w > 0 ? viewport.w : 800;
    return { w: cw, h: cw * (sh / sw) };
  }, [viewport.w, sw, sh]);

  const { panning, reset, stageProps, style, zoomIn, zoomOut, scale } = useZoomPan(fitScale, viewport, content);
  const [copiedPng, setCopiedPng] = useState(false);
  const [downloaded, setDownloaded] = useState(false);

  // Escape 关闭 + 打开时重置缩放 + 锁背景滚动（防滚动链穿透导致背景滑动）
  useEffect(() => {
    reset();
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener('keydown', onKey);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80" onClick={onClose}>
      {/* stage：无框沉浸区，图 fit 居中，可滚轮缩放/拖拽平移（边界 clamp） */}
      <div
        ref={stageRef}
        className={`absolute inset-0 overflow-hidden touch-none select-none ${panning ? 'cursor-grabbing' : 'cursor-grab'}`}
        onClick={(e) => e.stopPropagation()}
        onPointerDown={(e) => {
          e.stopPropagation();
          stageProps.onPointerDown(e);
        }}
        onPointerMove={stageProps.onPointerMove}
        onPointerUp={stageProps.onPointerUp}
        onPointerLeave={stageProps.onPointerLeave}
        onWheel={stageProps.onWheel}
        onDoubleClick={(e) => {
          e.stopPropagation();
          if (scale > fitScale * 1.1) {
            reset();
          } else {
            zoomIn();
          }
        }}
      >
        <div className="grid h-full w-full place-items-center">
          <div className="origin-center w-full" style={style}>
            <div className="w-full [&_svg]:block [&_svg]:w-full [&_svg]:h-auto [&_svg]:max-w-full [&_svg]:pointer-events-none">
              <div dangerouslySetInnerHTML={{ __html: svg }} />
            </div>
          </div>
        </div>
      </div>

      {/* 顶部浮动标题 + 关闭 */}
      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-center justify-between p-4">
        <span className="rounded-full bg-black/50 px-3 py-1 text-xs text-white/90 backdrop-blur">流程图预览</span>
        <button
          aria-label="关闭"
          title="关闭"
          className="pointer-events-auto grid size-9 place-items-center rounded-full bg-black/50 text-white/90 backdrop-blur transition-colors hover:bg-black/70"
          onClick={onClose}
          type="button"
        >
          <X size={18} />
        </button>
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
          <ToolbarButton
            label={downloaded ? '已下载' : '下载 PNG'}
            onClick={async () => {
              const ok = await onDownload();
              if (ok) {
                setDownloaded(true);
                setTimeout(() => setDownloaded(false), 1500);
              }
            }}
          >
            {downloaded ? <Check size={15} /> : <Download size={15} />}
          </ToolbarButton>
          <Divider />
          <ToolbarButton label="关闭" onClick={onClose}><X size={15} /></ToolbarButton>
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
