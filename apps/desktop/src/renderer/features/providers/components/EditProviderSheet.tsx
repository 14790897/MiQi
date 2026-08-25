import { useState } from 'react';
import { X, Eye, EyeOff, CheckCircle, Loader2, TestTube2, Save, ChevronDown, ChevronRight } from 'lucide-react';
import { cn } from '../../../lib/utils';
import { sanitizeUiMessage } from '../../../lib/sanitizeUiMessage';
import type { ProviderInfo } from '../../../../shared/ipc';
import { PROVIDER_DISPLAY_NAMES, PROVIDER_SUGGESTED_MODELS } from '../../../lib/providers';

export function ExtraHeadersField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs text-[var(--text-faint)] hover:text-[var(--text-muted)] transition-colors"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        Extra HTTP Headers <span className="text-[var(--text-faint)]">(JSON, optional)</span>
      </button>
      {open && (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={'{"APP-Code": "your-code"}'}
          rows={3}
          className="mt-2 w-full px-3 py-2 rounded-lg text-xs bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-[var(--border-strong)] font-mono resize-none"
          spellCheck={false}
        />
      )}
    </div>
  );
}


interface EditSheetProps {
  provider: ProviderInfo;
  onClose: () => void;
  onSaved: () => void;
}

import { Modal } from '../../../components/shared';

