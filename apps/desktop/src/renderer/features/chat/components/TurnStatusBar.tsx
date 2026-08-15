import { useUserInput } from '../../../contexts/UserInputContext';

/**
 * TurnStatusBar — 顶栏状态联动（v5）：有 pending 确认卡时显示
 * "等待你的确认"（accent + 脉冲点），与卡片状态联动。
 *
 * 完整 turn 状态（执行中/已取消/已停止）依赖 turn_status_changed 事件流，
 * 本期先做等待确认态；legacy 路径的 turn 事件接入后扩展。
 */
export function TurnStatusBar() {
  const { pending } = useUserInput();
  const waiting = Object.keys(pending).length > 0;
  if (!waiting) return null;

  return (
    <div
      className="inline-flex items-center gap-2 rounded-full px-3 py-1 text-[11.5px] font-semibold"
      style={{
        border: '1px solid var(--accent)',
        color: 'var(--accent-hover)',
        background: 'var(--accent-soft)',
      }}
      data-testid="turn-status-waiting"
    >
      <span
        className="w-[7px] h-[7px] rounded-full"
        style={{ background: 'var(--accent)', animation: 'turnPulse 1.1s ease-in-out infinite' }}
      />
      等待你的确认
    </div>
  );
}
