import {
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
  useCallback,
  useRef,
  useState,
} from 'react';

/**
 * Headless pan/zoom transform（照抄 Hermes Desktop use-zoom-pan.ts）。
 * Wheel 朝光标缩放，拖拽平移，按钮朝中心缩放；任何内容（SVG/图）都可套用。
 */
interface Transform {
  scale: number;
  x: number;
  y: number;
}

const MIN_SCALE = 0.25;
const MAX_SCALE = 8;
const WHEEL_STEP = 1.1;
const BUTTON_STEP = 1.25;

const clamp = (scale: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));

export function useZoomPan() {
  const [transform, setTransform] = useState<Transform>({ scale: 1, x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number } | null>(null);
  const [panning, setPanning] = useState(false);

  // 朝 (cx, cy) 缩放（相对表面中心），保持该点固定
  const zoomAt = useCallback((factor: number, cx = 0, cy = 0) => {
    setTransform((prev) => {
      const scale = clamp(prev.scale * factor);
      const k = scale / prev.scale;
      return { scale, x: cx - k * (cx - prev.x), y: cy - k * (cy - prev.y) };
    });
  }, []);

  const onWheel = useCallback(
    (event: ReactWheelEvent) => {
      event.preventDefault();
      const rect = event.currentTarget.getBoundingClientRect();
      const cx = event.clientX - rect.left - rect.width / 2;
      const cy = event.clientY - rect.top - rect.height / 2;
      zoomAt(event.deltaY < 0 ? WHEEL_STEP : 1 / WHEEL_STEP, cx, cy);
    },
    [zoomAt]
  );

  const onPointerDown = useCallback((event: ReactPointerEvent) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    setTransform((prev) => {
      drag.current = { x: event.clientX - prev.x, y: event.clientY - prev.y };
      return prev;
    });
    setPanning(true);
  }, []);

  const onPointerMove = useCallback((event: ReactPointerEvent) => {
    if (!drag.current) return;
    const start = drag.current;
    setTransform((prev) => ({ ...prev, x: event.clientX - start.x, y: event.clientY - start.y }));
  }, []);

  const endPan = useCallback(() => {
    drag.current = null;
    setPanning(false);
  }, []);

  const reset = useCallback(() => setTransform({ scale: 1, x: 0, y: 0 }), []);
  const zoomIn = useCallback(() => zoomAt(BUTTON_STEP), [zoomAt]);
  const zoomOut = useCallback(() => zoomAt(1 / BUTTON_STEP), [zoomAt]);

  const style: CSSProperties = {
    transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})`,
  };

  return {
    panning,
    reset,
    scale: transform.scale,
    stageProps: { onPointerDown, onPointerLeave: endPan, onPointerMove, onPointerUp: endPan, onWheel },
    style,
    zoomIn,
    zoomOut,
  };
}
