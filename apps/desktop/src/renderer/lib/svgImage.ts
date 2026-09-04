/**
 * SVG 工具（逻辑照抄 Hermes lib/svg-image.ts）——mermaid 与 svg embed 共用。
 */

// Mermaid 输出 width="100%" + viewBox；百分比不是固有尺寸，缩放容器会塌陷。
// 用 viewBox 像素替换百分比宽高；无百分比时原样返回。
// mermaid 输出含 &nbsp; 等 HTML 命名实体 → image/svg+xml 解析失败，
// 回退 text/html 解析（HTML 解析器容忍 HTML 实体）——否则 width="100%"
// 保留，dialog/缩放容器里 shrink-to-fit 链路会塌陷成 300px 默认宽。
export function normalizeSvgSize(svg: string): string {
  let el: Element | null = null;
  try {
    const doc = new DOMParser().parseFromString(svg, 'image/svg+xml');
    if (doc.documentElement.tagName === 'svg') el = doc.documentElement;
  } catch {
    el = null;
  }
  if (!el) {
    const doc = new DOMParser().parseFromString(svg, 'text/html');
    el = doc.querySelector('svg');
  }
  if (!el) return svg;
  const width = el.getAttribute('width');
  const height = el.getAttribute('height');
  const widthPct = Boolean(width?.trim().endsWith('%'));
  const heightPct = Boolean(height?.trim().endsWith('%'));
  if (!widthPct && !heightPct) return svg;
  const [, , vbW, vbH] = (el.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
  if (!(vbW > 0 && vbH > 0)) return svg;
  if (widthPct) el.setAttribute('width', String(vbW));
  if (heightPct || (widthPct && !height)) el.setAttribute('height', String(vbH));
  // mermaid 渲染时会给 svg 写 inline style="max-width: <svg宽>px"——inline 优先级
  // 高于 class，容器里的 max-w-full/缩放都压不住它 → 删除
  const style = (el as unknown as { style?: CSSStyleDeclaration }).style;
  style?.removeProperty?.('max-width');
  return new XMLSerializer().serializeToString(el);
}

export function svgSize(svg: string): { height: number; width: number } {
  const el = new DOMParser().parseFromString(svg, 'image/svg+xml').documentElement;
  if (el.tagName !== 'svg') {
    // mermaid 输出含 HTML 实体 → XML 解析失败，用 HTML 解析兜底
    const doc = new DOMParser().parseFromString(svg, 'text/html');
    const svgEl = doc.querySelector('svg');
    if (!svgEl) return { height: 600, width: 800 };
    const [, , vbW2, vbH2] = (svgEl.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
    return vbW2 > 0 && vbH2 > 0 ? { height: vbH2, width: vbW2 } : { height: 600, width: 800 };
  }
  const wRaw = el.getAttribute('width') || '';
  const hRaw = el.getAttribute('height') || '';
  // % 宽度不是固有尺寸（如 mermaid 的 width="100%"），回退 viewBox
  const w = wRaw && !wRaw.trim().endsWith('%') ? Number.parseFloat(wRaw) : NaN;
  const h = hRaw && !hRaw.trim().endsWith('%') ? Number.parseFloat(hRaw) : NaN;
  if (Number.isFinite(w) && Number.isFinite(h) && w > 0 && h > 0) return { height: h, width: w };
  const [, , vbW, vbH] = (el.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
  return vbW > 0 && vbH > 0 ? { height: vbH, width: vbW } : { height: 600, width: 800 };
}

/**
 * 把 SVG 字符串转成 XML 合法形式（mermaid 输出含 &nbsp; 等 HTML 命名实体，
 * 直接放 data URL 时 img 用 XML 解析会失败 → PNG 生成失败）。
 * 用 HTML 解析器读入（容忍 HTML 实体），再用 XMLSerializer 输出
 * （自动转成 XML 合法实体 &#160; 等）。
 */
export function svgToXmlSafe(svg: string): string {
  const doc = new DOMParser().parseFromString(svg, 'text/html');
  const svgEl = doc.querySelector('svg');
  if (!svgEl) return svg;
  return new XMLSerializer().serializeToString(svgEl);
}

/** 把 SVG 渲染成 2x PNG Blob（copy / download 共用）。
 *  用 canvg（GitHub 主流 svg→canvas 引擎，9k stars）渲染：
 *  解析容错（HTML 实体/非标准 SVG）、不依赖 <img> 加载（更稳定）；
 *  先 svgToXmlSafe 清洗实体双保险。动态 import——SSR 环境不加载。 */
export async function svgToPngBlob(svg: string, scale = 2): Promise<Blob> {
  const { height, width } = svgSize(svg);
  const xml = svgToXmlSafe(svg);
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  const ctx = canvas.getContext('2d');
  if (!ctx) return Promise.reject(new Error('no 2d context'));
  // mermaid SVG 背景透明——PNG 导出铺白底（用户反馈"后面全是透明的"）
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const { Canvg } = await import('canvg');
  // canvg v4：忽略 svg 自带尺寸，按目标画布尺寸（2x）等比渲染；
  // ignoreClear——不清空画布（否则白底被擦掉）
  const v = await Canvg.from(ctx, xml, {
    ignoreDimensions: true,
    scaleWidth: canvas.width,
    scaleHeight: canvas.height,
    ignoreClear: true,
  });
  await v.render();
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('toBlob failed'))), 'image/png')
  );
}

/** 把 SVG 导出为 PNG 文件下载（图表用户保存场景）。 */
export async function downloadSvgAsPng(svg: string, filename = 'diagram.png'): Promise<boolean> {
  try {
    const blob = await svgToPngBlob(svg);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    return true;
  } catch {
    return false;
  }
}

/** 把 SVG 渲染成 PNG 并复制到剪贴板（失败回退复制 SVG 文本）。 */
export async function copySvgAsPng(svg: string): Promise<boolean> {
  try {
    const blob = await svgToPngBlob(svg);
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
