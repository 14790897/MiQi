import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, Copy, Download, Maximize, Minus, Plus, X } from 'lucide-react';
import Lightbox, { type ZoomRef } from 'yet-another-react-lightbox';
import Zoom from 'yet-another-react-lightbox/plugins/zoom';
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
 * 点击放大：腾讯 QQ 邮箱图片预览形态（用户提供截图作为设计基准）——
 *   顶部白色工具行：「流程图预览」+ 右侧 − / 百分比 / + / 适应窗口 ｜ 复制 PNG / 下载 PNG / ✕
 *   主区浅灰画布（#f0f0f0），白图居中、无边框无阴影
 *   滚轮 = 缩放（scrollToZoom，腾讯行为）；双击放大×2；放大后拖拽平移
 * 内核用 yet-another-react-lightbox（zoom 插件：缩放/平移边界 clamp/触摸/键盘）。
 */
interface DiagramCardProps {
  /** 已消毒的 SVG 字符串 */
  svg: string;
  /** 复制为 PNG 的动作（返回是否成功） */
  onCopy: () => Promise<boolean>;
  /** 下载为 PNG 文件（返回是否成功） */
  onDownload: () => Promise<boolean>;
}

const TOOLBAR_BTN =
  'grid size-8 place-items-center rounded-md text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900';

export function DiagramCard({ svg, onCopy, onDownload }: DiagramCardProps) {
  const [zoom, setZoom] = useState(false);
  const [copied, setCopied] = useState(false);
  const [scale, setScale] = useState(1);
  const zoomRef = useRef<ZoomRef | null>(null);
  // 入口统一 normalize（幂等）：% 宽 → viewBox 像素 + 删 mermaid inline max-width
  const svgNorm = useMemo(() => normalizeSvgSize(svg), [svg]);

  // YARL 浅色主题（腾讯形态：画布浅灰 #f0f0f0）——portal 挂 body 下需全局注入；
  // 打开时设置，关闭时恢复
  useEffect(() => {
    if (!zoom) return;
    const root = document.documentElement;
    const prev: [string, string][] = [
      '--yarl__color_backdrop',
      '--yarl__color_button',
      '--yarl__color_button_active',
      '--yarl__button_filter',
    ].map((k) => [k, root.style.getPropertyValue(k)]);
    root.style.setProperty('--yarl__color_backdrop', '#f0f0f0');
    root.style.setProperty('--yarl__color_button', 'rgba(0,0,0,0.55)');
    root.style.setProperty('--yarl__color_button_active', 'rgba(0,0,0,0.85)');
    root.style.setProperty('--yarl__button_filter', 'none');
    setScale(1);
    return () => {
      for (const [k, v] of prev) {
        if (v) root.style.setProperty(k, v);
        else root.style.removeProperty(k);
      }
    };
  }, [zoom]);

  const copy = async () => {
    const ok = await onCopy();
    if (ok) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    }
  };

  const pct = Math.round(scale * 100);

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

      {/* 点击放大：腾讯式查看器（YARL zoom 内核 + 顶部工具行） */}
      {zoom && (
        <>
          <Lightbox
            open
            close={() => setZoom(false)}
            plugins={[Zoom]}
            zoom={{
              ref: zoomRef,
              supports: ['diagram'],
              maxZoom: 8,
              scrollToZoom: true, // 腾讯行为：鼠标滚轮直接缩放（不按 Ctrl）
            }}
            // 隐藏 YARL 自带 toolbar/导航——用腾讯式顶部工具行替代
            toolbar={{ buttons: [] }}
            on={{
              zoom: ({ zoom: z }) => setScale(z),
            }}
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            slides={[{ type: 'diagram', svg: svgNorm }] as any}
            render={{
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              slide: ({ slide }: any) =>
                (slide as DiagramSlide).type === 'diagram' ? (
                  // svg 铺满 slide（viewBox 保持比例居中，无边框无阴影）
                  <div
                    className="flex h-full w-full items-center justify-center [&_svg]:h-full [&_svg]:w-full [&_svg]:pointer-events-none"
                    dangerouslySetInnerHTML={{ __html: (slide as DiagramSlide).svg }}
                  />
                ) : undefined,
              // 单图查看：隐藏左右翻页箭头
              buttonPrev: () => null,
              buttonNext: () => null,
            }}
          />
          {/* 腾讯式顶部工具行：左文件名 + 右缩放/复制/下载/关闭 */}
          <div className="fixed inset-x-0 top-0 z-[10001] flex h-11 items-center justify-between border-b border-gray-200 bg-white px-3">
            <span className="pl-1 text-sm font-medium text-gray-800">流程图预览</span>
            <div className="flex items-center gap-0.5">
              <button
                aria-label="缩小"
                title="缩小"
                type="button"
                className={TOOLBAR_BTN}
                onClick={() => zoomRef.current?.zoomOut()}
              >
                <Minus size={16} />
              </button>
              <span className="min-w-11 text-center text-xs tabular-nums text-gray-600">
                {scale === 1 ? '适应' : `${pct}%`}
              </span>
              <button
                aria-label="放大"
                title="放大"
                type="button"
                className={TOOLBAR_BTN}
                onClick={() => zoomRef.current?.zoomIn()}
              >
                <Plus size={16} />
              </button>
              <button
                aria-label="适应窗口"
                title="适应窗口"
                type="button"
                className={TOOLBAR_BTN}
                onClick={() => zoomRef.current?.changeZoom?.(1)}
              >
                <Maximize size={15} />
              </button>
              <span className="mx-1.5 h-5 w-px bg-gray-200" />
              <button
                aria-label="复制 PNG"
                title="复制 PNG"
                type="button"
                className={TOOLBAR_BTN}
                onClick={copy}
              >
                {copied ? <Check size={16} className="text-green-600" /> : <Copy size={16} />}
              </button>
              <button
                aria-label="下载 PNG"
                title="下载 PNG"
                type="button"
                className={TOOLBAR_BTN}
                onClick={() => void onDownload()}
              >
                <Download size={16} />
              </button>
              <span className="mx-1.5 h-5 w-px bg-gray-200" />
              <button
                aria-label="关闭"
                title="关闭"
                type="button"
                className={`${TOOLBAR_BTN} ml-0.5`}
                onClick={() => setZoom(false)}
              >
                <X size={17} />
              </button>
            </div>
          </div>
        </>
      )}
    </>
  );
}
