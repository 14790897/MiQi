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

const MIN_SCALE = 1; // 最小 = contain 完整显示（YARL minZoom: 1，不再缩小）
const MAX_SCALE = 8; // YARL maxZoom: 8
const WHEEL_STEP = 1.1;
const BUTTON_STEP = 2; // YARL zoomInMultiplier: 2 —— 双击/按钮一次 ×2，保证放大后一定超过视口可拖动

const clampScale = (scale: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));

export function useZoomPan(
  initialScale = 1,
  viewport: { w: number; h: number } = { w: 0, h: 0 },
  content: { w: number; h: number } = { w: 0, h: 0 }
) {
  const [transform, setTransform] = useState<Transform>({ scale: initialScale, x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number } | null>(null);
  const [panning, setPanning] = useState(false);

  // 平移边界约束：内容相对视口中心偏移（grid 居中 + translate），
  // 最大偏移 = (内容尺寸 - 视口尺寸)/2，对称 clamp —— 上下左右都能拖到头。
  // （对照 YARL useZoomState.changeOffsets：maxOffset = (image*zoom - slide)/2/zoom）
  const clampTransform = useCallback(
    (t: Transform): Transform => {
      const cw = content.w * t.scale;
      const ch = content.h * t.scale;
      const maxX = Math.max(0, (cw - viewport.w) / 2);
      const maxY = Math.max(0, (ch - viewport.h) / 2);
      return {
        scale: t.scale,
        x: Math.min(maxX, Math.max(-maxX, t.x)),
        y: Math.min(maxY, Math.max(-maxY, t.y)),
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

  // 滚轮：普通 = 上下滑动查看；Ctrl/Cmd+滚轮 = 中心缩放（看图器标准交互）
  const onWheel = useCallback(
    (event: ReactWheelEvent) => {
      event.preventDefault();
      if (event.ctrlKey || event.metaKey) {
        // Ctrl+滚轮：朝中心缩放（连续步进）
        zoomAt(event.deltaY < 0 ? WHEEL_STEP : 1 / WHEEL_STEP, 0, 0);
      } else {
        // 普通滚轮：滑动（上下；shift = 左右）
        const dx = event.shiftKey ? event.deltaY : 0;
        const dy = event.shiftKey ? 0 : event.deltaY;
        setTransform((prev) => clampTransform({ ...prev, x: prev.x - dx, y: prev.y - dy }));
      }
    },
    [zoomAt, clampTransform]
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
  // 连续缩放（滚轮用）：朝中心，1.1 步进
  const zoomBy = useCallback((factor: number) => zoomAt(factor), [zoomAt]);
  // 跳到指定 scale（1:1 按钮用）：中心保持
  const zoomTo = useCallback(
    (target: number) => {
      setTransform((prev) => {
        const scale = clampScale(target);
        if (scale === prev.scale) return prev;
        const k = scale / prev.scale;
        return clampTransform({ scale, x: k * prev.x, y: k * prev.y });
      });
    },
    [clampScale, clampTransform]
  );

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
    zoomBy,
    zoomTo,
  };
}
