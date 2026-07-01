import { useState, useEffect, useCallback } from 'react';
import { useRestartRequired } from '../../contexts/RestartRequiredContext';
import {
  Zap,
  Server,
  Globe,
  HardDrive,
  CheckCircle,
  Circle,
  Edit2,
  TestTube2,
  Eye,
  EyeOff,
  Save,
  X,
  Loader2,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { cn } from '../../lib/utils';
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
        apiBase || undefined
      );
      setTestResult({
        ok: result.ok,
        message: result.ok ? '连接成功' : '连接失败',
      });
    } catch (err: unknown) {
      setTestResult({
        ok: false,
        message: err instanceof Error ? err.message : '测试失败',
      });
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
  deepseek: ['deepseek-chat', 'deepseek-reasoner'],
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
  testingName: string | null;
  testResults: Record<string, boolean>;
}

function ProviderRow({ provider, onEdit, onTest, testingName, testResults }: ProviderRowProps) {
  const label = PROVIDER_DISPLAY_NAMES[provider.name] ?? provider.display_name;
  const isTesting = testingName === provider.name;
  const testOk = testResults[provider.name];
  const hasTestResult = provider.name in testResults;

  return (
    <div className="flex items-center gap-3 px-4 py-2.5 hover:bg-[var(--surface-muted)] transition-colors group">
      <div
        className={cn(
          'shrink-0',
          provider.configured ? 'text-[var(--success)]' : 'text-[var(--border)]'
        )}
      >
        {provider.configured ? <CheckCircle size={14} /> : <Circle size={14} />}
      </div>
      <div className="flex-1 min-w-0">
        <span className="text-sm text-[var(--text)]">{label}</span>
        {provider.configured && (
          <div className="flex items-center gap-2 mt-0.5">
            {provider.api_key_hint && (
              <span className="text-xs text-[var(--text-faint)] font-mono">
                {provider.api_key_hint}
              </span>
            )}
            {provider.configured_model && (
              <span className="text-xs text-[var(--text-faint)] truncate max-w-[160px]">
                {provider.configured_model}
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
          provider.configured
            ? 'bg-[color-mix(in_srgb,var(--success)_15%,transparent)] text-[var(--success)]'
            : 'bg-[var(--surface-muted)] text-[var(--text-faint)]'
        )}
      >
        {provider.configured ? '已配置' : '未配置'}
      </span>
      {hasTestResult && (
        <span
          className={cn(
            'text-xs shrink-0',
            testOk ? 'text-[var(--success)]' : 'text-[var(--danger)]'
          )}
        >
          {testOk ? '✓ OK' : '✗ Failed'}
        </span>
      )}
      <div className="flex items-center gap-1 shrink-0">
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
  testingName: string | null;
  testResults: Record<string, boolean>;
}

function CategorySection({
  title,
  icon,
  providers,
  onEdit,
  onTest,
  testingName,
  testResults,
}: CategorySectionProps) {
  if (providers.length === 0) return null;
  return (
    <div>
      <div className="flex items-center gap-2 px-4 py-2 text-xs font-semibold uppercase tracking-widest text-[var(--text-faint)] border-b border-[var(--border-subtle)]">
        {icon}
        {title}
        <span className="ml-auto font-normal normal-case tracking-normal">
          {providers.filter((p) => p.configured).length}/{providers.length} 已配置
        </span>
      </div>
      <div className="divide-y divide-[var(--border-subtle)]">
        {providers.map((p) => (
          <ProviderRow
            key={p.name}
            provider={p}
            onEdit={onEdit}
            onTest={onTest}
            testingName={testingName}
            testResults={testResults}
          />
        ))}
      </div>
    </div>
  );
}

export function ProvidersPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [editProvider, setEditProvider] = useState<ProviderInfo | null>(null);
  const [testingName, setTestingName] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    try {
      const result = await window.miqi.providers.list();
      setProviders(result.providers);
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
      setTestResults((prev) => ({ ...prev, [p.name]: false }));
      return;
    }
    setTestingName(p.name);
    try {
      const result = await window.miqi.providers.test(p.name, undefined, p.api_base ?? undefined);
      setTestResults((prev) => ({ ...prev, [p.name]: result.ok }));
    } catch {
      setTestResults((prev) => ({ ...prev, [p.name]: false }));
    } finally {
      setTestingName(null);
    }
  };

  const gateways = providers.filter((p) => getCategory(p) === 'gateway');
  const international = providers.filter((p) => getCategory(p) === 'international');
  const domestic = providers.filter((p) => getCategory(p) === 'domestic');
  const local = providers.filter((p) => getCategory(p) === 'local');
  const configuredCount = providers.filter((p) => p.configured).length;

  return (
    <div className="flex flex-col h-full bg-[var(--background)]">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border-subtle)] bg-[var(--surface)] shrink-0">
        <div>
          <h1 className="text-base font-semibold text-[var(--text)]">模型提供商</h1>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            {loading ? '加载中…' : `${configuredCount} / ${providers.length} 已配置`}
          </p>
        </div>
        <button
          onClick={load}
          className="text-xs text-[var(--text-faint)] hover:text-[var(--text-muted)] transition-colors px-2 py-1 rounded"
        >
          Refresh
        </button>
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
              testingName={testingName}
              testResults={testResults}
            />
            <CategorySection
              title="国际"
              icon={<Zap size={12} />}
              providers={international}
              onEdit={setEditProvider}
              onTest={handleTest}
              testingName={testingName}
              testResults={testResults}
            />
            <CategorySection
              title="国内"
              icon={<Server size={12} />}
              providers={domestic}
              onEdit={setEditProvider}
              onTest={handleTest}
              testingName={testingName}
              testResults={testResults}
            />
            <CategorySection
              title="本地"
              icon={<HardDrive size={12} />}
              providers={local}
              onEdit={setEditProvider}
              onTest={handleTest}
              testingName={testingName}
              testResults={testResults}
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
