import { useEffect, useMemo, useState } from 'react';
import { Check, Copy, Maximize } from 'lucide-react';
import Viewer from 'react-viewer';
import { normalizeSvgSize, svgToPngBlob, svgToXmlSafe } from '../../../lib/svgImage';

/**
 * 统一图表容器（mermaid / svg embed 共用）。
 * 内联：Hermes 式轻量嵌入（无卡片，图居中，hover 右上角 Maximize 提示）。
 * 点击放大：react-viewer（GitHub 主流 React 图片查看器，UI 即经典看图器形态：
 * 底部工具栏 − / + / 1:1 / 下载 / 关闭 + 浅灰画布）——腾讯 QQ 邮箱预览同款交互。
 *   - 滚轮缩放（disableMouseZoom=false 默认即滚轮缩放）
 *   - 拖拽平移（drag）· 双击不做（react-viewer 无内置，滚轮即可）
 *   - 下载 = 白底 PNG（downloadUrl）；复制 PNG 走 customToolbar 自定义按钮
 */
interface DiagramCardProps {
  /** 已消毒的 SVG 字符串 */
  svg: string;
  /** 复制为 PNG 的动作（返回是否成功） */
  onCopy: () => Promise<boolean>;
  /** 下载为 PNG 文件（返回是否成功） */
  onDownload: () => Promise<boolean>;
}

/** 把 SVG 转成可在 <img> 中渲染的 data URL（XML 合法化 + URL 编码） */
function svgToDataUrl(svg: string): string {
  const xml = svgToXmlSafe(svg);
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(xml)}`;
}

export function DiagramCard({ svg, onCopy, onDownload }: DiagramCardProps) {
  const [zoom, setZoom] = useState(false);
  const [copied, setCopied] = useState(false);
  const [dlUrl, setDlUrl] = useState('');
  // 入口统一 normalize（幂等）：% 宽 → viewBox 像素 + 删 mermaid inline max-width
  const svgNorm = useMemo(() => normalizeSvgSize(svg), [svg]);
  const imgSrc = useMemo(() => (svgNorm ? svgToDataUrl(svgNorm) : ''), [svgNorm]);

  // 打开时生成白底 PNG 的下载地址（下载按钮用）
  useEffect(() => {
    if (!zoom) return;
    let alive = true;
    void (async () => {
      try {
        const blob = await svgToPngBlob(svgNorm, 2);
        if (alive) setDlUrl(URL.createObjectURL(blob));
      } catch {
        /* 下载兜底：无 PNG 时按钮禁用 */
      }
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoom]);

  const copy = async () => {
    const ok = await onCopy();
    if (ok) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    }
  };

  const close = () => setZoom(false);

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
        <>
          {/* 画布浅灰背景 + 关闭按钮浅色（腾讯式，融入浅色画布）——注入全局样式 */}
          <style>{`
            .miqi-viewer .react-viewer-mask { background-color: #f0f0f0 !important; }
            .miqi-viewer .react-viewer-close {
              background-color: rgba(0,0,0,0.08) !important;
              color: #444 !important;
            }
            .miqi-viewer .react-viewer-close:hover { background-color: rgba(0,0,0,0.16) !important; }
          `}</style>
          <Viewer
            visible={zoom}
            onClose={close}
            onMaskClick={close}
            images={[{ src: imgSrc, alt: '流程图.png', downloadUrl: dlUrl || imgSrc }]}
            downloadable
            zoomable
            rotatable={false}
            scalable={false}
            noNavbar
            loop={false}
            drag
            className="miqi-viewer"
            customToolbar={(toolbars) => {
              // 腾讯式按钮组：− / + / 1:1 / 下载 / 复制（去掉 prev/next/rotate 等）
              const byKey = Object.fromEntries(toolbars.map((t) => [t.key, t]));
              const order = ['zoomOut', 'zoomIn', 'reset', 'download'];
              const keep = order.map((k) => byKey[k]).filter(Boolean);
              const copyBtn = {
                key: 'copy',
                render: copied ? <Check size={18} style={{ color: '#22c55e' }} /> : <Copy size={18} />,
                onClick: () => void copy(),
              };
              return [...keep, copyBtn];
            }}
          />
        </>
      )}
    </>
  );
}
