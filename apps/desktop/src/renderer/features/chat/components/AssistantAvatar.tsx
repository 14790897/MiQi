/** AssistantAvatar — AI 消息/卡片头像（柔和渐变圆 + 光点——用户拍板版）。
 * CodeRabbit: 3 处重复 → 提取共享组件（size 可控）。 */
export function AssistantAvatar({ size = 24 }: { size?: number }) {
  const inner = Math.max(8, Math.round(size * 0.33));
  return (
    <span
      className="rounded-full flex items-center justify-center shrink-0"
      style={{
        width: size,
        height: size,
        background: 'linear-gradient(135deg,#e3edf9,#e9e3f7)',
      }}
    >
      <span
        className="rounded-full"
        style={{
          width: inner,
          height: inner,
          background: 'linear-gradient(135deg,#8fb8e8,#a89ad9)',
        }}
      />
    </span>
  );
}
