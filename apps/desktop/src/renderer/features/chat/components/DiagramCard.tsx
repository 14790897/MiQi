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
  // fit 比例：打开弹窗时图完整显示（用户要求），放大以图中心为锚点
  const fitScale = useMemo(() => {
    if (typeof window === 'undefined') return 1;
    const { height: sh, width: sw } = svgSize(svg);
    // 弹窗 85vw×85vh（用户：96% 太大、680 太小——折中）
    const viewW = window.innerWidth * 0.85 - 8;
    const viewH = window.innerHeight * 0.85 - 96;
    return Math.min(1, viewW / sw, viewH / sh);
  }, [svg]);

  const { panning, reset, stageProps, style, zoomIn, zoomOut, scale } = useZoomPan(fitScale);
  const [copiedPng, setCopiedPng] = useState(false);
  const [downloaded, setDownloaded] = useState(false);
  // 弹窗拖动（按住标题条可移动弹窗位置）
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const dragRef = useRef<{ sx: number; sy: number; ox: number; oy: number } | null>(null);

  // Escape 关闭 + 打开时重置缩放 + 锁背景滚动（防弹窗内滚动穿透导致
  // 背景页面滑动——用户反馈"向上滑"）
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

  // 弹窗拖动：pointer 按下记录起点，移动更新位置
  const startDrag = (e: ReactPointerEvent) => {
    dragRef.current = { sx: e.clientX, sy: e.clientY, ox: pos.x, oy: pos.y };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onDragMove = (e: ReactPointerEvent) => {
    if (!dragRef.current) return;
    const d = dragRef.current;
    setPos({ x: d.ox + (e.clientX - d.sx), y: d.oy + (e.clientY - d.sy) });
  };
  const endDrag = () => { dragRef.current = null; };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="relative h-[85vh] w-[85vw] rounded-2xl bg-[var(--surface-elevated)] shadow-xl"
        style={{ border: '1px solid var(--border-subtle)', transform: `translate(${pos.x}px, ${pos.y}px)` }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 顶部标题条：按住可拖动弹窗（与图区域平移互不冲突） */}
        <div
          className="flex h-9 cursor-move touch-none select-none items-center justify-between rounded-t-2xl border-b border-[var(--border-subtle)] px-3"
          onPointerDown={startDrag}
          onPointerMove={onDragMove}
          onPointerUp={endDrag}
          onPointerLeave={endDrag}
        >
          <span className="text-xs text-[var(--text-muted)]">流程图预览</span>
          <button
            aria-label="关闭"
            title="关闭"
            className="grid size-7 place-items-center rounded-full text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-muted)] hover:text-[var(--text)]"
            onClick={onClose}
            type="button"
          >
            <X size={15} />
          </button>
        </div>
        <div
          className={`max-h-[calc(100%-92px)] overflow-auto rounded-t-2xl ${panning ? 'cursor-grabbing' : 'cursor-grab'}`}
          onPointerDown={(e) => {
            e.stopPropagation();
            stageProps.onPointerDown(e);
          }}
          onPointerMove={stageProps.onPointerMove}
          onPointerUp={stageProps.onPointerUp}
          onPointerLeave={stageProps.onPointerLeave}
          onWheel={stageProps.onWheel}
          onDoubleClick={(e) => {
            // 双击放大/还原（对齐 YARL 等看图器交互）
            e.stopPropagation();
            if (scale > fitScale * 1.1) {
              reset();
            } else {
              zoomIn();
            }
          }}
        >
          <div className="grid w-full place-items-center">
            <div className="origin-center w-full" style={style}>
              {/* 图撑满弹窗宽度（大图清晰）；超高时弹窗内滚动；缩放后可平移。
                  注意：mermaid 输出含 HTML 实体导致 DOMParser XML 解析失败，
                  normalizeSvgSize 会跳过（width 保持 100%）——靠容器固定宽度
                  让 width:100% 生效（不要依赖 svg 属性像素值） */}
              <div className="w-full [&_svg]:block [&_svg]:w-full [&_svg]:h-auto [&_svg]:max-w-full [&_svg]:pointer-events-none">
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
