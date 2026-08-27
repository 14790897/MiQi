import { useEffect, useState, type ReactNode } from 'react';
import { Check, Copy, Download, Maximize, RefreshCw, X, ZoomIn, ZoomOut } from 'lucide-react';
import { useZoomPan } from '../../../hooks/useZoomPan';

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
      {/* 内联渲染：透明嵌入消息流（Hermes 式，无卡片），hover 显示展开提示 */}
      <div
        className="group/zoomable relative my-2 w-full max-w-full cursor-zoom-in select-none"
        onClick={() => setZoom(true)}
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
  const { panning, reset, stageProps, style, zoomIn, zoomOut } = useZoomPan();
  const [copiedPng, setCopiedPng] = useState(false);
  const [downloaded, setDownloaded] = useState(false);

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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-6" onClick={onClose}>
      <div
        className="relative h-[85vh] w-[90vw] max-w-[90vw] overflow-hidden rounded-2xl bg-[var(--surface-elevated)] shadow-xl"
        style={{ border: '1px solid var(--border-subtle)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className={`relative h-full flex-1 touch-none select-none overflow-hidden ${panning ? 'cursor-grabbing' : 'cursor-grab'}`}
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
