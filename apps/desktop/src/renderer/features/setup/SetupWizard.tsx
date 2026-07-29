import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  Folder,
  Key,
  Loader2,
  Monitor,
  RefreshCw,
  Terminal,
  X,
  Zap,
} from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { cn } from '../../lib/utils';
import { sanitizeUiMessage } from '../../lib/sanitizeUiMessage';

type Step = 'welcome' | 'provider';
type CheckState<T> = {
  status: 'idle' | 'checking' | 'ok' | 'warning' | 'error';
  result?: T;
  error?: string;
};

interface PythonStatus {
  ok: boolean;
  python_version: string;
  issues: string[];
  config_exists: boolean;
}

interface WslStatus {
  isWindows: boolean;
  installed: boolean;
  version: string | null;
  distros: string[];
  defaultDistro: string | null;
  running: boolean;
}

interface StaticProvider {
  name: string;
  displayName: string;
  defaultModel: string;
  isLocal: boolean;
  isOllamaCloud: boolean;
  defaultApiBase?: string;
  keyRequired: boolean;
}

const DEFAULT_WORKSPACE = '~/.miqi/workspace';

const PROVIDER_MODEL_SUGGESTIONS: Record<string, string[]> = {
  openrouter: ['anthropic/claude-opus-4-5', 'google/gemini-2.5-pro', 'deepseek/deepseek-r1'],
  anthropic: ['claude-opus-4-5', 'claude-sonnet-4-5', 'claude-haiku-4-5'],
  openai: ['gpt-4.1', 'gpt-4o', 'gpt-4o-mini'],
  deepseek: ['deepseek-v4-flash', 'deepseek-v4-pro', 'deepseek-chat', 'deepseek-reasoner'],
  gemini: ['gemini-2.5-pro', 'gemini-2.0-flash', 'gemini-2.5-flash'],
  moonshot: ['kimi-k2.5', 'moonshot-v1-32k', 'moonshot-v1-128k'],
  dashscope: ['qwen-max', 'qwen-plus', 'qwen-turbo'],
  zhipu: ['glm-4-plus', 'glm-z1-flash', 'glm-4-long'],
  minimax: ['MiniMax-Text-01', 'abab6.5s-chat'],
  aihubmix: ['claude-opus-4-5', 'gpt-4o', 'gemini-2.5-pro'],
  siliconflow: ['Qwen/Qwen3-235B-A22B', 'deepseek-ai/DeepSeek-V3', 'deepseek-ai/DeepSeek-R1'],
  vllm: ['meta-llama/Llama-3.1-8B-Instruct'],
  ollama_local: ['llama3.2', 'qwen2.5:7b', 'deepseek-r1:7b'],
  ollama_cloud: ['gpt-oss:20b-cloud'],
};

