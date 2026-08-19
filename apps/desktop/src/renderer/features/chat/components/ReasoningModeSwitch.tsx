import React from 'react';

export type ReasoningMode = 'fast' | 'think';

interface ReasoningModeSwitchProps {
  mode: ReasoningMode;
  onChange: (mode: ReasoningMode) => void;
}

/** 极速回答 / 深度研究 单按钮切换（issue #680）。
 * 放执行策略选择器右边，交互与 ExecutionPolicySelector 一致：
 * 一个按钮显示当前模式，点击直接切换（两态无需弹菜单）。 */
export const ReasoningModeSwitch: React.FC<ReasoningModeSwitchProps> = ({ mode, onChange }) => {
  const fast = mode === 'fast';
  return (
    <button
      type="button"
      role="switch"
      aria-checked={fast}
      onClick={() => onChange(fast ? 'think' : 'fast')}
      className={[
        'flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium transition-colors',
        'outline-none focus-visible:ring-0 select-none cursor-pointer',
        fast
          ? 'text-[#fbbf24]'
          : 'text-[#a855f7]',
      ].join(' ')}
      title={fast ? '极速回答（30 秒内作答）——点击切换深度研究' : '深度研究（AI 自由发挥）——点击切换极速回答'}
      aria-label="回答模式切换"
    >
      <span aria-hidden>{fast ? '⚡' : '🧠'}</span>
      <span>{fast ? '极速回答' : '深度研究'}</span>
    </button>
  );
};
