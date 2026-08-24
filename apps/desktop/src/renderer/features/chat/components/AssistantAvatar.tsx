/** AssistantAvatar — AI 消息/卡片头像。
 * 用户明确：头像未授权改——恢复原版（蓝色渐变 + AI 文字——静态无动画）。 */
export function AssistantAvatar({ size = 24 }: { size?: number }) {
  return (
    <span
      className="rounded-[9px] flex items-center justify-center shrink-0"
      style={{
        width: size,
        height: size,
        background: 'linear-gradient(135deg,#4db2ff,#2a7de1)',
        color: '#fff',
        fontSize: Math.max(10, Math.round(size * 0.4)),
        fontWeight: 600,
        lineHeight: 1,
      }}
    >
      AI
    </span>
  );
}
