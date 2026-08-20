```tsx
import { useState } from 'react';

interface PlanStep {
  name: string;
  tools: string[];
}

interface PlanEntry {
  title?: string;
  goal: string;
  steps: PlanStep[];
  permissions: string[];
  phase: string;
}

interface PlanCardProps {
  entry: PlanEntry;
  onResolve: (choiceId: 'confirm' | 'cancel') => void;
}

export function PlanCard({ entry, onResolve }: PlanCardProps) {
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  const toggleStep = (index: number) => {
    setExpanded((prev) => ({ ...prev, [index]: !prev[index] }));
  };

  return (
    <div
      data-testid="plan-card"
      className="w-full max-w-[560px] bg-white rounded-[18px] border border-black/5 shadow-[0_2px_12px_rgba(0,0,0,0.04)] p-5 flex flex-col gap-4"
    >
      {/* Header */}
      <div className="flex flex-col gap-1">
        {entry.title && (
          <h3 className="text-[15px] font-semibold text-[#1f1f1f] leading-snug">
            {entry.title}
          </h3>
        )}
        <p className="text-[13px] text-[#6b6b6b] leading-relaxed">{entry.goal}</p>
      </div>

      {/* Steps */}
      {entry.steps.length > 0 && (
        <div className="flex flex-col gap-1">
          {entry.steps.map((step, index) => {
            const isOpen = expanded[index];
            return (
              <div
                key={index}
                className="group rounded-[12px] hover:bg-[#f7f7f7] transition-colors"
              >
                <button
                  type="button"
                  onClick={() => toggleStep(index)}
                  className="w-full flex items-start gap-3 py-2.5 px-2 text-left"
                >
                  <span
                    className="mt-0.5 w-2 h-2 rounded-full shrink-0"
                    style={{
                      backgroundColor:
                        index % 4 === 0
                          ? '#2fb27b'
                          : index % 4 === 1
                          ? '#4db2ff'
                          : index % 4 === 2
                          ? '#f5a623'
                          : '#a259ff',
                    }}
                  />
                  <span className="flex-1 text-[13.5px] text-[#1f1f1f] leading-snug">
                    {step.name}
                  </span>
                  {step.tools.length > 0 && (
                    <span className="text-[11px] text-[#9a9a9a] shrink-0 mt-0.5">
                      {isOpen ? '收起' : '展开'}
                    </span>
                  )}
                </button>

                {isOpen && step.tools.length > 0 && (
                  <div className="px-7 pb-2.5 flex flex-wrap gap-1.5">
                    {step.tools.map((tool, tIndex) => (
                      <span
                        key={tIndex}
                        className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] text-[#6b6b6b] bg-[#f0f0f0]"
                      >
                        {tool}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Permissions */}
      {entry.permissions.length > 0 && (
        <div className="flex flex-col gap-2 px-1">
          <span className="text-[11.5px] font-medium text-[#9a9a9a] uppercase tracking-wide">
            所需权限
          </span>
          <div className="flex flex-wrap gap-1.5">
            {entry.permissions.map((permission, index) => (
              <span
                key={index}
                className="inline-flex items-center px-2.5 py-1 rounded-full text-[11.5px] text-[#5a5a5a] bg-[#f5f5f5] border border-black/5"
              >
                {permission}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Footer status */}
      <div className="flex items-center justify-between gap-3 pt-1">
        <span className="text-[11.5px] text-[#9a9a9a]">
          请确认以上执行计划
        </span>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onResolve('cancel')}
            className="px-4 py-2 rounded-full text-[13px] font-medium text-[#5a5a5a] bg-transparent hover:bg-[#f2f2f2] transition-colors"
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => onResolve('confirm')}
            className="px-5 py-2 rounded-full text-[13px] font-medium text-white bg-[#1f1f1f] hover:bg-[#000] transition-colors shadow-sm"
          >
            开始执行
          </button>
        </div>
      </div>
    </div>
  );
}
```