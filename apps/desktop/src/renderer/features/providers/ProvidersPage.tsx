import { useState, useEffect, useCallback } from 'react';
import { useRestartRequired } from '../../contexts/RestartRequiredContext';
import {
  Zap,
  Server,
  Globe,
  HardDrive,
  CheckCircle,
  Circle,
  AlertCircle,
  XCircle,
  Edit2,
  TestTube2,
  Eye,
  EyeOff,
  Save,
  X,
  Loader2,
  ChevronDown,
  ChevronRight,
  Play,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { sanitizeUiMessage } from '../../lib/sanitizeUiMessage';
import type { ProviderInfo } from '../../../shared/ipc';

const DOMESTIC_NAMES = new Set([
  'dashscope',
  'zhipu',
  'moonshot',
  'minimax',
  'siliconflow',
  'volcengine',
]);

function getCategory(p: ProviderInfo): 'gateway' | 'domestic' | 'local' | 'international' {
  if (p.is_local) return 'local';
  if (p.is_gateway) return 'gateway';
  if (DOMESTIC_NAMES.has(p.name)) return 'domestic';
  return 'international';
}

type VerificationStatus = NonNullable<ProviderInfo['verification_status']>;

function getVerificationStatus(provider: ProviderInfo): VerificationStatus {
  if (!provider.configured) return 'missing';
  return provider.verification_status ?? 'unverified';
}

function getStatusMeta(provider: ProviderInfo) {
  const status = getVerificationStatus(provider);
  if (status === 'success') {
    return {
      label: '验证成功',
      icon: CheckCircle,
      tone: 'success',
      title: provider.verified_at ? `上次验证：${provider.verified_at}` : '已通过连接测试',
    };
  }
  if (status === 'failed') {
    return {
      label: '验证失败',
      icon: XCircle,
      tone: 'danger',
      title: provider.verification_message ?? '最近一次连接测试失败',
    };
  }
  if (status === 'unverified') {
    return {
      label: '已填写，未验证',
      icon: AlertCircle,
      tone: 'warning',
      title: '已保存配置，但还没有通过连接测试',
    };
  }
  return {
    label: '未填写',
    icon: Circle,
    tone: 'muted',
    title: '还没有填写 API Key 或 API Base',
  };
}

function statusClass(tone: string) {
  if (tone === 'success') return 'text-[var(--success)]';
  if (tone === 'danger') return 'text-[var(--danger)]';
  if (tone === 'warning') return 'text-[var(--warning)]';
  return 'text-[var(--border)]';
}

function statusBadgeClass(tone: string) {
  if (tone === 'success') {
    return 'bg-[color-mix(in_srgb,var(--success)_15%,transparent)] text-[var(--success)]';
  }
  if (tone === 'danger') {
    return 'bg-[color-mix(in_srgb,var(--danger)_15%,transparent)] text-[var(--danger)]';
  }
  if (tone === 'warning') {
    return 'bg-[color-mix(in_srgb,var(--warning)_15%,transparent)] text-[var(--warning)]';
  }
  return 'bg-[var(--surface-muted)] text-[var(--text-faint)]';
}

interface EditSheetProps {
  provider: ProviderInfo;
  onClose: () => void;
  onSaved: () => void;
}

function EditSheet({ provider, onClose, onSaved }: EditSheetProps) {
  const { markRestartRequired } = useRestartRequired();
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

  const placeholderBase = provider.default_api_base || '';

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const extraHeaders = extraHeadersText.trim()
        ? (JSON.parse(extraHeadersText) as Record<string, string>)
        : null;
      await window.miqi.providers.update(
        provider.name,
        apiKey || undefined,
        apiBase || null,
        extraHeaders,
        model || undefined
      );
      onSaved();
      markRestartRequired();
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-[var(--surface-elevated)] border border-[var(--border)] rounded-xl shadow-xl w-[480px] max-h-[80vh] overflow-y-auto">
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
                className="w-full px-3 py-2 pr-10 rounded-lg text-sm bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-[var(--accent)] font-mono"
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
              className="w-full px-3 py-2 rounded-lg text-sm bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-[var(--accent)] font-mono"
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
              className="w-full px-3 py-2 rounded-lg text-sm bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-[var(--accent)] font-mono"
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
    </div>
  );
}

function ExtraHeadersField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
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
          className="mt-2 w-full px-3 py-2 rounded-lg text-xs bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-[var(--accent)] font-mono resize-none"
          spellCheck={false}
        />
      )}
    </div>
  );
}

