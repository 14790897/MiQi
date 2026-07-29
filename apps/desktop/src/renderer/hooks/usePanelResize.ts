import { useState, useRef, useCallback, useEffect } from 'react';

export interface UsePanelResizeOptions {
  minWidth: number;
  maxWidth: number;
  defaultWidth: number;
  /** Compute new width from mouse position and container rect.
   *  For left-mounted panels: `e.clientX - rect.left`
   *  For right-mounted panels: `window.innerWidth - e.clientX` */
  computeWidth: (e: MouseEvent, rect: DOMRect) => number;
}

export function usePanelResize(options: UsePanelResizeOptions) {
  const { minWidth, maxWidth, defaultWidth, computeWidth } = options;
  const [width, setWidth] = useState(defaultWidth);
  const isResizing = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isResizing.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing.current) return;
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const newWidth = computeWidth(e, rect);
      setWidth(Math.max(minWidth, Math.min(maxWidth, newWidth)));
    };
    const handleMouseUp = () => {
      if (isResizing.current) {
        isResizing.current = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      isResizing.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [minWidth, maxWidth, computeWidth]);

  return { width, containerRef, handleMouseDown };
}
