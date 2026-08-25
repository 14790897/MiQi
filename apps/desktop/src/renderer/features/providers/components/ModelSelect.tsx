import { useEffect, useMemo, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { ModelInfo } from '../../../../shared/ipc';
import { PROVIDER_DISPLAY_NAMES } from '../../../lib/providers';

/**
 * 常用模型下拉 + 自定义输入（issue #788）。
 * 预设清单来自后端 model/list（model_catalog.py，覆盖
 * context_runtime._MODEL_MAX_INPUT_TOKENS 常用模型）；选择后自动填充
 * "provider/model-name" 格式。
 */

const CUSTOM_VALUE = '__custom__';

// 后端不可用（运行时未启动）时的兜底预设，保证下拉始终可用
export const FALLBACK_MODEL_PRESETS: ModelInfo[] = [
  { id: 'deepseek/deepseek-chat', name: 'DeepSeek Chat', provider: 'deepseek', providerDisplayName: 'DeepSeek', hidden: false, default: false },
  { id: 'deepseek/deepseek-reasoner', name: 'DeepSeek Reasoner', provider: 'deepseek', providerDisplayName: 'DeepSeek', hidden: false, default: false },
  { id: 'deepseek/deepseek-v4-flash', name: 'DeepSeek V4 Flash', provider: 'deepseek', providerDisplayName: 'DeepSeek', hidden: false, default: false },
  { id: 'openai/gpt-4o', name: 'GPT-4o', provider: 'openai', providerDisplayName: 'OpenAI', hidden: false, default: false },
  { id: 'openai/gpt-4o-mini', name: 'GPT-4o Mini', provider: 'openai', providerDisplayName: 'OpenAI', hidden: false, default: false },
  { id: 'anthropic/claude-sonnet-4-5', name: 'Claude Sonnet 4.5', provider: 'anthropic', providerDisplayName: 'Anthropic', hidden: false, default: false },
  { id: 'anthropic/claude-opus-4-5', name: 'Claude Opus 4.5', provider: 'anthropic', providerDisplayName: 'Anthropic', hidden: false, default: false },
  { id: 'gemini/gemini-2.5-pro', name: 'Gemini 2.5 Pro', provider: 'gemini', providerDisplayName: 'Google Gemini', hidden: false, default: false },
  { id: 'dashscope/qwen-max', name: 'Qwen Max', provider: 'dashscope', providerDisplayName: 'DashScope · 通义千问', hidden: false, default: false },
  { id: 'moonshot/kimi-k2.5', name: 'Kimi K2.5', provider: 'moonshot', providerDisplayName: 'Moonshot · 月之暗面', hidden: false, default: false },
  { id: 'zhipu/glm-4', name: 'GLM-4', provider: 'zhipu', providerDisplayName: 'Zhipu AI · 智谱', hidden: false, default: false },
];

function displayName(provider: string): string {
  return PROVIDER_DISPLAY_NAMES[provider] ?? provider;
}

function groupPresets(presets: ModelInfo[]): { provider: string; label: string; models: ModelInfo[] }[] {
  const map = new Map<string, ModelInfo[]>();
  for (const m of presets) {
    if (m.hidden) continue;
    const arr = map.get(m.provider) ?? [];
    arr.push(m);
    map.set(m.provider, arr);
  }
  return [...map.entries()].map(([provider, models]) => ({
    provider,
    label: models[0]?.providerDisplayName || displayName(provider),
    models,
  }));
}

interface ModelSelectProps {
  value: string;
  onChange: (v: string) => void;
  /** 外部传入的预设（如已加载的 providers 列表）；默认走后端 model/list */
  presets?: ModelInfo[];
  placeholder?: string;
}

export function ModelSelect({ value, onChange, presets, placeholder }: ModelSelectProps) {
  const [loaded, setLoaded] = useState<ModelInfo[] | null>(null);

  useEffect(() => {
    let alive = true;
    window.miqi.models
      .list()
      .then((r) => {
        if (alive) setLoaded(r.models ?? []);
      })
      .catch(() => {
        if (alive) setLoaded([]);
      });
    return () => {
      alive = false;
    };
  }, []);

  const all = useMemo(() => {
    const source = loaded === null ? null : loaded.length > 0 ? loaded : null;
    return source ?? presets ?? FALLBACK_MODEL_PRESETS;
  }, [loaded, presets]);

  const groups = useMemo(() => groupPresets(all), [all]);
  const isPreset = all.some((m) => m.id === value);

  return (
    <div className="flex flex-col gap-1.5">
      <div className="relative">
        <select
          value={isPreset ? value : CUSTOM_VALUE}
          onChange={(e) => {
            const v = e.target.value;
            if (v === CUSTOM_VALUE) {
              // 切到自定义：保留当前值，让用户在输入框里继续编辑
              onChange(value);
            } else {
              onChange(v);
            }
          }}
          className="w-full appearance-none px-3 py-2 pr-9 rounded-lg text-sm bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] focus:outline-none focus:border-[var(--border-strong)] font-mono cursor-pointer"
        >
          {groups.map((g) => (
            <optgroup key={g.provider} label={g.label}>
              {g.models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.id}
                </option>
              ))}
            </optgroup>
          ))}
          <option value={CUSTOM_VALUE}>自定义模型…</option>
        </select>
        <ChevronDown
          size={14}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-faint)] pointer-events-none"
        />
      </div>
      {!isPreset && (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder ?? 'provider/model-name'}
          className="w-full px-3 py-2 rounded-lg text-sm bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-[var(--border-strong)] font-mono"
          spellCheck={false}
        />
      )}
    </div>
  );
}
