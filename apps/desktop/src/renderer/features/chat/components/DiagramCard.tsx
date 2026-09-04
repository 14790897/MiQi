import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Check, Copy, Download, Maximize, Minus, Plus, RotateCw, X } from 'lucide-react';
import { useZoomPan } from '../../../hooks/useZoomPan';
import { normalizeSvgSize, svgSize } from '../../../lib/svgImage';

/**
 * 统一图表容器（mermaid / svg embed 共用）。
 * 内联：Hermes 式轻量嵌入（无卡片，图居中，hover 右上角 Maximize 提示）。
 * 点击放大：腾讯 QQ 邮箱图片预览形态（自绘，无第三方 portal——第三方的
 * portal 层叠会拦截真实鼠标点击，自绘 overlay 全部自己控制）：
 *   - 顶部白色工具行：流程图预览 + − / 百分比 / + / 适应窗口 ｜ 复制 PNG / 下载 PNG / ✕
 *   - 主区浅灰画布（#f0f0f0），白图居中无边框
 *   - 滚轮 = 缩放（腾讯行为）；双击放大×2；拖拽平移（边界 clamp）
 */
interface DiagramCardProps {
  /** 已消毒的 SVG 字符串 */
  svg: string;
  /** 复制为 PNG 的动作（返回是否成功） */
  onCopy: () => Promise<boolean>;
  /** 下载为 PNG 文件（返回是否成功） */
  onDownload: () => Promise<boolean>;
}

const BAR_BTN =
  'grid size-9 place-items-center rounded-full text-white/90 transition-colors hover:bg-white/20 active:bg-white/30';

export function DiagramCard({ svg, onCopy, onDownload }: DiagramCardProps) {
  const [zoom, setZoom] = useState(false);
  const [copied, setCopied] = useState(false);
  // 入口统一 normalize（幂等）：% 宽 → viewBox 像素 + 删 mermaid inline max-width
  const svgNorm = useMemo(() => normalizeSvgSize(svg), [svg]);

  const copy = useCallback(async () => {
    const ok = await onCopy();
    if (ok) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    }
  }, [onCopy]);

  return (
    <>
      {/* 内联渲染：透明嵌入消息流（无卡片），hover 显示展开提示。
          键盘可达：role=button + tabIndex + Enter/Space 打开 */}
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
        <div className="w-full overflow-hidden p-1 [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-h-[50vh] [&_svg]:max-w-full [&_svg]:pointer-events-none">
          <div dangerouslySetInnerHTML={{ __html: svgNorm }} />
        </div>
        {/* 悬停时右上角展开提示 */}
        <span
          aria-hidden
          className="pointer-events-none absolute right-2 top-2 grid size-7 place-items-center rounded-full border border-[var(--border)] bg-[var(--surface)]/80 text-[var(--text-muted)] opacity-0 shadow-sm transition-opacity group-hover/zoomable:opacity-100"
        >
          <Maximize size={14} />
        </span>
      </div>

      {zoom && (
        <TencentViewer
          svg={svgNorm}
          onClose={() => setZoom(false)}
          onCopy={copy}
          onDownload={onDownload}
        />
      )}
    </>
  );
}

