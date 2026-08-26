import DOMPurifyImport from 'dompurify';
import { useMemo } from 'react';

// vite/node 下 dompurify 的 default 导出可能是嵌套的（ESM/CJS interop）
const DOMPurify = (DOMPurifyImport as unknown as { default?: typeof DOMPurifyImport }).default ?? DOMPurifyImport;

/**
 * ```svg 代码块渲染（对齐 Hermes Desktop embeds/svg-embed.tsx）。
 * DOMPurify svg profile 硬消毒后渲染：剥离 script、事件处理器、foreignObject，
 * 模型输出的不可信 SVG 无法执行代码。
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
    <div
      className="my-2 [&_svg]:block [&_svg]:h-auto [&_svg]:w-auto [&_svg]:max-h-[33vh] [&_svg]:max-w-full"
      // DOMPurify svg profile 消毒后注入（剥离 script/事件处理器）
      dangerouslySetInnerHTML={{ __html: clean }}
    />
  );
}