const PROVIDER_DISPLAY_NAMES: Record<string, string> = {
  // 网关
  openrouter: 'OpenRouter',
  aihubmix: 'AiHubMix',
  siliconflow: 'SiliconFlow · 硅基流动',
  volcengine: 'VolcEngine · 火山引擎',
  custom: '自定义端点',
  // 国际
  anthropic: 'Anthropic',
  openai: 'OpenAI',
  deepseek: 'DeepSeek',
  gemini: 'Google Gemini',
  groq: 'Groq',
  // 国内
  zhipu: 'Zhipu AI · 智谱',
  dashscope: 'DashScope · 通义千问',
  moonshot: 'Moonshot · 月之暗面',
  minimax: 'MiniMax',
  // 本地
  ollama_cloud: 'Ollama Cloud',
  ollama_local: 'Ollama Local',
  vllm: 'vLLM / 本地部署',
};

const PROVIDER_SUGGESTED_MODELS: Record<string, string[]> = {
  openrouter: ['anthropic/claude-opus-4-5', 'google/gemini-2.5-pro', 'deepseek/deepseek-r1'],
  aihubmix: ['claude-opus-4-5', 'gpt-4o', 'gemini-2.5-pro'],
  siliconflow: ['Qwen/Qwen3-235B-A22B', 'deepseek-ai/DeepSeek-V3', 'deepseek-ai/DeepSeek-R1'],
  volcengine: ['doubao-pro-32k', 'doubao-lite-32k', 'doubao-1-5-pro-32k'],
  anthropic: ['claude-opus-4-5', 'claude-sonnet-4-5', 'claude-haiku-4-5'],
  openai: ['gpt-4o', 'gpt-4o-mini', 'o3', 'o4-mini'],
  deepseek: ['deepseek-v4-flash', 'deepseek-v4-pro', 'deepseek-chat', 'deepseek-reasoner'],
  gemini: ['gemini-2.5-pro', 'gemini-2.0-flash', 'gemini-2.5-flash'],
  groq: ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'moonshard-whisper-large-v3'],
  zhipu: ['glm-4-plus', 'glm-z1-flash', 'glm-4-long'],
  dashscope: ['qwen-max', 'qwen-plus', 'qwen-turbo', 'qwen3-235b-a22b'],
  moonshot: ['kimi-k2.5', 'moonshot-v1-32k', 'moonshot-v1-128k'],
  minimax: ['MiniMax-Text-01', 'abab6.5s-chat'],
  ollama_local: ['llama3.2', 'qwen2.5:7b', 'deepseek-r1:7b'],
  ollama_cloud: ['llama3.2', 'qwen2.5'],
  vllm: [],
  custom: [],
};

interface ProviderRowProps {
  provider: ProviderInfo;
  onEdit: (p: ProviderInfo) => void;
  onTest: (p: ProviderInfo) => void;
  onActivate: (p: ProviderInfo) => void;
  testingName: string | null;
  activatingName: string | null;
  activeProvider?: string | null;
}