/** 腾讯式查看器：顶部工具行 + 浅灰画布 + 图居中（自绘 overlay，交互全可控） */
function TencentViewer({
  svg,
  onClose,
  onCopy,
  onDownload,
}: {
  svg: string;
  onClose: () => void;
  onCopy: () => Promise<void>;
  onDownload: () => Promise<boolean>;
}) {
  const stageRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const [viewport, setViewport] = useState({ w: 0, h: 0 });
  const [content, setContent] = useState({ w: 0, h: 0 });
  const [copied, setCopied] = useState(false);
  const [rot, setRot] = useState(0);
  // svg 原始像素尺寸（1:1 按钮需要；旋转后宽高互换）
  const svgW = useMemo(() => svgSize(svg).width || 1, [svg]);
  const svgH = useMemo(() => svgSize(svg).height || 1, [svg]);

  // 测量 stage 视口 + svg 实际布局尺寸（clamp 需要真实布局尺寸）
  useEffect(() => {
    const measure = () => {
      if (stageRef.current) {
        setViewport({ w: stageRef.current.clientWidth, h: stageRef.current.clientHeight });
      }
      const svgEl = contentRef.current?.querySelector('svg');
      if (svgEl) {
        const r = svgEl.getBoundingClientRect();
        setContent({ w: r.width, h: r.height });
      }
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

  const { panning, reset, scale, stageProps, style, zoomBy, zoomTo } = useZoomPan(1, viewport, content);

  // 1:1 = svg 原始像素尺寸（相对当前 contain 布局尺寸的比例；旋转 90° 后宽高互换）
  const toOriginalSize = useCallback(() => {
    const origW = rot % 180 === 0 ? svgW : svgH;
    const target = origW / (content.w || 1);
    if (target > 0 && Math.abs(target - scale) > 0.01) zoomTo(target);
  }, [svgW, svgH, rot, content.w, scale, zoomTo]);

  // 旋转 90°：内容视觉宽高互换（clamp 基准随之 swap）
  const rotate = useCallback(() => {
    setRot((r) => {
      const nr = (r + 90) % 360;
      if (nr % 180 !== 0) {
        setContent((c) => ({ w: c.h, h: c.w }));
      }
      return nr;
    });
    window.setTimeout(reset, 0);
  }, [reset]);

  // Esc 关闭 + 锁背景滚动
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

  // 滚轮 = 缩放（腾讯行为）；shift+滚轮 = 横向滑动；Ctrl+滚轮同样缩放
  const onWheel = useCallback(
    (e: React.WheelEvent) => {
      e.preventDefault();
      zoomBy(e.deltaY < 0 ? 1.1 : 1 / 1.1);
    },
    [zoomBy]
  );

  const copyPng = async () => {
    await onCopy();
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  const pct = Math.round((scale * (content.w || 1) / svgW) * 100);

  return (
    <div className="fixed inset-0 z-50 bg-[#f0f0f0]" role="dialog" aria-label="流程图预览">
      {/* 画布：图居中 + 缩放/平移/旋转 */}
      <div
        ref={stageRef}
        className={`absolute inset-0 touch-none select-none overflow-hidden ${panning ? 'cursor-grabbing' : 'cursor-grab'}`}
        onPointerDown={(e) => {
          e.stopPropagation();
          stageProps.onPointerDown(e);
        }}
        onPointerMove={stageProps.onPointerMove}
        onPointerUp={stageProps.onPointerUp}
        onPointerLeave={stageProps.onPointerLeave}
        onWheel={onWheel}
        onDoubleClick={(e) => {
          e.stopPropagation();
          if (scale > 1.1) reset();
          else zoomBy(2);
        }}
      >
        <div className="absolute inset-0 grid place-items-center">
          <div className="origin-center h-full w-full" style={{ ...style, transform: `${style.transform} rotate(${rot}deg)` }}>
            <div className="flex h-full w-full items-center justify-center">
              {/* 图：CSS contain（max-h/max-w 内自然尺寸），无边框无阴影 */}
              <div
                ref={contentRef}
                className="w-full [&_svg]:block [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-h-[calc(100vh-88px)] [&_svg]:max-w-full [&_svg]:pointer-events-none"
                dangerouslySetInnerHTML={{ __html: svg }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* 底部居中深色半透明工具条（Windows 照片/微信看图器范式）：
          旋转 ｜ − / % / + / 1:1 ｜ 复制 / 下载 ｜ 关闭 */}
      <div className="pointer-events-none absolute inset-x-0 bottom-5 z-10 flex justify-center">
        <div className="pointer-events-auto flex items-center gap-1 rounded-full bg-black/65 px-2 py-1.5 shadow-lg backdrop-blur-md">
          <button aria-label="旋转 90°" title="旋转 90°" type="button" className={BAR_BTN} onClick={rotate}>
            <RotateCw size={17} strokeWidth={1.75} />
          </button>
          <span className="mx-1 h-4 w-px bg-white/25" />
          <button aria-label="缩小" title="缩小" type="button" className={BAR_BTN} onClick={() => zoomBy(1 / 1.25)}>
            <Minus size={17} strokeWidth={1.75} />
          </button>
          <span className="min-w-12 text-center text-xs tabular-nums text-white/85 select-none">
            {pct}%
          </span>
          <button aria-label="放大" title="放大" type="button" className={BAR_BTN} onClick={() => zoomBy(1.25)}>
            <Plus size={17} strokeWidth={1.75} />
          </button>
          {/* 1:1：回到原始像素尺寸 */}
          <button
            aria-label="1:1 原始大小"
            title="1:1 原始大小"
            type="button"
            className={`${BAR_BTN} px-2 text-xs font-medium text-white/90`}
            onClick={toOriginalSize}
          >
            1:1
          </button>
          <span className="mx-1 h-4 w-px bg-white/25" />
          <button aria-label="复制 PNG" title="复制 PNG" type="button" className={BAR_BTN} onClick={() => void copyPng()}>
            {copied ? <Check size={17} strokeWidth={2} className="text-green-400" /> : <Copy size={17} strokeWidth={1.75} />}
          </button>
          <button aria-label="下载 PNG" title="下载 PNG" type="button" className={BAR_BTN} onClick={() => void onDownload()}>
            <Download size={17} strokeWidth={1.75} />
          </button>
          <span className="mx-1 h-4 w-px bg-white/25" />
          <button aria-label="关闭" title="关闭" type="button" className={BAR_BTN} onClick={onClose}>
            <X size={18} strokeWidth={1.75} />
          </button>
        </div>
      </div>
    </div>
  );
}
