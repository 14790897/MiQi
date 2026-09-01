import { useEffect, useState } from 'react';
import { Check, Loader2, LogIn, Save } from 'lucide-react';
import { invalidateConfigCache } from '../../../lib/configCache';
import { sanitizeUiMessage } from '../../../lib/sanitizeUiMessage';
import { useQraftStatus } from '../../../hooks/useQraftStatus';
import { ModelSelect } from './ModelSelect';

/**
 * 模型选择面板（#835 合规收口后）。
 * 仅保留「默认模型」下拉；移除 Provider 凭据（API Key / Base URL）配置。
 * 未登录时禁用模型选择并引导去 Qraft 登录。
 */

interface ModelQuickPanelProps {
  activeModel: string;
  onSaved: () => void;
  onGoToQraft: () => void;
}

export function ModelQuickPanel({ activeModel, onSaved, onGoToQraft }: ModelQuickPanelProps) {
  const [modelValue, setModelValue] = useState(activeModel || '');
  const [saving, setSaving] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { loggedIn } = useQraftStatus();

  useEffect(() => {
    if (activeModel) setModelValue(activeModel);
  }, [activeModel]);

  const handleSave = async () => {
    if (!modelValue) {
      setError('请先选择模型');
      return;
    }
    // 模型 id 形如 "deepseek/deepseek-v4-flash"，provider 取斜杠前段；
    // 只更新默认模型，不携带 apiKey/apiBase，避免清掉内置激活。
    const providerFromModel = modelValue.split('/')[0];
    setSaving(true);
    setError(null);
    try {
      await window.miqi.providers.update(
        providerFromModel,
        undefined,
        null,
        null,
        modelValue.trim()
      );
      invalidateConfigCache();
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 2500);
      onSaved();
    } catch (err: unknown) {
      setError(sanitizeUiMessage(err instanceof Error ? err.message : String(err)));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="px-6 py-4 border-b border-[var(--border-subtle)] bg-[var(--surface)]">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-[var(--text)]">模型设置</h2>
        <span className="text-xs text-[var(--text-faint)]">
          当前默认模型：
          <span className="font-mono text-[var(--text-muted)] ml-1">{activeModel || '未设置'}</span>
        </span>
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">
            默认模型
          </label>
          {loggedIn ? (
            <ModelSelect value={modelValue} onChange={setModelValue} />
          ) : (
            <div className="flex items-center justify-between gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-3 py-2.5">
              <span className="text-sm text-[var(--text-muted)]">登录后使用平台内置模型</span>
              <button
                onClick={onGoToQraft}
                data-testid="model-quickpanel-go-login"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white transition-colors shrink-0"
              >
                <LogIn size={13} />
                去登录
              </button>
            </div>
          )}
        </div>

        {loggedIn && (
          <div className="flex items-center gap-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white transition-colors disabled:opacity-50"
            >
              {saving ? (
                <Loader2 size={14} className="animate-spin" />
              ) : savedFlash ? (
                <Check size={14} />
              ) : (
                <Save size={14} />
              )}
              {savedFlash ? '已保存' : '保存'}
            </button>
            {savedFlash && (
              <span className="text-xs text-[var(--success)]">已保存，新会话立即生效</span>
            )}
          </div>
        )}

        {error && (
          <div className="rounded-lg px-3 py-2 bg-[var(--accent-soft)] text-xs text-[var(--danger)]">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