export function EditSheet({ provider, onClose, onSaved }: EditSheetProps) {
  const [apiKey, setApiKey] = useState('');
  const [apiBase, setApiBase] = useState(provider.api_base ?? provider.default_api_base ?? '');
  const [model, setModel] = useState(provider.configured_model ?? '');
  const [extraHeadersText, setExtraHeadersText] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    message: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Built-in activation state
  // Default to built-in ("推荐") when already activated, otherwise own key.
  const [useOwnKey, setUseOwnKey] = useState(!provider.builtin_activated);
  const [activationCode, setActivationCode] = useState('');
  const [activating, setActivating] = useState(false);
  const [activationError, setActivationError] = useState<string | null>(null);
  const [activationSuccess, setActivationSuccess] = useState(provider.builtin_activated ?? false);

  const placeholderBase = provider.default_api_base || '';

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      // When in builtin mode and not yet activated, activation is required
      // before saving makes sense. If the user entered a code, activate
      // first; otherwise guide them to enter and activate.
      if (!useOwnKey && !activationSuccess && provider.builtin_available) {
        if (activationCode.trim()) {
          // Auto-activate before saving — this stores the builtin key and model
          const activated = await handleActivate();
          if (!activated) {
            setError('激活失败，请检查激活码后重试');
            return;
          }
          // handleActivate already saves provider update, but we still
          // need to persist extra headers or model override if any.
          const model_ = model || undefined;
          if (!model_) {
            onSaved();
            onClose();
            return;
          }
        } else {
          setError('请先输入激活码并点击"激活"，或切换到"我自己的API Key"模式手动配置API Key');
          return;
        }
      }
      const extraHeaders = extraHeadersText.trim()
        ? (JSON.parse(extraHeadersText) as Record<string, string>)
        : null;
      await window.miqi.providers.update(
        provider.name,
        // When switching from builtin to own-key mode, explicitly clear the
        // activation by sending an explicit API key — even if blank — so the
        // backend clears the builtin activation flag in providerActivation.
        useOwnKey && activationSuccess ? '' : (apiKey || undefined),
        apiBase || null,
        extraHeaders,
        model || undefined
      );
      // If user saved their own key while builtin was activated, reset state
      if (useOwnKey && activationSuccess) {
        setActivationSuccess(false);
      }
      onSaved();
      onClose();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes('JSON')) {
        setError('额外请求头必须是合法 JSON，例如 {"APP-Code": "xxx"}');
      } else {
        setError(msg);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleActivate = async (): Promise<boolean> => {
    if (!activationCode.trim()) {
      setActivationError('请输入激活码');
      return false;
    }
    setActivating(true);
    setActivationError(null);
    try {
      const result = await window.miqi.providers.activate(provider.name, activationCode.trim());
      if (result.activated) {
        setActivationSuccess(true);
        setUseOwnKey(false);
        // Auto-test and auto-set as default
        try {
          await window.miqi.providers.test(provider.name);
        } catch { /* test failure doesn't block activation */ }
        // Auto-activate as current provider
        const fallbackModel = (PROVIDER_SUGGESTED_MODELS[provider.name] ?? [])[0] || 'deepseek-v4-flash';
        try {
          await window.miqi.providers.update(provider.name, undefined, undefined, undefined, fallbackModel);
        } catch { /* activation as default can fail silently */ }
        onSaved();
        return true;
      } else {
        setActivationError(result.error || '激活失败');
        return false;
      }
    } catch (err: unknown) {
      const msg = sanitizeUiMessage(err instanceof Error ? err.message : String(err));
      setActivationError(msg || '激活失败，请检查激活码');
      return false;
    } finally {
      setActivating(false);
    }
  };

  const handleTest = async () => {
    if (!apiKey && !provider.configured) {
      setTestResult({ ok: false, message: '请先输入 API Key' });
      return;
    }
    setTesting(true);
    setTestResult(null);
    try {
      const result = await window.miqi.providers.test(
        provider.name,
        apiKey || undefined,
        apiBase || undefined,
        model || provider.configured_model || undefined
      );
      setTestResult({
        ok: result.ok,
        message: result.ok
          ? apiKey
            ? '连接成功。保存后请重新测试以记录验证状态。'
            : '连接成功，已记录验证状态。'
          : '连接失败',
      });
      if (result.ok && !apiKey) onSaved();
    } catch (err: unknown) {
      const message = sanitizeUiMessage(err instanceof Error ? err.message : String(err));
      setTestResult({
        ok: false,
        message,
      });
      if (!apiKey) onSaved();
    } finally {
      setTesting(false);
    }
  };

  return (
    <Modal open onOpenChange={onClose} hideClose className="max-w-[480px] w-[480px] p-0">
      <div className="w-full max-h-[80vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border-subtle)]">
          <div>
            <h2 className="text-sm font-semibold text-[var(--text)]">
              {PROVIDER_DISPLAY_NAMES[provider.name] ?? provider.display_name}
            </h2>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">{provider.name}</p>
          </div>
          <button
            onClick={onClose}
            className="text-[var(--text-faint)] hover:text-[var(--text)] transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-4 flex flex-col gap-4">
          {/* ---- API Key / Built-in activation ---- */}
          {provider.builtin_available ? (
            <div className="flex flex-col gap-3">
              <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">
                {activationSuccess ? 'API来源' : 'API Key'}
              </label>

              {/* Radio: 推荐 */}
              <label className={cn(
                'flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors',
                !useOwnKey
                  ? 'border-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_8%,transparent)]'
                  : 'border-[var(--border-subtle)] hover:border-[var(--accent)]'
              )}>
                <input
                  type="radio"
                  name="apiSource"
                  checked={!useOwnKey}
                  onChange={() => setUseOwnKey(false)}
                  className="mt-0.5 w-3.5 h-3.5 accent-[var(--accent)] shrink-0"
                />
                <div className="flex-1 min-w-0">
                  <span className="text-sm text-[var(--text)]">
                    推荐（无需API Key）
                  </span>
                  {activationSuccess ? (
                    <div className="flex items-center gap-2 mt-1">
                      <p className="flex items-center gap-1.5 text-xs text-[var(--success)]">
                        <CheckCircle size={12} />
                        已激活
                      </p>
                      <button
                        type="button"
                        onClick={async () => {
                          // Clear built-in activation: switch to own-key mode
                          // and save empty API key so the backend clears the activation flag
                          try {
                            await window.miqi.providers.update(
                              provider.name,
                              '',
                              null,
                              null,
                              undefined,
                            );
                            setActivationSuccess(false);
                            setUseOwnKey(true);
                            setApiKey('');
                          } catch (err: unknown) {
                            const msg = err instanceof Error ? err.message : String(err);
                            setError(msg || '取消激活失败');
                          }
                        }}
                        className="text-xs text-[var(--text-faint)] hover:text-[var(--danger)] underline transition-colors"
                      >
                        取消激活
                      </button>
                    </div>
                  ) : !useOwnKey ? (
                    <div className="flex flex-col gap-2 mt-2">
                      <div className="flex gap-2">
                        <input
                          type="password"
                          value={activationCode}
                          onChange={(e) => { setActivationCode(e.target.value); setActivationError(null); }}
                          onKeyDown={(e) => { if (e.key === 'Enter') handleActivate(); }}
                          placeholder="输入激活码"
                          className="flex-1 px-3 py-1.5 rounded-md text-sm bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-[var(--border-strong)] font-mono"
                          autoComplete="off"
                          spellCheck={false}
                          disabled={activating}
                        />
                        <button
                          onClick={handleActivate}
                          disabled={activating || !activationCode.trim()}
                          className="px-3 py-1.5 rounded-md bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-xs font-medium transition-colors disabled:opacity-50 shrink-0"
                        >
                          {activating ? <Loader2 size={13} className="animate-spin" /> : '激活'}
                        </button>
                      </div>
                      {activationError && (
                        <p className="text-xs text-[var(--danger)]">{activationError}</p>
                      )}
                    </div>
                  ) : null}
                </div>
              </label>

              {/* Radio: 我自己的API Key */}
              <label className={cn(
                'flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors',
                useOwnKey
                  ? 'border-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_8%,transparent)]'
                  : 'border-[var(--border-subtle)] hover:border-[var(--accent)]'
              )}>
                <input
                  type="radio"
                  name="apiSource"
                  checked={useOwnKey}
                  onChange={() => setUseOwnKey(true)}
                  className="mt-0.5 w-3.5 h-3.5 accent-[var(--accent)] shrink-0"
                />
                <div className="flex-1 min-w-0">
                  <span className="text-sm text-[var(--text)]">
                    我自己的API Key
                  </span>
                  {useOwnKey && (
                    <div className="flex flex-col gap-3 mt-3">
                      <div className="relative">
                        <input
                          type={showKey ? 'text' : 'password'}
                          value={apiKey}
                          onChange={(e) => setApiKey(e.target.value)}
                          placeholder={
                            provider.configured
                              ? '●●●●●●●●●●●● (leave blank to keep current)'
                              : provider.env_key
                                ? `Set ${provider.env_key} or enter here`
                                : 'Enter API key'
                          }
                          className="w-full px-3 py-2 pr-10 rounded-lg text-sm bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-[var(--border-strong)] font-mono"
                          autoComplete="off"
                          spellCheck={false}
                        />
                        <button
                          onClick={() => setShowKey(!showKey)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-faint)] hover:text-[var(--text-muted)]"
                          tabIndex={-1}
                          type="button"
                        >
                          {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
                        </button>
                      </div>
                      <div>
                        <label className="text-xs font-medium text-[var(--text-muted)]">
                          API Base URL <span className="font-normal text-[var(--text-faint)]">(optional)</span>
                        </label>
                        <input
                          type="url"
                          value={apiBase}
                          onChange={(e) => setApiBase(e.target.value)}
                          placeholder={placeholderBase || 'https://api.example.com/v1'}
                          className="mt-1 w-full px-3 py-2 rounded-lg text-sm bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-[var(--border-strong)] font-mono"
                          spellCheck={false}
                        />
                        {placeholderBase && (
                          <p className="text-xs text-[var(--text-faint)] mt-1">Default: {placeholderBase}</p>
                        )}
                      </div>
                      {provider.api_key_hint && (
                        <p className="text-xs text-[var(--text-faint)]">
                          当前已保存：<span className="font-mono">{provider.api_key_hint}</span>；API Key 留空将保持当前值。
                        </p>
                      )}
                      <ExtraHeadersField value={extraHeadersText} onChange={setExtraHeadersText} />
                    </div>
                  )}
                </div>
              </label>
            </div>
          ) : (
            <>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">
              API Key
            </label>
            <div className="relative">
              <input
                type={showKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={
                  provider.configured
                    ? '●●●●●●●●●●●● (leave blank to keep current)'
                    : provider.env_key
                      ? `Set ${provider.env_key} or enter here`
                      : 'Enter API key'
                }
                className="w-full px-3 py-2 pr-10 rounded-lg text-sm bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-[var(--border-strong)] font-mono"
                autoComplete="off"
                spellCheck={false}
              />
              <button
                onClick={() => setShowKey(!showKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-faint)] hover:text-[var(--text-muted)]"
                tabIndex={-1}
                type="button"
              >
                {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">
              API Base URL <span className="font-normal text-[var(--text-faint)]">(optional)</span>
            </label>
            <input
              type="url"
              value={apiBase}
              onChange={(e) => setApiBase(e.target.value)}
              placeholder={placeholderBase || 'https://api.example.com/v1'}
              className="w-full px-3 py-2 rounded-lg text-sm bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-[var(--border-strong)] font-mono"
              spellCheck={false}
            />
            {placeholderBase && (
              <p className="text-xs text-[var(--text-faint)]">Default: {placeholderBase}</p>
            )}
          </div>

          {provider.api_key_hint && (
            <p className="text-xs text-[var(--text-faint)]">
              当前已保存：<span className="font-mono">{provider.api_key_hint}</span>；API Key 留空将保持当前值。
            </p>
          )}

          <ExtraHeadersField value={extraHeadersText} onChange={setExtraHeadersText} />
            </>
          )}

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">
              默认模型 <span className="font-normal text-[var(--text-faint)]">(可选)</span>
            </label>
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder={
                (PROVIDER_SUGGESTED_MODELS[provider.name] ?? [])[0]
                  ? `例：${(PROVIDER_SUGGESTED_MODELS[provider.name] ?? [])[0]}`
                  : '输入模型名称'
              }
              className="w-full px-3 py-2 rounded-lg text-sm bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-[var(--border-strong)] font-mono"
              spellCheck={false}
            />
            {(PROVIDER_SUGGESTED_MODELS[provider.name] ?? []).length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-0.5">
                {(PROVIDER_SUGGESTED_MODELS[provider.name] ?? []).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setModel(m)}
                    className="px-2 py-0.5 rounded text-xs bg-[var(--surface-muted)] text-[var(--text-faint)] hover:text-[var(--accent)] hover:bg-[var(--accent-soft)] transition-colors font-mono"
                  >
                    {m}
                  </button>
                ))}
              </div>
            )}
            <p className="text-xs text-[var(--text-faint)]">修改此字段会更新全局默认模型</p>
          </div>

          {error && (
            <div className="rounded-lg px-3 py-2 bg-[var(--accent-soft)] text-xs text-[var(--danger)]">
              {error}
            </div>
          )}
          {testResult && (
            <div
              className={cn(
                'rounded-lg px-3 py-2 text-xs',
                testResult.ok
                  ? 'bg-[color-mix(in_srgb,var(--success)_15%,transparent)] text-[var(--success)]'
                  : 'bg-[var(--accent-soft)] text-[var(--danger)]'
              )}
            >
              {testResult.message}
            </div>
          )}
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-3 py-2 text-xs text-[var(--text-muted)] leading-relaxed">
            保存 Provider 配置后，当前运行中的会话可能仍在使用旧实例；如需确认新配置生效，请重新测试并按提示重启运行时或新建会话。
          </div>
        </div>

        <div className="flex items-center justify-between px-5 py-3 border-t border-[var(--border-subtle)]">
          <button
            onClick={handleTest}
            disabled={testing}
            className="flex items-center gap-1.5 text-sm text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors disabled:opacity-50"
          >
            {testing ? <Loader2 size={14} className="animate-spin" /> : <TestTube2 size={14} />}
            测试连接
          </button>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-sm text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
            >
              取消
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-medium transition-colors disabled:opacity-50"
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
              保存
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
