import { useEffect, useMemo, useState } from 'react';
import {
  Check,
  CheckCircle2,
  ChevronDown,
  Eye,
  EyeOff,
  Loader2,
  Save,
  TestTube2,
  XCircle,
} from 'lucide-react';
import { cn } from '../../../lib/utils';
import { invalidateConfigCache } from '../../../lib/configCache';
import { sanitizeUiMessage } from '../../../lib/sanitizeUiMessage';
import type { ProviderInfo } from '../../../../shared/ipc';
import { PROVIDER_DISPLAY_NAMES } from '../../../lib/providers';
import { ModelSelect } from './ModelSelect';

/**
 * 模型与 Provider 配置一体化面板（issue #788）。
 * 聚合：当前模型展示、模型切换（常用模型预设下拉 + 自定义）、
 * Provider 凭据（API Key / Base URL）配置、连通性测试、保存即生效。
 * 首次进入或未配置 Provider 时显示 3 步引导：选模型 → 填 Key → 测试保存。
 */

const GUIDE_SEEN_KEY = 'miqi-model-guide-seen';

function providerDisplayName(name: string): string {
  return PROVIDER_DISPLAY_NAMES[name] ?? name;
}

function bareModel(model: string): string {
  const slash = model.indexOf('/');
  return slash > 0 ? model.slice(slash + 1) : model;
}

interface ModelQuickPanelProps {
  providers: ProviderInfo[];
  activeModel: string;
  activeProvider: string | null;
  onSaved: () => void;
}