function ProviderRow({
  provider,
  onEdit,
  onTest,
  onActivate,
  testingName,
  activatingName,
  activeProvider,
}: ProviderRowProps) {
  const label = PROVIDER_DISPLAY_NAMES[provider.name] ?? provider.display_name;
  const isTesting = testingName === provider.name;
  const isActivating = activatingName === provider.name;
  const statusMeta = getStatusMeta(provider);
  const StatusIcon = statusMeta.icon;
  const isActive = provider.name === activeProvider;

  return (
    <div
      className={cn(
        'flex items-center gap-3 px-4 py-2.5 hover:bg-[var(--surface-muted)] transition-colors group',
        isActive && 'bg-[var(--accent-soft)]/40'
      )}
    >
      <div className={cn('shrink-0', statusClass(statusMeta.tone))} title={statusMeta.title}>
        <StatusIcon size={14} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm text-[var(--text)] truncate">{label}</span>
          {isActive && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--accent)] text-white shrink-0">
              当前使用
            </span>
          )}
        </div>
        {provider.configured && (
          <div className="flex items-center gap-2 mt-0.5">
            {provider.api_key_hint && (
              <span className="text-xs text-[var(--text-faint)] font-mono">
                {provider.api_key_hint}
              </span>
            )}
            {provider.configured_model && (
              <span className="text-xs text-[var(--text-faint)] truncate max-w-[160px]">
                模型：{provider.configured_model}
              </span>
            )}
          </div>
        )}
      </div>
      <span
        className={cn(
          'text-xs px-2 py-0.5 rounded-full shrink-0',
          provider.is_gateway
            ? 'bg-[color-mix(in_srgb,var(--info)_15%,transparent)] text-[var(--info)]'
            : provider.is_local
              ? 'bg-[color-mix(in_srgb,var(--warning)_15%,transparent)] text-[var(--warning)]'
              : 'bg-[var(--surface-muted)] text-[var(--text-muted)]'
        )}
      >
        {provider.is_gateway ? '网关' : provider.is_local ? '本地' : provider.provider_type}
      </span>
      <span
        className={cn(
          'text-xs px-2 py-0.5 rounded-full shrink-0',
          statusBadgeClass(statusMeta.tone)
        )}
        title={statusMeta.title}
      >
        {statusMeta.label}
      </span>
      <div className="flex items-center gap-1 shrink-0">
        {provider.configured && !isActive && (
          <button
            onClick={() => onActivate(provider)}
            disabled={isActivating}
            title="启用为当前模型"
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium border transition-colors disabled:opacity-50"
            style={{
              borderColor: 'color-mix(in srgb, var(--info) 45%, transparent)',
              background: 'color-mix(in srgb, var(--info) 10%, transparent)',
              color: 'var(--info)',
            }}
          >
            {isActivating ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Play size={13} />
            )}
            启用
          </button>
        )}
        {isActive && (
          <span
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium shrink-0"
            style={{
              background: 'color-mix(in srgb, var(--success) 18%, transparent)',
              color: 'var(--success)',
              border: '1px solid color-mix(in srgb, var(--success) 35%, transparent)',
            }}
          >
            <CheckCircle size={13} />
            使用中
          </span>
        )}
        <button
          onClick={() => onTest(provider)}
          disabled={isTesting}
          title="测试连接"
          className="p-1.5 rounded-md text-[var(--text-faint)] hover:text-[var(--accent)] hover:bg-[var(--accent-soft)] transition-colors disabled:opacity-40"
        >
          {isTesting ? <Loader2 size={14} className="animate-spin" /> : <TestTube2 size={14} />}
        </button>
        <button
          onClick={() => onEdit(provider)}
          title="编辑 Provider"
          className="p-1.5 rounded-md text-[var(--text-faint)] hover:text-[var(--text)] hover:bg-[var(--surface-muted)] transition-colors"
        >
          <Edit2 size={14} />
        </button>
      </div>
    </div>
  );
}

interface CategorySectionProps {
  title: string;
  icon: React.ReactNode;
  providers: ProviderInfo[];
  onEdit: (p: ProviderInfo) => void;
  onTest: (p: ProviderInfo) => void;
  onActivate: (p: ProviderInfo) => void;
  testingName: string | null;
  activatingName: string | null;
  activeProvider?: string | null;
}

function CategorySection({
  title,
  icon,
  providers,
  onEdit,
  onTest,
  onActivate,
  testingName,
  activatingName,
  activeProvider,
}: CategorySectionProps) {
  if (providers.length === 0) return null;
  const filledCount = providers.filter((p) => p.configured).length;
  return (
    <div>
      <div className="flex items-center gap-2 px-4 py-2 text-xs font-semibold uppercase tracking-widest text-[var(--text-faint)] border-b border-[var(--border-subtle)]">
        {icon}
        {title}
        <span className="ml-auto font-normal normal-case tracking-normal">
          {filledCount}/{providers.length} 已填写
        </span>
      </div>
      <div className="divide-y divide-[var(--border-subtle)]">
        {providers.map((p) => (
          <ProviderRow
            key={p.name}
            provider={p}
            onEdit={onEdit}
            onTest={onTest}
            onActivate={onActivate}
            testingName={testingName}
            activatingName={activatingName}
            activeProvider={activeProvider}
          />
        ))}
      </div>
    </div>
  );
}

