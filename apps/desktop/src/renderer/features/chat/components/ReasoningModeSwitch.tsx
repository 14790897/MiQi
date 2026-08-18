import React from 'react';

export type ReasoningMode = 'fast' | 'think';

interface ReasoningModeSwitchProps {
  mode: ReasoningMode;
  onChange: (mode: ReasoningMode) => void;
}

/** 极速回答 / 深度研究 双态分段控件（issue #680）。
 * 无背景无框、emoji 图标（延续输入框 "no text, like DeepSeek" 风格）。 */
export const ReasoningModeSwitch: React.FC<ReasoningModeSwitchProps> = ({ mode, onChange }) => {
  return (
    <div className="flex items-center gap-0.5 select-none" role="radiogroup" aria-label="回答模式">
      <button
        type="button"
        role="radio"
        aria-checked={mode === 'fast'}
        onClick={() => onChange('fast')}
        className={[
          'flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium transition-colors',
          'outline-none focus-visible:ring-0',
          mode === 'fast'
            ? 'text-[#fbbf24]'
            : 'text-[var(--text-faint)] hover:text-[var(--text-secondary)]',
        ].join(' ')}
        title="极速回答（30 秒内作答）"
        aria-label="极速回答"
      >
        <span aria-hidden>⚡</span>
        <span>极速回答</span>
      </button>
      <button
        type="button"
        role="radio"
        aria-checked={mode === 'think'}
        onClick={() => onChange('think')}
        className={[
          'flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium transition-colors',
          'outline-none focus-visible:ring-0',
          mode === 'think'
            ? 'text-[#a855f7]'
            : 'text-[var(--text-faint)] hover:text-[var(--text-secondary)]',
        ].join(' ')}
        title="深度研究（AI 自由发挥）"
        aria-label="深度研究"
      >
        <span aria-hidden>🧠</span>
        <span>深度研究</span>
      </button>
    </div>
  );
};
