import {
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
  useCallback,
  useRef,
  useState,
} from 'react';

/**
 * Headless pan/zoom transform（核心逻辑照抄 Hermes Desktop use-zoom-pan.ts，
 * 补充 YARL 式平移边界约束 clamp——内容不能拖出视口）。
 * Wheel 朝光标缩放，拖拽平移，按钮朝中心缩放；任何内容（SVG/图）都可套用。
 * 支持初始 fit 比例：打开时按 initialScale 显示（图完整可见），
 * 放大以图中心为锚点（fit 状态下图中心=视图中心，中心放大成立）；
 * reset 回到 fit 比例。
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

const clampScale = (scale: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));

export function useZoomPan(
  initialScale = 1,
  viewport: { w: number; h: number } = { w: 0, h: 0 },
  content: { w: number; h: number } = { w: 0, h: 0 }
) {
  const [transform, setTransform] = useState<Transform>({ scale: initialScale, x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number } | null>(null);
  const [panning, setPanning] = useState(false);

  // 平移边界约束（YARL 式 clamp）：内容不能拖出视口；
  // 内容小于视口时保持居中（x=0）
  const clampTransform = useCallback(
    (t: Transform): Transform => {
      const cw = content.w * t.scale;
      const ch = content.h * t.scale;
      const minX = Math.min(0, viewport.w - cw);
      const maxX = Math.max(0, viewport.w - cw);
      const minY = Math.min(0, viewport.h - ch);
      const maxY = Math.max(0, viewport.h - ch);
      return {
        scale: t.scale,
        x: Math.min(maxX, Math.max(minX, t.x)),
        y: Math.min(maxY, Math.max(minY, t.y)),
      };
    },
    [viewport.w, viewport.h, content.w, content.h]
  );

  // 朝 (cx, cy) 缩放（相对表面中心），保持该点固定；结果 clamp
  const zoomAt = useCallback(
    (factor: number, cx = 0, cy = 0) => {
      setTransform((prev) => {
        const scale = clampScale(prev.scale * factor);
        const k = scale / prev.scale;
        return clampTransform({ scale, x: cx - k * (cx - prev.x), y: cy - k * (cy - prev.y) });
      });
    },
    [clampTransform]
  );

  // 滚轮 = 滑动（纵向平移），符合用户预期"向下滑动查看"；
  // 缩放走双击 / 工具栏按钮。shift+滚轮 = 横向滑动。
  const onWheel = useCallback(
    (event: ReactWheelEvent) => {
      event.preventDefault();
      const dx = event.shiftKey ? event.deltaY : 0;
      const dy = event.shiftKey ? 0 : event.deltaY;
      setTransform((prev) => clampTransform({ ...prev, x: prev.x - dx, y: prev.y - dy }));
    },
    [clampTransform]
  );

  const onPointerDown = useCallback((event: ReactPointerEvent) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    setTransform((prev) => {
      drag.current = { x: event.clientX - prev.x, y: event.clientY - prev.y };
      return prev;
    });
    setPanning(true);
  }, []);

  const onPointerMove = useCallback(
    (event: ReactPointerEvent) => {
      if (!drag.current) return;
      const start = drag.current;
      setTransform((prev) =>
        clampTransform({ ...prev, x: event.clientX - start.x, y: event.clientY - start.y })
      );
    },
    [clampTransform]
  );

  const endPan = useCallback(() => {
    drag.current = null;
    setPanning(false);
  }, []);

  const reset = useCallback(
    () => setTransform({ scale: initialScale, x: 0, y: 0 }),
    [initialScale]
  );
  const zoomIn = useCallback(() => zoomAt(BUTTON_STEP), [zoomAt]);
  const zoomOut = useCallback(() => zoomAt(1 / BUTTON_STEP), [zoomAt]);

  const style: CSSProperties = {
    transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})`,
  };

  return {
    panning,
    reset,
    scale: transform.scale,
    stageProps: {
      onPointerDown,
      onPointerLeave: endPan,
      onPointerMove,
      onPointerUp: endPan,
      onWheel,
    },
    style,
    zoomIn,
    zoomOut,
  };
}