const STATIC_PROVIDERS: StaticProvider[] = [
  {
    name: 'openrouter',
    displayName: 'OpenRouter（推荐网关）',
    defaultModel: 'anthropic/claude-opus-4-5',
    isLocal: false,
    isOllamaCloud: false,
    keyRequired: true,
  },
  {
    name: 'anthropic',
    displayName: 'Anthropic',
    defaultModel: 'claude-opus-4-5',
    isLocal: false,
    isOllamaCloud: false,
    keyRequired: true,
  },
  {
    name: 'openai',
    displayName: 'OpenAI',
    defaultModel: 'gpt-4.1',
    isLocal: false,
    isOllamaCloud: false,
    keyRequired: true,
  },
  {
    name: 'deepseek',
    displayName: 'DeepSeek',
    defaultModel: 'deepseek-v4-flash',
    isLocal: false,
    isOllamaCloud: false,
    keyRequired: true,
  },
  {
    name: 'gemini',
    displayName: 'Google Gemini',
    defaultModel: 'gemini-2.5-pro',
    isLocal: false,
    isOllamaCloud: false,
    keyRequired: true,
  },
  {
    name: 'moonshot',
    displayName: 'Moonshot (Kimi)',
    defaultModel: 'kimi-k2.5',
    isLocal: false,
    isOllamaCloud: false,
    keyRequired: true,
  },
  {
    name: 'dashscope',
    displayName: 'DashScope（通义千问）',
    defaultModel: 'qwen-max',
    isLocal: false,
    isOllamaCloud: false,
    keyRequired: true,
  },
  {
    name: 'zhipu',
    displayName: 'Zhipu AI（智谱）',
    defaultModel: 'glm-4',
    isLocal: false,
    isOllamaCloud: false,
    keyRequired: true,
  },
  {
    name: 'minimax',
    displayName: 'MiniMax',
    defaultModel: 'MiniMax-M2.7',
    isLocal: false,
    isOllamaCloud: false,
    keyRequired: true,
  },
  {
    name: 'aihubmix',
    displayName: 'AiHubMix',
    defaultModel: 'claude-opus-4.1',
    isLocal: false,
    isOllamaCloud: false,
    keyRequired: true,
  },
  {
    name: 'siliconflow',
    displayName: 'SiliconFlow（硅基流动）',
    defaultModel: 'deepseek-ai/DeepSeek-V3',
    isLocal: false,
    isOllamaCloud: false,
    keyRequired: true,
  },
  {
    name: 'vllm',
    displayName: 'vLLM / 本地 OpenAI 兼容',
    defaultModel: 'meta-llama/Llama-3.1-8B-Instruct',
    isLocal: true,
    isOllamaCloud: false,
    defaultApiBase: 'http://localhost:8000/v1',
    keyRequired: false,
  },
  {
    name: 'ollama_local',
    displayName: 'Ollama（本地）',
    defaultModel: 'llama3.2',
    isLocal: true,
    isOllamaCloud: false,
    defaultApiBase: 'http://localhost:11434',
    keyRequired: false,
  },
  {
    name: 'ollama_cloud',
    displayName: 'Ollama Cloud',
    defaultModel: 'gpt-oss:20b-cloud',
    isLocal: false,
    isOllamaCloud: true,
    defaultApiBase: 'https://ollama.com',
    keyRequired: true,
  },
];

