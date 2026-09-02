import { useMemo, useState } from 'react';
import { Check, Copy, Maximize } from 'lucide-react';
import Lightbox from 'yet-another-react-lightbox';
import Zoom from 'yet-another-react-lightbox/plugins/zoom';
import Download from 'yet-another-react-lightbox/plugins/download';
import 'yet-another-react-lightbox/styles.css';
import { normalizeSvgSize } from '../../../lib/svgImage';

// 自定义 slide 类型：diagram（SVG 图）。
// 注：YARL 的 SlideTypes 在内部模块声明（re-export），module augmentation
// 无法合并（TS 限制）——slides/render 用类型断言标注，运行时不受影响。
interface DiagramSlide {
  type: 'diagram';
  svg: string;
}

/**
 * 统一图表容器（mermaid / svg embed 共用）。
 * 内联：Hermes 式轻量嵌入（无卡片，图居中，hover 右上角 Maximize 提示）。
 * 点击放大：直接用专业 lightbox 库 yet-another-react-lightbox（React 生态主流，
 * 1.3k stars）——zoom 插件提供双击放大×2 / Ctrl+滚轮缩放 / 拖拽平移（边界
 * clamp）/ 键盘方向键 / 触摸缩放，download 插件提供下载（白底 PNG）。
 * 不再自写查看器轮子（用户反馈"专门的库比较好"）。
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
  const [copied, setCopied] = useState(false);
  // 入口统一 normalize（幂等）：% 宽 → viewBox 像素 + 删 mermaid inline max-width，
  // 覆盖 mermaid 与 ```svg embed 两条路径——否则 shrink/缩放容器里塌陷或压不住
  const svgNorm = useMemo(() => normalizeSvgSize(svg), [svg]);

  const copy = async () => {
    const ok = await onCopy();
    if (ok) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    }
  };

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

      {/* 点击放大：YARL Lightbox（zoom 插件全交互 + download 插件下载白底 PNG） */}
      {zoom && (
        <>
          <Lightbox
            open
            close={() => setZoom(false)}
            plugins={[Zoom, Download]}
            zoom={{
              supports: ['diagram'],
              maxZoom: 8,
              // 滚轮语义（用户要求）：Ctrl+滚轮 = 中心缩放（scrollToZoom 默认 false），
              // 放大后普通滚轮 = 平移查看
            }}
            download={{
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              download: ({ slide }: any) => {
                if ((slide as DiagramSlide).type === 'diagram') {
                  void onDownload();
                }
              },
            }}
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            slides={[{ type: 'diagram', svg: svgNorm }] as any}
            render={{
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              slide: ({ slide }: any) =>
                (slide as DiagramSlide).type === 'diagram' ? (
                  // svg 铺满 slide（viewBox 保持比例居中）；zoom 时 wrapper
                  // transform scale 放大整个矢量内容（清晰无损）
                  <div
                    className="flex h-full w-full items-center justify-center [&_svg]:h-full [&_svg]:w-full [&_svg]:pointer-events-none"
                    dangerouslySetInnerHTML={{ __html: (slide as DiagramSlide).svg }}
                  />
                ) : undefined,
              // 单图查看：隐藏左右导航箭头
              buttonPrev: () => null,
              buttonNext: () => null,
            }}
          />
          {/* 复制 PNG：YARL 无内置复制按钮——左下角浮层（避开右上角 YARL 工具栏） */}
          <button
            aria-label="复制 PNG"
            title="复制 PNG"
            type="button"
            onClick={copy}
            className="fixed bottom-6 left-6 z-[10001] flex h-10 items-center gap-2 rounded-full border border-white/20 bg-black/50 px-4 text-sm text-white/90 shadow-lg backdrop-blur transition-colors hover:bg-black/70"
          >
            {copied ? <Check size={16} /> : <Copy size={16} />}
            {copied ? '已复制' : '复制 PNG'}
          </button>
        </>
      )}
    </>
  );
}
