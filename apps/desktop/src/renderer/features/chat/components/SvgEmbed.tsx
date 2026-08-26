import DOMPurifyImport from 'dompurify';
import { useMemo } from 'react';
import { copySvgAsPng, downloadSvgAsPng } from '../../../lib/svgImage';
import { DiagramCard } from './DiagramCard';

// vite/node 下 dompurify 的 default 导出可能是嵌套的（ESM/CJS interop）
const DOMPurify = (DOMPurifyImport as unknown as { default?: typeof DOMPurifyImport }).default ?? DOMPurifyImport;

/**
 * ```svg 代码块渲染（对齐 Hermes Desktop embeds/svg-embed.tsx）。
 * DOMPurify svg profile 硬消毒后渲染：剥离 script、事件处理器、foreignObject，
 * 模型输出的不可信 SVG 无法执行代码。
 * 展示统一走 DiagramCard（宽度一致/居中/弹窗预览/复制 PNG）。
 */
export function SvgEmbed({ code }: { code: string }) {
  const clean = useMemo(() => {
    // SSR/node 环境无 window，dompurify 无法工作 —— 渲染器在浏览器执行
    if (typeof window === 'undefined') return '';
    return DOMPurify.sanitize(code, {
      USE_PROFILES: { svg: true, svgFilters: true },
    });
  }, [code]);

  if (!clean.trim()) {
    return null;
  }

  return (
    <DiagramCard
      svg={clean}
      onCopy={() => copySvgAsPng(clean)}
      onDownload={() => downloadSvgAsPng(clean, `diagram-${Date.now()}.png`)}
    />
  );
}
