/** AssistantAvatar — AI 消息/卡片头像。
 * 用户明确：恢复原本（AgentAvatar——圆形 accent 底 + "A" 字——不叫 AI）。 */
export function AssistantAvatar({ size = 24 }: { size?: number }) {
  return (
    <span
      className="rounded-full flex items-center justify-center shrink-0 font-bold text-white"
      style={{
        width: size,
        height: size,
        background: 'var(--accent)',
        fontSize: Math.max(10, Math.round(size * 0.42)),
        lineHeight: 1,
      }}
    >
      A
    </span>
  );
}
