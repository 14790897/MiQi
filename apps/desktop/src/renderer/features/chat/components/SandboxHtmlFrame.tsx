import { useEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';

/**
 * Inject a sizing script into the HTML so the (opaque-origin, sandboxed)
 * iframe reports its content height to the parent via postMessage. Lets the
 * frame hug its content instead of leaving a fixed-height white void below a
 * short page.
 */
const SIZER_SCRIPT =
  `<script>(function(){function s(){var d=Math.max(document.body?document.body.scrollHeight:0,document.documentElement?document.documentElement.scrollHeight:0);parent.postMessage({__miqiHtmlH:d},'*')}window.addEventListener('load',s);window.addEventListener('resize',s);setTimeout(s,400)})()<\/script>`;

function withSizer(html: string): string {
  if (/<\/body>/i.test(html)) return html.replace(/<\/body>/i, SIZER_SCRIPT + '</body>');
  return html + SIZER_SCRIPT;
}

interface Props {
  html: string;
  className?: string;
  /** Caps the fitted height (CSS length). The frame scrolls if content is taller. */
  maxHeight?: string;
}

/** Sandboxed HTML preview frame (scripts allowed, opaque origin) that
 *  auto-fits its height to the page content. */
export function SandboxHtmlFrame({ html, className = '', maxHeight }: Props) {
  const ref = useRef<HTMLIFrameElement>(null);
  const [contentHeight, setContentHeight] = useState<number | null>(null);

  useEffect(() => {
    setContentHeight(null);
    const onMsg = (e: MessageEvent) => {
      if (e.source !== ref.current?.contentWindow) return;
      if (e.data && typeof e.data.__miqiHtmlH === 'number') {
        setContentHeight(e.data.__miqiHtmlH);
      }
    };
    window.addEventListener('message', onMsg);
    return () => window.removeEventListener('message', onMsg);
  }, [html]);

  const style: CSSProperties = { background: '#fff' };
  if (contentHeight) {
    style.height = maxHeight
      ? `min(${contentHeight}px, ${maxHeight})`
      : `${contentHeight}px`;
  }

  return (
    <iframe
      ref={ref}
      sandbox="allow-scripts"
      srcDoc={withSizer(html)}
      className={className}
      style={style}
      title="HTML 预览"
    />
  );
}