export function SetupWizard({
  onComplete,
  onExit,
}: {
  onComplete: () => void;
  onExit?: () => void;
}) {
  const [step, setStep] = useState<Step>('welcome');
  const [workspace, setWorkspace] = useState(DEFAULT_WORKSPACE);
  const [selectedProvider, setSelectedProvider] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [apiBase, setApiBase] = useState('');
  const [modelName, setModelName] = useState('');
  const [testResult, setTestResult] = useState<'idle' | 'testing' | 'ok' | 'error'>('idle');
  const [testError, setTestError] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [pythonCheck, setPythonCheck] = useState<CheckState<PythonStatus>>({ status: 'idle' });
  const [wslCheck, setWslCheck] = useState<CheckState<WslStatus>>({ status: 'idle' });

  useEffect(() => {
    Promise.all([
      window.miqi.config.get().catch(() => null),
      window.miqi.providers.list().catch(() => null),
    ])
      .then(([cfg, providersResult]) => {
        if (!cfg) return;
        const agents = (cfg as Record<string, unknown>)['agents'] as
          Record<string, unknown> | undefined;
        const defaults = agents?.['defaults'] as Record<string, unknown> | undefined;
        const activeModel =
          typeof providersResult?.active_model === 'string' && providersResult.active_model
            ? providersResult.active_model
            : defaults?.['model']
              ? String(defaults['model'])
              : '';
        if (defaults?.['workspace']) setWorkspace(String(defaults['workspace']));
        if (activeModel) setModelName(activeModel);

        const providers = (cfg as Record<string, unknown>)['providers'] as
          Record<string, unknown> | undefined;
        if (!providers) return;

        const activeProvider =
          typeof providersResult?.active_provider === 'string'
            ? providersResult.active_provider
            : providersResult?.providers?.find((p) => p.configured_model)?.name;
        const selected =
          activeProvider && STATIC_PROVIDERS.some((p) => p.name === activeProvider)
            ? activeProvider
            : STATIC_PROVIDERS.find((provider) => {
                const entry = providers[provider.name] as Record<string, unknown> | undefined;
                return !!entry?.['apiKey'] || !!entry?.['apiBase'];
              })?.name;
        if (!selected) return;

        const selectedMeta = STATIC_PROVIDERS.find((p) => p.name === selected);
        const entry = providers[selected] as Record<string, unknown> | undefined;
        setSelectedProvider(selected);
        if (entry?.['apiKey']) setApiKey(String(entry['apiKey']));
        if (entry?.['apiBase']) {
          setApiBase(String(entry['apiBase']));
        } else {
          setApiBase(selectedMeta?.defaultApiBase ?? '');
        }
        if (!activeModel && selectedMeta) setModelName(selectedMeta.defaultModel);
      })
      .catch(() => {
        /* no existing config yet */
      });
  }, []);

  const runEnvironmentChecks = async () => {
    setPythonCheck({ status: 'checking' });
    setWslCheck({ status: 'checking' });

    const [pythonResult, wslResult] = await Promise.allSettled([
      window.miqi.python.check(),
      window.miqi.wsl.check(),
    ]);

    if (pythonResult.status === 'fulfilled') {
      const result = pythonResult.value as PythonStatus;
      setPythonCheck({ status: result.ok ? 'ok' : 'error', result });
    } else {
      setPythonCheck({
        status: 'error',
        error: pythonResult.reason?.message ?? String(pythonResult.reason),
      });
    }

    if (wslResult.status === 'fulfilled') {
      const result = wslResult.value as WslStatus;
      const hasWarning =
        result.isWindows &&
        (!result.installed ||
          (result.version !== null && result.version !== '2') ||
          result.distros.length === 0);
      setWslCheck({ status: hasWarning ? 'warning' : 'ok', result });
    } else {
      setWslCheck({
        status: 'warning',
        error: wslResult.reason?.message ?? String(wslResult.reason),
      });
    }
  };

  useEffect(() => {
    void runEnvironmentChecks();
  }, []);

  const providerMeta = STATIC_PROVIDERS.find((p) => p.name === selectedProvider);

  const canContinueProvider = () => {
    if (!selectedProvider || !providerMeta) return false;
    if (providerMeta.isLocal) return !!apiBase;
    if (providerMeta.isOllamaCloud) return !!apiBase && !!apiKey;
    return !!apiKey;
  };

  const resetConnectionTest = () => {
    setTestResult('idle');
    setTestError('');
  };

  const saveInitialConfig = async (config: Record<string, unknown>) => {
    if (saving) return;
    setSaving(true);
    setSaveError('');
    try {
      await window.miqi.setup.writeInitialConfig(config);
      const savedProvider = typeof config.provider_name === 'string' ? config.provider_name : '';
      const savedModel = typeof config.model === 'string' ? config.model : undefined;
      if (savedProvider && testResult === 'ok') {
        try {
          await window.miqi.providers.test(savedProvider, undefined, undefined, savedModel);
        } catch (e) {
          console.warn('[SetupWizard] 保存配置后二次验证 Provider 失败，已继续完成初始化', e);
        }
      }
      try {
        await window.miqi.runtime.start();
      } catch {
        /* non-fatal */
      }
      onComplete();
    } catch (e: any) {
      setSaveError(e?.message ?? String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleUseDefaults = () => {
    void saveInitialConfig({
      workspace: workspace || DEFAULT_WORKSPACE,
    });
  };

  const handleFinish = async () => {
    if (!providerMeta) return;
    await saveInitialConfig({
      provider_name: providerMeta.name,
      api_key: apiKey || null,
      api_base: apiBase || null,
      model: modelName || providerMeta.defaultModel,
      workspace: workspace || DEFAULT_WORKSPACE,
    });
  };

  const testProvider = async () => {
    if (!selectedProvider) return;
    setTestResult('testing');
    setTestError('');
    try {
      const result = await window.miqi.providers.test(
        selectedProvider,
        apiKey,
        apiBase || undefined,
        modelName || providerMeta?.defaultModel
      );
      if (result.ok) {
        setTestResult('ok');
      } else {
        setTestResult('error');
        setTestError('Provider 测试失败，请检查 API Key、API Base 或网络连接。');
      }
    } catch (e: any) {
      const msg: string = e?.message ?? String(e);
      if (msg.includes('Bridge not running') || msg.includes('not running')) {
        setTestResult('idle');
        setTestError('运行时未启动或正在重启，请稍后再试。');
      } else {
        setTestResult('error');
        setTestError(sanitizeUiMessage(msg));
      }
    }
  };

  const pythonBlocksStart = pythonCheck.status === 'checking' || pythonCheck.status === 'error';

  const renderStatusIcon = (status: CheckState<unknown>['status']) => {
    if (status === 'checking') return <Loader2 size={13} className="animate-spin" />;
    if (status === 'ok') return <Check size={13} />;
    if (status === 'warning' || status === 'error') return <AlertTriangle size={13} />;
    return <RefreshCw size={13} />;
  };

  const renderEnvironmentStatus = () => {
    const statusStyles: Record<CheckState<unknown>['status'], string> = {
      idle: 'border-[var(--border)] bg-[var(--surface)]',
      checking: 'border-[var(--border)] bg-[var(--surface)]',
      ok: 'border-[var(--success)]/40 bg-[var(--success)]/5',
      warning: 'border-[var(--warning)]/40 bg-[var(--warning)]/5',
      error: 'border-[var(--danger)]/40 bg-[var(--danger)]/5',
    };

    const pythonSummary = (() => {
      if (pythonCheck.status === 'checking') return '正在检查 Python 和 MiQi 依赖...';
      if (pythonCheck.status === 'ok') {
        const version = pythonCheck.result?.python_version;
        return version ? `已就绪 · Python ${version}` : '已就绪';
      }
      if (pythonCheck.status === 'error') {
        return pythonCheck.result?.issues?.[0] ?? pythonCheck.error ?? 'Python 或 MiQi 依赖不可用';
      }
      return '等待检查';
    })();

    const wslSummary = (() => {
      if (wslCheck.status === 'checking') return '正在检查 WSL2 状态...';
      const result = wslCheck.result;
      if (result && !result.isWindows) return '非 Windows 环境，无需 WSL2';
      if (wslCheck.status === 'ok') {
        const distro = result?.defaultDistro ?? result?.distros?.[0];
        return distro ? `已就绪 · ${distro}` : '已就绪';
      }
      if (wslCheck.status === 'warning') {
        if (wslCheck.error) return wslCheck.error;
        if (!result?.installed) return '未检测到 WSL2，可稍后在设置中处理';
        if (result.distros.length === 0) return 'WSL 已安装，但还没有 Linux 分发版';
        if (result.version && result.version !== '2') return `检测到 WSL ${result.version}，建议升级到 WSL2`;
        return 'WSL2 状态需要确认';
      }
      return '等待检查';
    })();

    const renderCommand = (command: string) => (
      <code className="block rounded-md bg-[var(--surface)] px-2.5 py-1.5 text-xs text-[var(--accent)] break-all">
        {command}
      </code>
    );

    const renderPythonGuidance = () => {
      if (pythonCheck.status !== 'error') return null;

      return (
        <div className="mt-2 rounded-md border border-[var(--danger)]/25 bg-[var(--danger)]/5 p-3">
          <p className="text-xs font-medium text-[var(--danger)]">需要先修复 Python / MiQi 环境</p>
          <ul className="mt-1.5 list-disc pl-4 text-xs text-[var(--danger)] space-y-1">
            {(pythonCheck.result?.issues?.length
              ? pythonCheck.result.issues
              : [pythonCheck.error ?? 'Python 或 MiQi 依赖不可用']
            ).map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
          <div className="mt-2 space-y-1.5 text-xs text-[var(--text-muted)]">
            <p>处理方式：</p>
            <p>1. 安装 Python 3.11 或更高版本，或设置 MIQI_PYTHON_PATH 指向可用 Python。</p>
            <p>2. 在 MiQi 仓库根目录安装依赖后重新检查：</p>
            {renderCommand('uv sync')}
          </div>
        </div>
      );
    };

    const renderWslGuidance = () => {
      if (wslCheck.status !== 'warning') return null;

      const result = wslCheck.result;
      if (result && !result.isWindows) return null;

      if (!result?.installed) {
        return (
          <div className="mt-2 rounded-md border border-[var(--warning)]/25 bg-[var(--warning)]/5 p-3">
            <p className="text-xs font-medium text-[var(--text)]">可选：安装 WSL2</p>
            <p className="mt-1 text-xs text-[var(--text-muted)] leading-relaxed">
              这不会阻止你进入 MiQi，但沙箱、Linux 工具链等能力在 WSL2 上体验更稳定。
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Button variant="ghost" size="sm" onClick={() => void runEnvironmentChecks()}>
                重新检查
              </Button>
            </div>
            <div className="mt-2 space-y-1.5 text-xs text-[var(--text-muted)]">
              <p>也可以手动操作：以管理员身份打开 PowerShell，运行命令并重启电脑。</p>
              {renderCommand('wsl --install')}
            </div>
          </div>
        );
      }

      if (result.distros.length === 0) {
        return (
          <div className="mt-2 rounded-md border border-[var(--warning)]/25 bg-[var(--warning)]/5 p-3">
            <p className="text-xs font-medium text-[var(--text)]">安装 Linux 分发版</p>
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              WSL 已安装，但还没有可用的 Linux 分发版。安装完成后重新检查即可。
            </p>
            <div className="mt-2">{renderCommand('wsl --install -d Ubuntu')}</div>
          </div>
        );
      }

      if (result.version && result.version !== '2') {
        return (
          <div className="mt-2 rounded-md border border-[var(--warning)]/25 bg-[var(--warning)]/5 p-3">
            <p className="text-xs font-medium text-[var(--text)]">建议升级到 WSL2</p>
            <div className="mt-2 space-y-1.5">
              {renderCommand('wsl --set-default-version 2')}
              {result.defaultDistro
                ? renderCommand(`wsl --set-version ${result.defaultDistro} 2`)
                : null}
            </div>
          </div>
        );
      }

      return (
        <p className="mt-2 text-xs text-[var(--text-muted)]">
          WSL2 状态暂时无法确认。你可以先进入应用，稍后在设置中继续处理。
        </p>
      );
    };

    return (
      <section className="flex flex-col gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/40 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-[var(--text)]">启动前状态</h2>
            <p className="text-xs text-[var(--text-faint)] mt-0.5">
              保留基础环境检查；Provider 和工具能力可稍后配置。
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void runEnvironmentChecks()}
            disabled={pythonCheck.status === 'checking' || wslCheck.status === 'checking'}
            title="重新检查"
          >
            <RefreshCw size={14} />
          </Button>
        </div>

        <div className="grid gap-2">
          <div className={cn('rounded-lg border px-3 py-2.5', statusStyles[pythonCheck.status])}>
            <div className="flex items-start gap-2">
              <Terminal size={15} className="mt-0.5 text-[var(--text-muted)]" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--text)]">
                  {renderStatusIcon(pythonCheck.status)}
                  Python / MiQi
                </div>
                <p className="text-xs text-[var(--text-muted)] mt-1 break-words">{pythonSummary}</p>
                {renderPythonGuidance()}
              </div>
            </div>
          </div>

          <div className={cn('rounded-lg border px-3 py-2.5', statusStyles[wslCheck.status])}>
            <div className="flex items-start gap-2">
              <Monitor size={15} className="mt-0.5 text-[var(--text-muted)]" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--text)]">
                  {renderStatusIcon(wslCheck.status)}
                  WSL2
                </div>
                <p className="text-xs text-[var(--text-muted)] mt-1 break-words">{wslSummary}</p>
                {renderWslGuidance()}
              </div>
            </div>
          </div>
        </div>

        {pythonCheck.status === 'error' && (
          <p className="text-xs text-[var(--danger)]">
            Python / MiQi 运行环境未就绪，修复后重新检查即可继续进入应用。
          </p>
        )}
      </section>
    );
  };

  const renderWelcome = () => (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col items-center text-center gap-3">
        <div className="w-16 h-16 rounded-2xl bg-[var(--accent-soft)] flex items-center justify-center mb-1">
          <Zap size={32} className="text-[var(--accent)]" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold text-[var(--text)]">欢迎使用 MiQi Desktop</h1>
          <p className="text-sm text-[var(--text-muted)] max-w-sm leading-relaxed mt-2">
            默认配置会先初始化工作目录。Provider、API Key、模型和工具可稍后在设置中配置。
          </p>
        </div>
      </div>

      <WorkspacePicker workspace={workspace} setWorkspace={setWorkspace} />

      {renderEnvironmentStatus()}

      {saveError && (
        <div className="rounded-lg border border-[var(--danger)]/30 bg-[var(--danger)]/10 px-3 py-2 text-xs text-[var(--danger)]">
          {saveError}
        </div>
      )}

      <div className="flex flex-col gap-2">
        <Button onClick={handleUseDefaults} disabled={saving || pythonBlocksStart}>
          {saving ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
          使用默认配置，进入应用
        </Button>
        <Button
          variant="ghost"
          onClick={() => setStep('provider')}
          disabled={saving || pythonBlocksStart}
        >
          高级配置 <ArrowRight size={16} />
        </Button>
      </div>
    </div>
  );

  const renderProvider = () => {
    const needsApiBase = providerMeta?.isLocal || providerMeta?.isOllamaCloud;
    const keyOptional = providerMeta?.isLocal && !providerMeta?.isOllamaCloud;
    const modelSuggestions = providerMeta
      ? (PROVIDER_MODEL_SUGGESTIONS[providerMeta.name] ?? [providerMeta.defaultModel])
      : [];

    return (
      <div className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold text-[var(--text)]">Provider 配置</h2>
        <p className="text-sm text-[var(--text-muted)]">
          需要立即配置模型服务时填写；也可以返回默认流程，进入应用后再到设置中配置。
        </p>

        <WorkspacePicker workspace={workspace} setWorkspace={setWorkspace} />

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-[var(--text-muted)]">Provider</label>
          <select
            value={selectedProvider}
            onChange={(e) => {
              const providerName = e.target.value;
              const nextProvider = STATIC_PROVIDERS.find((p) => p.name === providerName);
              setSelectedProvider(providerName);
              setApiKey('');
              setApiBase(nextProvider?.defaultApiBase ?? '');
              setModelName(nextProvider?.defaultModel ?? '');
              resetConnectionTest();
            }}
            className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 text-sm text-[var(--text)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30"
          >
            <option value="">请选择 Provider...</option>
            <optgroup label="云端 API">
              {STATIC_PROVIDERS.filter((p) => !p.isLocal && !p.isOllamaCloud).map((p) => (
                <option key={p.name} value={p.name}>
                  {p.displayName}
                </option>
              ))}
            </optgroup>
            <optgroup label="本地 / 自托管">
              {STATIC_PROVIDERS.filter((p) => p.isLocal || p.isOllamaCloud).map((p) => (
                <option key={p.name} value={p.name}>
                  {p.displayName}
                </option>
              ))}
            </optgroup>
          </select>
        </div>

        {providerMeta && (
          <>
            {needsApiBase && (
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-[var(--text-muted)]">API Base URL</label>
                <Input
                  value={apiBase}
                  onChange={(e) => {
                    setApiBase(e.target.value);
                    resetConnectionTest();
                  }}
                  placeholder={providerMeta.defaultApiBase ?? 'https://api.example.com/v1'}
                />
              </div>
            )}

            {!keyOptional && (
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-[var(--text-muted)]">API Key</label>
                <Input
                  type="password"
                  value={apiKey}
                  onChange={(e) => {
                    setApiKey(e.target.value);
                    resetConnectionTest();
                  }}
                  placeholder="sk-..."
                />
              </div>
            )}

            {!needsApiBase && (
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-[var(--text-muted)]">
                  API Base URL（可选）
                </label>
                <Input
                  value={apiBase}
                  onChange={(e) => {
                    setApiBase(e.target.value);
                    resetConnectionTest();
                  }}
                  placeholder="https://api.openai.com/v1"
                />
              </div>
            )}

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-[var(--text-muted)]">默认模型</label>
              <Input
                value={modelName}
                onChange={(e) => {
                  setModelName(e.target.value);
                  resetConnectionTest();
                }}
                placeholder={providerMeta.defaultModel}
              />
              {modelSuggestions.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-0.5">
                  {modelSuggestions.map((model) => (
                    <button
                      key={model}
                      type="button"
                      onClick={() => {
                        setModelName(model);
                        resetConnectionTest();
                      }}
                      className="px-2 py-0.5 rounded text-xs bg-[var(--surface-muted)] text-[var(--text-faint)] hover:text-[var(--accent)] hover:bg-[var(--accent-soft)] transition-colors font-mono"
                    >
                      {model}
                    </button>
                  ))}
                </div>
              )}
              <p className="text-xs text-[var(--text-faint)]">
                当前连接测试会使用 {providerMeta.displayName} / {modelName || providerMeta.defaultModel}
              </p>
            </div>

            {(keyOptional || apiKey) && (
              <div className="flex items-center gap-3">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={testProvider}
                  disabled={testResult === 'testing'}
                >
                  {testResult === 'testing' && <Loader2 size={14} className="animate-spin" />}
                  测试连接
                </Button>
                {testResult === 'ok' && (
                  <span className="text-xs text-[var(--success)] flex items-center gap-1">
                    <Check size={12} /> 连接成功
                  </span>
                )}
                {testResult === 'error' && (
                  <span className="text-xs text-[var(--danger)]">{testError}</span>
                )}
                {testResult === 'idle' && testError && (
                  <span className="text-xs text-[var(--text-muted)]">{testError}</span>
                )}
              </div>
            )}
          </>
        )}

        {saveError && (
          <div className="rounded-lg border border-[var(--danger)]/30 bg-[var(--danger)]/10 px-3 py-2 text-xs text-[var(--danger)]">
            {saveError}
          </div>
        )}

        <div className="flex gap-2 mt-2">
          <Button
            variant="ghost"
            onClick={() => setStep('welcome')}
          >
            <ArrowLeft size={16} /> 返回
          </Button>
          <Button onClick={handleFinish} disabled={!canContinueProvider() || saving}>
            {saving ? <Loader2 size={16} className="animate-spin" /> : <Key size={16} />}
            保存并进入应用
          </Button>
        </div>
      </div>
    );
  };

  const allSteps: Step[] = ['welcome', 'provider'];
  const stepIdx = allSteps.indexOf(step);

  return (
    <div className="flex items-center justify-center min-h-full bg-[var(--background)] py-8">
      <div className="w-full max-w-lg bg-[var(--surface-elevated)] border border-[var(--border)] rounded-xl shadow-sm p-8 relative">
        {onExit && (
          <button
            onClick={onExit}
            className="absolute top-4 right-4 p-1.5 rounded-lg text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-muted)] transition-colors"
            title="退出配置向导"
          >
            <X size={16} />
          </button>
        )}

        <div className="flex items-center justify-center gap-1.5 mb-8">
          {allSteps.map((s, i) => (
            <div key={s} className="flex items-center gap-1.5">
              <div
                className={cn(
                  'w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-medium transition-colors',
                  step === s
                    ? 'bg-[var(--accent)] text-white'
                    : i < stepIdx
                      ? 'bg-[var(--success)]/30 text-[var(--success)]'
                      : 'bg-[var(--surface-muted)] text-[var(--text-faint)]'
                )}
              >
                {i < stepIdx ? <Check size={10} /> : i + 1}
              </div>
              {i < allSteps.length - 1 && <div className="w-4 h-px bg-[var(--border)]" />}
            </div>
          ))}
        </div>

        {step === 'welcome' && renderWelcome()}
        {step === 'provider' && renderProvider()}
      </div>
    </div>
  );
}
function WorkspacePicker({
  workspace,
  setWorkspace,
}: {
  workspace: string;
  setWorkspace: (workspace: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-medium text-[var(--text-muted)]">工作目录</label>
      <div className="flex gap-2">
        <Input
          value={workspace}
          onChange={(e) => setWorkspace(e.target.value)}
          placeholder={DEFAULT_WORKSPACE}
          className="flex-1"
        />
        <Button
          variant="outline"
          size="sm"
          onClick={async () => {
            const dir = await window.miqi.dialog.openFile();
            if (dir) setWorkspace(dir);
          }}
          title="选择工作目录"
        >
          <Folder size={14} />
        </Button>
      </div>
    </div>
  );
}