export function ModelQuickPanel({
  providers,
  activeModel,
  activeProvider,
  onSaved,
}: ModelQuickPanelProps) {
  const [modelValue, setModelValue] = useState(activeModel || '');
  const [providerName, setProviderName] = useState(activeProvider ?? 'deepseek');
  const [apiKey, setApiKey] = useState('');
  const [apiBase, setApiBase] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedFlash, setSavedFlash] = useState(false);
  const [guideDismissed, setGuideDismissed] = useState(() => {
    try {
      return localStorage.getItem(GUIDE_SEEN_KEY) === '1';
    } catch {
      return false;
    }
  });

  // 外部（列表启用/编辑保存）变化时同步面板
  useEffect(() => {
    if (activeModel) setModelValue(activeModel);
    if (activeProvider) setProviderName(activeProvider);
  }, [activeModel, activeProvider]);

  const currentProvider = useMemo(
    () => providers.find((p) => p.name === providerName) ?? null,
    [providers, providerName]
  );
  const providerConfigured = currentProvider?.configured ?? false;
  const providerBase = currentProvider?.api_base ?? currentProvider?.default_api_base ?? '';

  const anyConfigured = providers.some((p) => p.configured);
  const showGuide = !guideDismissed && !anyConfigured;

  // 3 步引导：① 选模型 → ② 填 Key → ③ 测试保存（每步完成自动进入下一步）
  const guideStep = useMemo(() => {
    if (!modelValue) return 1;
    if (!apiKey) return 2;
    if (!(testResult?.ok && savedFlash)) return 3;
    return 4;
  }, [modelValue, apiKey, testResult, savedFlash]);

  useEffect(() => {
    if (showGuide && guideStep === 4) {
      const t = setTimeout(() => {
        localStorage.setItem(GUIDE_SEEN_KEY, '1');
        setGuideDismissed(true);
      }, 1500);
      return () => clearTimeout(t);
    }
  }, [showGuide, guideStep]);

  const handleModelChange = (v: string) => {
    setModelValue(v);
    setTestResult(null);
    const slash = v.indexOf('/');
    if (slash > 0) {
      const p = v.slice(0, slash);
      if (providers.some((pr) => pr.name === p)) setProviderName(p);
    }
  };

  const handleProviderChange = (v: string) => {
    setProviderName(v);
    setTestResult(null);
    setApiKey('');
    setApiBase('');
    setError(null);
  };

  const handleTest = async () => {
    if (!providerName) {
      setError('请先选择 Provider');
      return;
    }
    if (!apiKey && !providerConfigured) {
      setError('请先填写 API Key（或先保存 Provider 配置）');
      return;
    }
    setTesting(true);
    setTestResult(null);
    setError(null);
    try {
      const r = await window.miqi.providers.test(
        providerName,
        apiKey || undefined,
        apiBase || undefined,
        bareModel(modelValue) || undefined
      );
      setTestResult({
        ok: r.ok,
        message: r.ok ? '连接成功，API Key 有效 ✓' : '连接失败，请检查 API Key、Base URL 与网络',
      });
      if (r.ok) onSaved();
    } catch (err: unknown) {
      const message = sanitizeUiMessage(err instanceof Error ? err.message : String(err));
      setTestResult({ ok: false, message: message || '连接失败，请检查 API Key 与网络' });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    if (!providerName) {
      setError('请先选择 Provider');
      return;
    }
    if (!modelValue.trim()) {
      setError('请先选择或输入模型');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await window.miqi.providers.update(
        providerName,
        apiKey || undefined,
        apiBase || null,
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
      {/* ---- 3 步引导 ---- */}
      {showGuide && (
        <div className="mb-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-muted)]/40 px-4 py-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-[var(--text)]">
              快速配置引导 · 3 步完成模型接入
            </p>
            <button
              onClick={() => {
                localStorage.setItem(GUIDE_SEEN_KEY, '1');
                setGuideDismissed(true);
              }}
              className="text-xs text-[var(--text-faint)] hover:text-[var(--text-muted)] transition-colors"
            >
              跳过
            </button>
          </div>
          <div className="flex items-center gap-2 mt-2.5">
            {[
              { n: 1, label: '选择模型' },
              { n: 2, label: '填写 API Key' },
              { n: 3, label: '测试并保存' },
            ].map((s, i) => {
              const done = guideStep > s.n;
              const active = guideStep === s.n;
              return (
                <div key={s.n} className="flex items-center gap-2 min-w-0">
                  {i > 0 && (
                    <div
                      className={cn(
                        'h-px w-5 shrink-0',
                        guideStep > s.n - 1 ? 'bg-[var(--success)]' : 'bg-[var(--border)]'
                      )}
                    />
                  )}
                  <span
                    className={cn(
                      'flex items-center gap-1.5 text-xs rounded-full px-2.5 py-1 transition-colors',
                      done && 'text-[var(--success)]',
                      active &&
                        'bg-[color-mix(in_srgb,var(--accent)_15%,transparent)] text-[var(--accent)] font-medium',
                      !done && !active && 'text-[var(--text-faint)]'
                    )}
                  >
                    {done ? (
                      <CheckCircle2 size={12} />
                    ) : (
                      <span
                        className={cn(
                          'w-4 h-4 rounded-full inline-flex items-center justify-center text-[10px] shrink-0',
                          active
                            ? 'bg-[var(--accent)] text-white'
                            : 'bg-[var(--surface-muted)] text-[var(--text-faint)]'
                        )}
                      >
                        {s.n}
                      </span>
                    )}
                    {s.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-[var(--text)]">模型与连接设置</h2>
        <span className="text-xs text-[var(--text-faint)]">
          当前默认模型：
          <span className="font-mono text-[var(--text-muted)] ml-1">{activeModel || '未设置'}</span>
        </span>
      </div>

      <div className="flex flex-col gap-3">
        {/* ---- 模型选择 ---- */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">
            默认模型
          </label>
          <ModelSelect value={modelValue} onChange={handleModelChange} />
        </div>

        {/* ---- Provider 与凭据 ---- */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">
            Provider
          </label>
          <div className="relative">
            <select
              value={providerName}
              onChange={(e) => handleProviderChange(e.target.value)}
              className="w-full appearance-none px-3 py-2 pr-9 rounded-lg text-sm bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] focus:outline-none focus:border-[var(--border-strong)] cursor-pointer"
            >
              {providers.map((p) => (
                <option key={p.name} value={p.name}>
                  {providerDisplayName(p.name)}
                  {p.configured ? ' ✓ 已配置' : ''}
                </option>
              ))}
            </select>
            <ChevronDown
              size={14}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-faint)] pointer-events-none"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">
              API Key
            </label>
            <div className="relative">
              <input
                type={showKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => {
                  setApiKey(e.target.value);
                  setTestResult(null);
                }}
                placeholder={providerConfigured ? '●●●●●●●●●●●●（留空保持不变）' : '输入 API Key'}
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
            {currentProvider?.builtin_available && !currentProvider.builtin_activated && (
              <p className="text-xs text-[var(--text-faint)]">
                💡 {providerDisplayName(providerName)}{' '}
                内置支持，也可在下方列表中点击「编辑」使用企业激活码
              </p>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">
              API Base URL <span className="font-normal text-[var(--text-faint)]">(可选)</span>
            </label>
            <input
              type="url"
              value={apiBase}
              onChange={(e) => {
                setApiBase(e.target.value);
                setTestResult(null);
              }}
              placeholder={providerBase || 'https://api.example.com/v1'}
              className="w-full px-3 py-2 rounded-lg text-sm bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-[var(--border-strong)] font-mono"
              spellCheck={false}
            />
            {providerBase && (
              <p className="text-xs text-[var(--text-faint)]">默认：{providerBase}</p>
            )}
          </div>
        </div>

        {/* ---- 操作 ---- */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleTest}
            disabled={testing || saving}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium border transition-colors disabled:opacity-50"
            style={{
              borderColor: 'color-mix(in srgb, var(--border-strong) 60%, transparent)',
              background: 'var(--surface-muted)',
              color: 'var(--text-muted)',
            }}
          >
            {testing ? <Loader2 size={14} className="animate-spin" /> : <TestTube2 size={14} />}
            测试连接
          </button>
          <button
            onClick={handleSave}
            disabled={saving || testing}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white transition-colors disabled:opacity-50"
          >
            {saving ? (
              <Loader2 size={14} className="animate-spin" />
            ) : savedFlash ? (
              <Check size={14} />
            ) : (
              <Save size={14} />
            )}
            {savedFlash ? '已保存' : '保存并启用'}
          </button>
          {savedFlash && (
            <span className="text-xs text-[var(--success)]">已保存，新会话立即生效，无需重启</span>
          )}
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
            {testResult.ok ? (
              <CheckCircle2 size={13} className="inline mr-1" />
            ) : (
              <XCircle size={13} className="inline mr-1" />
            )}
            {testResult.message}
          </div>
        )}

        <p className="text-xs text-[var(--text-faint)] leading-relaxed">
          保存后新会话立即生效，无需重启；正在进行的会话继续使用旧配置。高级用户可直接编辑配置文件，或在下方列表中逐项管理
          Provider（激活码、额外请求头等）。
        </p>
      </div>
    </div>
  );
}