export function ProvidersPage() {
  const { markRestartRequired } = useRestartRequired();
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [editProvider, setEditProvider] = useState<ProviderInfo | null>(null);
  const [testingName, setTestingName] = useState<string | null>(null);
  const [activatingName, setActivatingName] = useState<string | null>(null);
  const [activeModel, setActiveModel] = useState('');
  const [activeProvider, setActiveProvider] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await window.miqi.providers.list();
      setProviders(result.providers);
      setActiveModel(result.active_model ?? '');
      setActiveProvider(result.active_provider ?? null);
    } catch {
      // silent — runtime may not be running
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleTest = async (p: ProviderInfo) => {
    if (!p.configured) {
      return;
    }
    setTestingName(p.name);
    try {
      await window.miqi.providers.test(
        p.name,
        undefined,
        p.api_base ?? undefined,
        p.configured_model || undefined
      );
    } catch {
      // providers.test persists failed verification for saved configs.
    } finally {
      setTestingName(null);
      void load();
    }
  };

  const handleActivate = async (p: ProviderInfo) => {
    if (!p.configured) return;
    const fallbackModel = (PROVIDER_SUGGESTED_MODELS[p.name] ?? [])[0];
    const model = p.configured_model || fallbackModel;
    if (!model) {
      setEditProvider(p);
      return;
    }
    setActivatingName(p.name);
    try {
      await window.miqi.providers.update(
        p.name,
        undefined,
        undefined,
        undefined,
        model
      );
      markRestartRequired();
      await load();
    } finally {
      setActivatingName(null);
    }
  };

  const gateways = providers.filter((p) => getCategory(p) === 'gateway');
  const international = providers.filter((p) => getCategory(p) === 'international');
  const domestic = providers.filter((p) => getCategory(p) === 'domestic');
  const local = providers.filter((p) => getCategory(p) === 'local');
  const filledCount = providers.filter((p) => p.configured).length;
  const verifiedCount = providers.filter((p) => getVerificationStatus(p) === 'success').length;
  const activeProviderLabel = activeProvider
    ? (PROVIDER_DISPLAY_NAMES[activeProvider] ?? activeProvider)
    : '未匹配';
  const activeProviderInfo = activeProvider
    ? providers.find((provider) => provider.name === activeProvider)
    : null;

  return (
    <div className="flex flex-col h-full bg-[var(--background)]">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border-subtle)] bg-[var(--surface)] shrink-0">
        <div>
          <h1 className="text-base font-semibold text-[var(--text)]">模型提供商</h1>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            {loading
              ? '加载中…'
              : `${filledCount} / ${providers.length} 已填写，${verifiedCount} 个验证成功`}
          </p>
          {!loading && (
            <p className="text-xs text-[var(--text-faint)] mt-1">
              当前默认模型：{activeModel || '未设置'} · 匹配 Provider：{activeProviderLabel}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {activeProviderInfo && (
            <button
              onClick={() => setEditProvider(activeProviderInfo)}
              className="text-xs text-[var(--accent)] hover:text-[var(--accent-hover)] transition-colors px-2 py-1 rounded bg-[var(--accent-soft)]"
            >
              编辑当前模型
            </button>
          )}
          <button
            onClick={load}
            className="text-xs text-[var(--text-faint)] hover:text-[var(--text-muted)] transition-colors px-2 py-1 rounded"
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center h-40 text-sm text-[var(--text-faint)]">
            <Loader2 size={16} className="animate-spin mr-2" /> 正在加载…
          </div>
        ) : providers.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 gap-2 text-sm text-[var(--text-faint)]">
            <Server size={24} />
            <span>MiQi 运行时未启动</span>
          </div>
        ) : (
          <div className="divide-y divide-[var(--border-subtle)]">
            <CategorySection
              title="网关"
              icon={<Globe size={12} />}
              providers={gateways}
              onEdit={setEditProvider}
              onTest={handleTest}
              onActivate={handleActivate}
              testingName={testingName}
              activatingName={activatingName}
              activeProvider={activeProvider}
            />
            <CategorySection
              title="国际"
              icon={<Zap size={12} />}
              providers={international}
              onEdit={setEditProvider}
              onTest={handleTest}
              onActivate={handleActivate}
              testingName={testingName}
              activatingName={activatingName}
              activeProvider={activeProvider}
            />
            <CategorySection
              title="国内"
              icon={<Server size={12} />}
              providers={domestic}
              onEdit={setEditProvider}
              onTest={handleTest}
              onActivate={handleActivate}
              testingName={testingName}
              activatingName={activatingName}
              activeProvider={activeProvider}
            />
            <CategorySection
              title="本地"
              icon={<HardDrive size={12} />}
              providers={local}
              onEdit={setEditProvider}
              onTest={handleTest}
              onActivate={handleActivate}
              testingName={testingName}
              activatingName={activatingName}
              activeProvider={activeProvider}
            />
          </div>
        )}
      </div>

      {editProvider && (
        <EditSheet provider={editProvider} onClose={() => setEditProvider(null)} onSaved={load} />
      )}
    </div>
  );
}
