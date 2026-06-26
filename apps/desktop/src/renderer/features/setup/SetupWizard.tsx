import { useState, useEffect } from 'react'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { cn } from '../../lib/utils'
import {
  Check,
  X,
  Loader2,
  ArrowRight,
  ArrowLeft,
  Zap,
  Key,
  Folder,
  Search,
  Globe,
  BookOpen,
  Bot,
  Monitor,
} from 'lucide-react'
import type { PythonCheckResult } from '../../../shared/ipc'
import type { WslCheckResult, WslExportDistroResult, WslImportDistroResult } from '../../../shared/ipc'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type Step =
  | 'welcome'
  | 'environment'
  | 'wsl2'
  | 'provider'
  | 'webtools'
  | 'papers'
  | 'agent'
  | 'finish'
type SearchMode = 'brave' | 'ollama' | 'hybrid'
type FetchMode = 'builtin' | 'ollama' | 'hybrid'
type PapersMode = 'hybrid' | 'semantic_scholar' | 'arxiv'

interface StaticProvider {
  name: string
  displayName: string
  defaultModel: string
  isLocal: boolean
  isOllamaCloud: boolean
  defaultApiBase?: string
  keyRequired: boolean
}

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
    defaultModel: 'deepseek-chat',
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
    displayName: 'DashScope (通义千问)',
    defaultModel: 'qwen-max',
    isLocal: false,
    isOllamaCloud: false,
    keyRequired: true,
  },
  {
    name: 'zhipu',
    displayName: 'Zhipu AI (智谱)',
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
    displayName: 'SiliconFlow (硅基流动)',
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
]

const SOUL_PRESETS = [
  { key: 'balanced', label: 'Balanced（均衡）', desc: '友好、简洁、好奇' },
  {
    key: 'concise',
    label: 'Concise Operator（精简）',
    desc: '直接、行动优先、低噪音',
  },
  {
    key: 'mentor',
    label: 'Mentor Guide（导师）',
    desc: '耐心、结构化、解释权衡',
  },
  {
    key: 'builder',
    label: 'Builder Partner（构建者）',
    desc: '务实、工程导向、快速交付',
  },
]

// ---------------------------------------------------------------------------
// Main wizard
// ---------------------------------------------------------------------------
export function SetupWizard({ onComplete, onExit }: { onComplete: () => void; onExit?: () => void }) {
  const [step, setStep] = useState<Step>('welcome')

  // ---- Environment ----
  const [pyCheck, setPyCheck] = useState<PythonCheckResult | null>(null)
  const [checking, setChecking] = useState(false)

  // ---- WSL2 ----
  const [wslCheck, setWslCheck] = useState<WslCheckResult | null>(null)
  const [wslChecking, setWslChecking] = useState(false)
  const [wslInstalling, setWslInstalling] = useState(false)
  const [wslInstallError, setWslInstallError] = useState('')
  const [wslExporting, setWslExporting] = useState(false)
  const [wslExportResult, setWslExportResult] = useState<WslExportDistroResult | null>(null)
  const [wslImporting, setWslImporting] = useState(false)
  const [wslImportResult, setWslImportResult] = useState<WslImportDistroResult | null>(null)
  const [wslExportError, setWslExportError] = useState('')
  const [wslImportError, setWslImportError] = useState('')

  // ---- Provider ----
  const [selectedProvider, setSelectedProvider] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [apiBase, setApiBase] = useState('')
  const [modelName, setModelName] = useState('')
  const [testResult, setTestResult] = useState<
    'idle' | 'testing' | 'ok' | 'error'
  >('idle')
  const [testError, setTestError] = useState('')

  // ---- Web tools ----
  const [searchMode, setSearchMode] = useState<SearchMode>('brave')
  const [braveApiKey, setBraveApiKey] = useState('')
  const [searchOllamaBase, setSearchOllamaBase] = useState('https://ollama.com')
  const [searchOllamaKey, setSearchOllamaKey] = useState('')
  const [fetchMode, setFetchMode] = useState<FetchMode>('builtin')
  const [fetchOllamaBase, setFetchOllamaBase] = useState('https://ollama.com')
  const [fetchOllamaKey, setFetchOllamaKey] = useState('')

  // ---- Papers ----
  const [papersMode, setPapersMode] = useState<PapersMode>('hybrid')
  const [s2ApiKey, setS2ApiKey] = useState('')

  // ---- Agent ----
  const [agentName, setAgentName] = useState('miqi')
  const [workspace, setWorkspace] = useState('~/.miqi/workspace')
  const [soulPreset, setSoulPreset] = useState('balanced')

  // -----------------------------------------------------------------------
  // Load existing config on mount (so re-running wizard pre-fills fields)
  // -----------------------------------------------------------------------
  useEffect(() => {
    window.miqi.config.get().then((cfg) => {
      const agents = (cfg as Record<string, unknown>)['agents'] as Record<string, unknown> | undefined
      const defaults = agents?.['defaults'] as Record<string, unknown> | undefined
      if (defaults) {
        if (defaults['name']) setAgentName(String(defaults['name']))
        if (defaults['workspace']) setWorkspace(String(defaults['workspace']))
        if (defaults['model']) setModelName(String(defaults['model']))
        if (defaults['soulPreset']) setSoulPreset(String(defaults['soulPreset']))
      }
      // Detect provider from providers map
      const providers = (cfg as Record<string, unknown>)['providers'] as Record<string, unknown> | undefined
      if (providers) {
        for (const p of STATIC_PROVIDERS) {
          const entry = providers[p.name] as Record<string, unknown> | undefined
          if (entry) {
            setSelectedProvider(p.name)
            if (entry['apiKey']) setApiKey(String(entry['apiKey']))
            if (entry['apiBase']) setApiBase(String(entry['apiBase']))
            break
          }
        }
      }
      // Web tools
      const tools = (cfg as Record<string, unknown>)['tools'] as Record<string, unknown> | undefined
      const web = tools?.['web'] as Record<string, unknown> | undefined
      if (web) {
        const search = web['search'] as Record<string, unknown> | undefined
        if (search) {
          if (search['provider']) setSearchMode(String(search['provider']) as SearchMode)
          if (search['apiKey']) setBraveApiKey(String(search['apiKey']))
          if (search['ollamaApiBase']) setSearchOllamaBase(String(search['ollamaApiBase']))
          if (search['ollamaApiKey']) setSearchOllamaKey(String(search['ollamaApiKey']))
        }
        const fetch = web['fetch'] as Record<string, unknown> | undefined
        if (fetch) {
          if (fetch['provider']) setFetchMode(String(fetch['provider']) as FetchMode)
          if (fetch['ollamaApiBase']) setFetchOllamaBase(String(fetch['ollamaApiBase']))
          if (fetch['ollamaApiKey']) setFetchOllamaKey(String(fetch['ollamaApiKey']))
        }
      }
      const papers = tools?.['papers'] as Record<string, unknown> | undefined
      if (papers) {
        if (papers['provider']) setPapersMode(String(papers['provider']) as PapersMode)
        if (papers['semanticScholarApiKey']) setS2ApiKey(String(papers['semanticScholarApiKey']))
      }
    }).catch(() => { /* no config yet, that's fine */ })
  }, [])

  // -----------------------------------------------------------------------
  // Helpers
  // -----------------------------------------------------------------------
  const providerMeta = STATIC_PROVIDERS.find((p) => p.name === selectedProvider)

  const canContinueProvider = () => {
    if (!selectedProvider || !providerMeta) return false
    if (providerMeta.isLocal) return !!apiBase && testResult === 'ok'
    if (providerMeta.isOllamaCloud)
      return !!apiBase && !!apiKey && testResult === 'ok'
    return !!apiKey && testResult === 'ok'
  }

  const runCheck = async () => {
    setChecking(true)
    try {
      const result = await window.miqi.python.check()
      setPyCheck(result)
    } catch {
      setPyCheck({
        ok: false,
        python_version: 'unknown',
        issues: ['无法检测 Python 环境'],
        config_exists: false,
      })
    }
    setChecking(false)
  }

  const runWslCheck = async () => {
    setWslChecking(true)
    try {
      const result = await window.miqi.wsl.check()
      setWslCheck(result)
    } catch {
      setWslCheck({
        isWindows: true,
        installed: false,
        version: null,
        distros: [],
        defaultDistro: null,
        running: false,
      })
    }
    setWslChecking(false)
  }

  const installWsl = async () => {
    setWslInstalling(true)
    setWslInstallError('')
    try {
      const result = await window.miqi.wsl.install()
      if (!result.launched) {
        setWslInstallError(result.error || '启动安装失败')
      }
    } catch (e: any) {
      setWslInstallError(e?.message ?? String(e))
    }
    setWslInstalling(false)
  }

  const exportDistro = async () => {
    // Skip if AIShadowSandbox already exists as a WSL distro
    if (wslCheck?.distros?.includes('AIShadowSandbox')) {
      setWslExportResult({
        exported: true,
        distro: 'AIShadowSandbox',
        tarPath: null,
        error: null,
      })
      setWslImportResult({
        imported: true,
        distro: 'AIShadowSandbox',
        installLocation: null,
        error: null,
      })
      return
    }
    if (wslCheck?.defaultDistro) {
      setWslExporting(true)
      setWslExportResult(null)
      setWslExportError('')
      try {
        const result = await window.miqi.wsl.exportDistro(
          wslCheck.defaultDistro,
        )
        setWslExportResult(result)
        if (result.exported) {
          // Auto-import after successful export
          setWslImporting(true)
          setWslImportResult(null)
          setWslImportError('')
          try {
            const impResult = await window.miqi.wsl.importDistro({
              tarPath: result.tarPath!,
              distroName: 'AIShadowSandbox',
            })
            setWslImportResult(impResult)
          } catch (e: any) {
            setWslImportError(e?.message ?? String(e))
          }
          setWslImporting(false)
        }
      } catch (e: any) {
        setWslExportError(e?.message ?? String(e))
      }
      setWslExporting(false)
    }
  }

  // Auto-trigger sandbox distro setup when WSL is detected with a distro.
  // Skips if AIShadowSandbox already exists or export was already completed.
  useEffect(() => {
    if (
      wslCheck?.installed &&
      wslCheck?.defaultDistro &&
      !wslExportResult &&
      !wslExporting &&
      !wslCheck?.distros?.includes('AIShadowSandbox')
    ) {
      exportDistro()
    }
  }, [
    wslCheck?.installed,
    wslCheck?.defaultDistro,
    wslExportResult,
    wslExporting,
  ])

  const importDistro = async () => {
    if (wslExportResult?.tarPath) {
      setWslImporting(true)
      setWslImportResult(null)
      setWslImportError('')
      try {
        const result = await window.miqi.wsl.importDistro({
          tarPath: wslExportResult.tarPath,
          distroName: 'AIShadowSandbox',
        })
        setWslImportResult(result)
      } catch (e: any) {
        setWslImportError(e?.message ?? String(e))
      }
      setWslImporting(false)
    }
  }

  const testProvider = async () => {
    setTestResult('testing')
    setTestError('')
    try {
      await window.miqi.providers.test(
        selectedProvider,
        apiKey,
        apiBase || undefined,
      )
      setTestResult('ok')
    } catch (e: any) {
      const msg: string = e?.message ?? String(e)
      if (msg.includes('Bridge not running') || msg.includes('not running')) {
        setTestResult('ok')
      } else {
        setTestResult('error')
        setTestError(msg)
      }
    }
  }

  const handleFinish = async () => {
    await window.miqi.setup.writeInitialConfig({
      provider_name: selectedProvider,
      api_key: apiKey,
      api_base: apiBase || null,
      model: modelName || providerMeta?.defaultModel || null,
      agent_name: agentName || null,
      workspace: workspace || null,
      soul_preset: soulPreset || null,
      search_provider: searchMode,
      brave_api_key: braveApiKey || null,
      search_ollama_api_base: searchOllamaBase || null,
      search_ollama_api_key: searchOllamaKey || null,
      fetch_provider: fetchMode,
      fetch_ollama_api_base: fetchOllamaBase || null,
      fetch_ollama_api_key: fetchOllamaKey || null,
      papers_provider: papersMode,
      semantic_scholar_api_key: s2ApiKey || null,
    })
    try {
      await window.miqi.runtime.start()
    } catch {
      /* non-fatal */
    }
    onComplete()
  }

  // -----------------------------------------------------------------------
  // Step renderers
  // -----------------------------------------------------------------------

  const renderWelcome = () => (
    <div className="flex flex-col items-center text-center gap-4">
      <div className="w-16 h-16 rounded-2xl bg-[var(--accent-soft)] flex items-center justify-center mb-2">
        <Zap size={32} className="text-[var(--accent)]" />
      </div>
      <h1 className="text-2xl font-semibold text-[var(--text)]">
        欢迎使用 MiQi Desktop
      </h1>
      <p className="text-sm text-[var(--text-muted)] max-w-sm leading-relaxed">
        MiQi Desktop 是本地 AI Agent 的桌面端伴侣。 让我们配置好 Provider
        和工具，开始对话吧。
      </p>
      <Button onClick={() => setStep('environment')} className="mt-4">
        开始配置 <ArrowRight size={16} />
      </Button>
    </div>
  )

  const renderEnvironment = () => (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold text-[var(--text)]">环境检查</h2>
      <p className="text-sm text-[var(--text-muted)]">
        检查 Python 和 MiQi 是否已安装。
      </p>

      {!pyCheck ? (
        <Button
          onClick={runCheck}
          disabled={checking}
          variant="outline"
          className="self-start"
        >
          {checking && <Loader2 size={14} className="animate-spin" />}
          运行检查
        </Button>
      ) : (
        <div className="flex flex-col gap-2 bg-[var(--surface-muted)] rounded-lg p-4 text-sm">
          <CheckItem
            label="Python"
            ok={pyCheck.ok}
            detail={pyCheck.python_version}
          />
          {pyCheck.issues.map((issue, i) => (
            <div
              key={i}
              className="flex items-center gap-2 text-[var(--danger)] text-xs"
            >
              <X size={12} /> {issue}
            </div>
          ))}
          <CheckItem
            label="配置文件"
            ok={!pyCheck.config_exists}
            detail={pyCheck.config_exists ? '已有配置（将更新）' : '尚未创建'}
          />
        </div>
      )}

      <div className="flex gap-2 mt-4">
        <Button variant="ghost" onClick={() => setStep('welcome')}>
          <ArrowLeft size={16} /> 返回
        </Button>
        <Button onClick={() => setStep('wsl2')} disabled={!pyCheck?.ok}>
          继续 <ArrowRight size={16} />
        </Button>
      </div>
    </div>
  )

  const renderWsl2 = () => {
    const isWindows = wslCheck?.isWindows ?? true
    // Non-Windows: auto-skip, but still render a "not needed" message
    if (!isWindows) {
      return (
        <div className="flex flex-col gap-4">
          <h2 className="text-lg font-semibold text-[var(--text)]">
            WSL2 环境
          </h2>
          <div className="flex items-center gap-2 text-sm text-[var(--success)]">
            <Check size={16} />
            <span>当前非 Windows 系统，无需配置 WSL2</span>
          </div>
          <div className="flex gap-2 mt-4">
            <Button variant="ghost" onClick={() => setStep('environment')}>
              <ArrowLeft size={16} /> 返回
            </Button>
            <Button onClick={() => setStep('provider')}>
              继续 <ArrowRight size={16} />
            </Button>
          </div>
        </div>
      )
    }

    const isInstalled = wslCheck?.installed ?? false
    const isWsl2 = wslCheck?.version === '2'
    const hasDistro = (wslCheck?.distros?.length ?? 0) > 0

    return (
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <Monitor size={18} className="text-[var(--accent)]" />
          <h2 className="text-lg font-semibold text-[var(--text)]">
            WSL2 环境
          </h2>
        </div>
        <p className="text-sm text-[var(--text-muted)]">
          MiQi Desktop 的 Python 后端在 WSL2 上运行最佳。请确认 WSL2
          已安装并配置了 Linux 分发版。
        </p>

        {!wslCheck ? (
          <Button
            onClick={runWslCheck}
            disabled={wslChecking}
            variant="outline"
            className="self-start"
          >
            {wslChecking && <Loader2 size={14} className="animate-spin" />}
            检测 WSL2
          </Button>
        ) : (
          <div className="flex flex-col gap-2 bg-[var(--surface-muted)] rounded-lg p-4 text-sm">
            <CheckItem
              label="WSL 已安装"
              ok={isInstalled}
              detail={
                isInstalled
                  ? `默认版本: WSL${wslCheck.version ?? '?'}`
                  : '未安装'
              }
            />
            <CheckItem
              label="WSL2 版本"
              ok={isWsl2}
              detail={
                isWsl2
                  ? '已设为默认'
                  : wslCheck.version
                    ? `当前为 WSL${wslCheck.version}，建议升级到 WSL2`
                    : '未设置'
              }
            />
            <CheckItem
              label="Linux 分发版"
              ok={hasDistro}
              detail={hasDistro ? wslCheck!.distros.join(', ') : '未安装分发版'}
            />
            {/* <CheckItem
              label="WSL 运行状态"
              ok={wslCheck!.running}
              detail={wslCheck!.running ? '运行中' : '未运行'}
            /> */}
          </div>
        )}

        {/* Install / guidance section */}
        {wslCheck && !isInstalled && (
          <div className="flex flex-col gap-3 bg-[var(--surface-muted)] rounded-lg p-4">
            <h3 className="text-sm font-medium text-[var(--text)]">
              安装 WSL2
            </h3>
            <p className="text-xs text-[var(--text-muted)] leading-relaxed">
              点击下方按钮将以管理员权限运行{' '}
              <code className="bg-[var(--surface)] px-1 rounded text-[var(--accent)]">
                wsl --install
              </code>
              。 安装完成后需要<strong>重启电脑</strong>
              ，然后回到此向导继续配置。
            </p>
            <Button
              onClick={installWsl}
              disabled={wslInstalling}
              size="sm"
              className="self-start"
            >
              {wslInstalling && <Loader2 size={14} className="animate-spin" />}
              安装 WSL2
            </Button>
            {wslInstallError && (
              <p className="text-xs text-[var(--danger)]">{wslInstallError}</p>
            )}
            <div className="text-xs text-[var(--text-faint)] mt-1 space-y-1">
              <p>也可手动安装：</p>
              <ol className="list-decimal ml-4 space-y-0.5">
                <li>以管理员身份打开 PowerShell</li>
                <li>
                  运行{' '}
                  <code className="bg-[var(--surface)] px-1 rounded text-[var(--accent)]">
                    wsl --install
                  </code>
                </li>
                <li>重启电脑完成安装</li>
                <li>设置 Linux 用户名和密码</li>
              </ol>
            </div>
          </div>
        )}

        {/* Installed but no distro */}
        {wslCheck && isInstalled && !hasDistro && (
          <div className="flex flex-col gap-2 bg-[var(--surface-muted)] rounded-lg p-4">
            <h3 className="text-sm font-medium text-[var(--text)]">
              安装 Linux 分发版
            </h3>
            <p className="text-xs text-[var(--text-muted)] leading-relaxed">
              WSL 已安装但未检测到 Linux 分发版。请在 PowerShell 中运行：
            </p>
            <code className="bg-[var(--surface)] px-3 py-1.5 rounded text-xs text-[var(--accent)]">
              wsl --install -d Ubuntu
            </code>
            <p className="text-xs text-[var(--text-faint)]">
              安装完成后点击"重新检测"刷新状态。
            </p>
          </div>
        )}

        {/* WSL2 installed with distro → auto-setup dedicated sandbox distro */}
        {wslCheck && isInstalled && hasDistro && (
          <div className="flex flex-col gap-2 bg-[var(--surface-muted)] rounded-lg p-4">
            <h3 className="text-sm font-medium text-[var(--text)]">
              专用沙箱发行版
            </h3>
            <p className="text-xs text-[var(--text-muted)] leading-relaxed">
              正在自动导出专用 WSL 发行版供沙箱隔离使用，避免沙箱需要 sudo 权限…
            </p>
            {/* Auto-export progress */}
            {wslExporting && (
              <div className="flex items-center gap-2 text-xs text-[var(--accent)]">
                <Loader2 size={14} className="animate-spin" />
                正在导出 {wslCheck.defaultDistro} 到专用沙箱发行版…
              </div>
            )}
            {/* Auto-import progress */}
            {wslImporting && (
              <div className="flex items-center gap-2 text-xs text-[var(--accent)]">
                <Loader2 size={14} className="animate-spin" />
                正在导入专用沙箱发行版 AIShadowSandbox…
              </div>
            )}
            {/* Export completed */}
            {wslExportResult?.exported && (
              <CheckItem
                label="导出沙箱发行版"
                ok={true}
                detail={`已导出 ${wslExportResult.distro}`}
              />
            )}
            {/* Import completed */}
            {wslImportResult?.imported && (
              <CheckItem
                label="导入专用沙箱发行版"
                ok={true}
                detail={`已导入 ${wslImportResult.distro}`}
              />
            )}
            {wslExportError && (
              <p className="text-xs text-[var(--danger)]">
                导出失败: {wslExportError}
              </p>
            )}
            {wslImportError && (
              <p className="text-xs text-[var(--danger)]">
                导入失败: {wslImportError}
              </p>
            )}
          </div>
        )}

        {/* WSL1 → WSL2 upgrade hint */}
        {wslCheck && isInstalled && wslCheck.version === '1' && (
          <div className="flex flex-col gap-2 bg-[var(--surface-muted)] rounded-lg p-4">
            <h3 className="text-sm font-medium text-[var(--text)]">
              升级到 WSL2
            </h3>
            <p className="text-xs text-[var(--text-muted)] leading-relaxed">
              当前默认为 WSL1，建议升级到 WSL2 以获得更好的性能和兼容性：
            </p>
            <code className="bg-[var(--surface)] px-3 py-1.5 rounded text-xs text-[var(--accent)]">
              wsl --set-default-version 2
            </code>
            {wslCheck.defaultDistro && (
              <>
                <p className="text-xs text-[var(--text-muted)]">
                  转换已有分发版：
                </p>
                <code className="bg-[var(--surface)] px-3 py-1.5 rounded text-xs text-[var(--accent)]">
                  wsl --set-version {wslCheck.defaultDistro} 2
                </code>
              </>
            )}
          </div>
        )}

        <div className="flex gap-2 mt-4">
          <Button variant="ghost" onClick={() => setStep('environment')}>
            <ArrowLeft size={16} /> 返回
          </Button>
          {wslCheck && !isInstalled && (
            <Button
              variant="outline"
              onClick={runWslCheck}
              disabled={wslChecking}
            >
              {wslChecking ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Check size={14} />
              )}
              重新检测
            </Button>
          )}
          <Button onClick={() => setStep('provider')}>
            继续 <ArrowRight size={16} />
          </Button>
        </div>
      </div>
    )
  }

  const renderProvider = () => {
    const meta = providerMeta
    const needsApiBase = meta?.isLocal || meta?.isOllamaCloud
    const keyOptional = meta?.isLocal && !meta?.isOllamaCloud

    return (
      <div className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold text-[var(--text)]">
          选择 LLM Provider
        </h2>
        <p className="text-sm text-[var(--text-muted)]">
          选择 AI Provider 并输入凭据，之后可在设置中修改。
        </p>

        {/* Provider selector */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-[var(--text-muted)]">
            Provider
          </label>
          <select
            value={selectedProvider}
            onChange={(e) => {
              const pname = e.target.value
              setSelectedProvider(pname)
              const p = STATIC_PROVIDERS.find((x) => x.name === pname)
              if (p?.defaultApiBase) setApiBase(p.defaultApiBase)
              else setApiBase('')
              setModelName(p?.defaultModel ?? '')
              setTestResult('idle')
            }}
            className="h-9 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 text-sm text-[var(--text)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30"
          >
            <option value="">请选择 Provider…</option>
            <optgroup label="云端 API">
              {STATIC_PROVIDERS.filter(
                (p) => !p.isLocal && !p.isOllamaCloud,
              ).map((p) => (
                <option key={p.name} value={p.name}>
                  {p.displayName}
                </option>
              ))}
            </optgroup>
            <optgroup label="本地 / 自托管">
              {STATIC_PROVIDERS.filter((p) => p.isLocal || p.isOllamaCloud).map(
                (p) => (
                  <option key={p.name} value={p.name}>
                    {p.displayName}
                  </option>
                ),
              )}
            </optgroup>
          </select>
        </div>

        {/* API Base for local/cloud-ollama providers */}
        {needsApiBase && (
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-[var(--text-muted)]">
              API Base URL
            </label>
            <Input
              value={apiBase}
              onChange={(e) => setApiBase(e.target.value)}
              placeholder={meta?.defaultApiBase ?? 'http://localhost:11434'}
            />
          </div>
        )}

        {/* API Key */}
        {!keyOptional && (
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-[var(--text-muted)]">
              API Key
            </label>
            <Input
              type="password"
              value={apiKey}
              onChange={(e) => {
                setApiKey(e.target.value)
                setTestResult('idle')
              }}
              placeholder="sk-..."
            />
          </div>
        )}

        {/* Optional custom API base for non-local providers */}
        {!needsApiBase && (
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-[var(--text-muted)]">
              API Base URL（可选，使用代理时填写）
            </label>
            <Input
              value={apiBase}
              onChange={(e) => setApiBase(e.target.value)}
              placeholder="https://api.openai.com/v1"
            />
          </div>
        )}

        {/* Model name */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-[var(--text-muted)]">
            默认模型
          </label>
          <Input
            value={modelName}
            onChange={(e) => setModelName(e.target.value)}
            placeholder={meta?.defaultModel ?? 'provider/model-name'}
          />
        </div>

        {/* Test connection */}
        {selectedProvider && (keyOptional || apiKey) && (
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={testProvider}
              disabled={testResult === 'testing'}
            >
              {testResult === 'testing' && (
                <Loader2 size={14} className="animate-spin" />
              )}
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
          </div>
        )}

        <div className="flex gap-2 mt-4">
          <Button variant="ghost" onClick={() => setStep('wsl2')}>
            <ArrowLeft size={16} /> 返回
          </Button>
          <Button
            onClick={() => setStep('webtools')}
            disabled={!canContinueProvider()}
          >
            继续 <ArrowRight size={16} />
          </Button>
        </div>
      </div>
    )
  }

  const renderWebTools = () => (
    <div className="flex flex-col gap-5 overflow-y-auto max-h-[420px] pr-1">
      <h2 className="text-lg font-semibold text-[var(--text)] shrink-0">
        Web 工具配置
      </h2>

      {/* ---- Web Search ---- */}
      <section className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <Search size={14} className="text-[var(--accent)]" />
          <h3 className="text-sm font-semibold text-[var(--text)]">Web 搜索</h3>
        </div>

        <div className="flex gap-2">
          {(['brave', 'ollama', 'hybrid'] as SearchMode[]).map((v) => (
            <button
              key={v}
              onClick={() => setSearchMode(v)}
              className={cn(
                'px-3 py-1.5 rounded-lg text-xs border capitalize transition-colors',
                searchMode === v
                  ? 'bg-[var(--accent)] text-white border-[var(--accent)]'
                  : 'bg-[var(--surface)] text-[var(--text-muted)] border-[var(--border)] hover:border-[var(--accent)]',
              )}
            >
              {v === 'brave' ? 'Brave' : v === 'ollama' ? 'Ollama' : 'Hybrid'}
            </button>
          ))}
        </div>

        {(searchMode === 'brave' || searchMode === 'hybrid') && (
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-[var(--text-muted)]">
              Brave Search API Key
              {searchMode === 'hybrid' ? '（优先使用 Brave）' : ''}
            </label>
            <Input
              type="password"
              value={braveApiKey}
              onChange={(e) => setBraveApiKey(e.target.value)}
              placeholder="BSA..."
            />
            <p className="text-xs text-[var(--text-faint)]">
              免费申请：{' '}
              <button
                className="text-[var(--accent)] underline"
                onClick={() =>
                  window.open?.('https://brave.com/search/api/', '_blank')
                }
              >
                brave.com/search/api
              </button>
            </p>
          </div>
        )}

        {(searchMode === 'ollama' || searchMode === 'hybrid') && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-[var(--text-muted)]">
                Ollama web_search Base URL
              </label>
              <Input
                value={searchOllamaBase}
                onChange={(e) => setSearchOllamaBase(e.target.value)}
                placeholder="https://ollama.com"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-[var(--text-muted)]">
                Ollama web_search API Key
              </label>
              <Input
                type="password"
                value={searchOllamaKey}
                onChange={(e) => setSearchOllamaKey(e.target.value)}
                placeholder="ollama-key..."
              />
            </div>
          </div>
        )}
      </section>

      {/* ---- Web Fetch ---- */}
      <section className="flex flex-col gap-3 pt-3 border-t border-[var(--border-subtle)]">
        <div className="flex items-center gap-2">
          <Globe size={14} className="text-[var(--accent)]" />
          <h3 className="text-sm font-semibold text-[var(--text)]">
            Web Fetch
          </h3>
        </div>

        <div className="flex gap-2">
          {(['builtin', 'ollama', 'hybrid'] as FetchMode[]).map((v) => (
            <button
              key={v}
              onClick={() => setFetchMode(v)}
              className={cn(
                'px-3 py-1.5 rounded-lg text-xs border transition-colors',
                fetchMode === v
                  ? 'bg-[var(--accent)] text-white border-[var(--accent)]'
                  : 'bg-[var(--surface)] text-[var(--text-muted)] border-[var(--border)] hover:border-[var(--accent)]',
              )}
            >
              {v === 'builtin' ? '内置' : v === 'ollama' ? 'Ollama' : 'Hybrid'}
            </button>
          ))}
        </div>

        {(fetchMode === 'ollama' || fetchMode === 'hybrid') && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-[var(--text-muted)]">
                Ollama web_fetch Base URL
              </label>
              <Input
                value={fetchOllamaBase}
                onChange={(e) => setFetchOllamaBase(e.target.value)}
                placeholder={searchOllamaBase || 'https://ollama.com'}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-[var(--text-muted)]">
                Ollama web_fetch API Key
              </label>
              <Input
                type="password"
                value={fetchOllamaKey}
                onChange={(e) => setFetchOllamaKey(e.target.value)}
                placeholder="留空则复用 web_search Key"
              />
            </div>
          </div>
        )}
      </section>

      <div className="flex gap-2 pt-2 shrink-0">
        <Button variant="ghost" onClick={() => setStep('provider')}>
          <ArrowLeft size={16} /> 返回
        </Button>
        <Button onClick={() => setStep('papers')}>
          继续 <ArrowRight size={16} />
        </Button>
      </div>
    </div>
  )

  const renderPapers = () => (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <BookOpen size={16} className="text-[var(--accent)]" />
        <h2 className="text-lg font-semibold text-[var(--text)]">
          论文研究工具（可选）
        </h2>
      </div>
      <p className="text-sm text-[var(--text-muted)]">
        用于 paper_search 工具，可跳过，稍后在设置中配置。
      </p>

      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)]">
          数据源
        </label>
        <div className="flex gap-2">
          {(
            [
              ['hybrid', 'Hybrid（推荐）'],
              ['semantic_scholar', 'Semantic Scholar'],
              ['arxiv', 'arXiv'],
            ] as [PapersMode, string][]
          ).map(([v, l]) => (
            <button
              key={v}
              onClick={() => setPapersMode(v)}
              className={cn(
                'px-3 py-1.5 rounded-lg text-xs border transition-colors',
                papersMode === v
                  ? 'bg-[var(--accent)] text-white border-[var(--accent)]'
                  : 'bg-[var(--surface)] text-[var(--text-muted)] border-[var(--border)] hover:border-[var(--accent)]',
              )}
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      {(papersMode === 'hybrid' || papersMode === 'semantic_scholar') && (
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-[var(--text-muted)]">
            Semantic Scholar API Key（可选，建议填写）
          </label>
          <Input
            type="password"
            value={s2ApiKey}
            onChange={(e) => setS2ApiKey(e.target.value)}
            placeholder="可选，填写后减少限流"
          />
          <p className="text-xs text-[var(--text-faint)]">
            申请地址：{' '}
            <button
              className="text-[var(--accent)] underline"
              onClick={() =>
                window.open?.(
                  'https://www.semanticscholar.org/product/api',
                  '_blank',
                )
              }
            >
              semanticscholar.org/product/api
            </button>
          </p>
        </div>
      )}

      <div className="flex gap-2 mt-4">
        <Button variant="ghost" onClick={() => setStep('webtools')}>
          <ArrowLeft size={16} /> 返回
        </Button>
        <Button onClick={() => setStep('agent')}>
          继续 <ArrowRight size={16} />
        </Button>
      </div>
    </div>
  )

  const renderAgent = () => (
    <div className="flex flex-col gap-4 overflow-y-auto max-h-[420px] pr-1">
      <div className="flex items-center gap-2">
        <Bot size={16} className="text-[var(--accent)]" />
        <h2 className="text-lg font-semibold text-[var(--text)]">
          Agent 身份配置
        </h2>
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)]">
          Agent 名称
        </label>
        <Input
          value={agentName}
          onChange={(e) => setAgentName(e.target.value)}
          placeholder="miqi"
        />
        <p className="text-xs text-[var(--text-faint)]">
          Agent 的自称，会出现在 SOUL.md 和对话中。
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)]">
          工作目录
        </label>
        <div className="flex gap-2">
          <Input
            value={workspace}
            onChange={(e) => setWorkspace(e.target.value)}
            placeholder="~/.miqi/workspace"
            className="flex-1"
          />
          <Button
            variant="outline"
            size="sm"
            onClick={async () => {
              const dir = await window.miqi.dialog.openFile()
              if (dir) setWorkspace(dir)
            }}
          >
            <Folder size={14} /> 浏览
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <label className="text-xs font-medium text-[var(--text-muted)]">
          Soul 预设（Agent 个性）
        </label>
        <div className="grid grid-cols-2 gap-2">
          {SOUL_PRESETS.map((p) => (
            <button
              key={p.key}
              onClick={() => setSoulPreset(p.key)}
              className={cn(
                'rounded-lg border px-3 py-2 text-left transition-colors',
                soulPreset === p.key
                  ? 'bg-[var(--accent-soft)] border-[var(--accent)] text-[var(--text)]'
                  : 'bg-[var(--surface)] border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--accent)]',
              )}
            >
              <div className="text-xs font-medium">{p.label}</div>
              <div className="text-[10px] text-[var(--text-faint)] mt-0.5">
                {p.desc}
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="flex gap-2 mt-2 shrink-0">
        <Button variant="ghost" onClick={() => setStep('papers')}>
          <ArrowLeft size={16} /> 返回
        </Button>
        <Button onClick={() => setStep('finish')}>
          继续 <ArrowRight size={16} />
        </Button>
      </div>
    </div>
  )

  const renderFinish = () => {
    const searchLabels: Record<SearchMode, string> = {
      brave: 'Brave',
      ollama: 'Ollama',
      hybrid: 'Hybrid (Brave + Ollama)',
    }
    const fetchLabels: Record<FetchMode, string> = {
      builtin: '内置',
      ollama: 'Ollama',
      hybrid: 'Hybrid',
    }
    const papersLabels: Record<PapersMode, string> = {
      hybrid: 'Hybrid',
      semantic_scholar: 'Semantic Scholar',
      arxiv: 'arXiv',
    }
    const pMeta = STATIC_PROVIDERS.find((p) => p.name === selectedProvider)

    return (
      <div className="flex flex-col items-center text-center gap-4">
        <div className="w-12 h-12 rounded-full bg-[var(--success)]/20 flex items-center justify-center">
          <Check size={24} className="text-[var(--success)]" />
        </div>
        <h2 className="text-xl font-semibold text-[var(--text)]">配置完成！</h2>
        <p className="text-sm text-[var(--text-muted)] max-w-sm">
          点击下方按钮保存配置并启动 MiQi。
        </p>

        <div className="w-full max-w-xs bg-[var(--surface-muted)] rounded-lg px-4 py-3 text-left text-xs space-y-1.5 text-[var(--text-muted)]">
          <SummaryRow
            label="Provider"
            value={pMeta?.displayName ?? selectedProvider}
          />
          <SummaryRow
            label="模型"
            value={modelName || pMeta?.defaultModel || '—'}
          />
          <SummaryRow label="搜索" value={searchLabels[searchMode]} />
          <SummaryRow label="Fetch" value={fetchLabels[fetchMode]} />
          <SummaryRow label="论文" value={papersLabels[papersMode]} />
          <SummaryRow label="Agent 名称" value={agentName || 'miqi'} />
          <SummaryRow
            label="Soul"
            value={
              SOUL_PRESETS.find((s) => s.key === soulPreset)?.label ??
              soulPreset
            }
          />
        </div>

        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => setStep('agent')}>
            <ArrowLeft size={16} /> 返回
          </Button>
          <Button onClick={handleFinish}>
            <Key size={16} /> 保存并启动
          </Button>
        </div>
      </div>
    )
  }

  // -----------------------------------------------------------------------
  // Shell
  // -----------------------------------------------------------------------
  const ALL_STEPS: Step[] = [
    'welcome',
    'environment',
    'wsl2',
    'provider',
    'webtools',
    'papers',
    'agent',
    'finish',
  ]
  const stepIdx = ALL_STEPS.indexOf(step)

  return (
    <div className="flex items-center justify-center min-h-full bg-[var(--background)] py-8">
      <div className="w-full max-w-lg bg-[var(--surface-elevated)] border border-[var(--border)] rounded-xl shadow-sm p-8 relative">
        {/* Exit button — only show when onExit is provided (re-running from settings) */}
        {onExit && step !== 'finish' && (
          <button
            onClick={onExit}
            className="absolute top-4 right-4 p-1.5 rounded-lg text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-muted)] transition-colors"
            title="退出配置向导"
          >
            <X size={16} />
          </button>
        )}
        {/* Step indicators */}
        <div className="flex items-center justify-center gap-1.5 mb-8">
          {ALL_STEPS.map((s, i) => (
            <div key={s} className="flex items-center gap-1.5">
              <div
                className={cn(
                  'w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-medium transition-colors',
                  step === s
                    ? 'bg-[var(--accent)] text-white'
                    : i < stepIdx
                      ? 'bg-[var(--success)]/30 text-[var(--success)]'
                      : 'bg-[var(--surface-muted)] text-[var(--text-faint)]',
                )}
              >
                {i < stepIdx ? <Check size={10} /> : i + 1}
              </div>
              {i < ALL_STEPS.length - 1 && (
                <div className="w-4 h-px bg-[var(--border)]" />
              )}
            </div>
          ))}
        </div>

        {step === 'welcome' && renderWelcome()}
        {step === 'environment' && renderEnvironment()}
        {step === 'wsl2' && renderWsl2()}
        {step === 'provider' && renderProvider()}
        {step === 'webtools' && renderWebTools()}
        {step === 'papers' && renderPapers()}
        {step === 'agent' && renderAgent()}
        {step === 'finish' && renderFinish()}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Small helper components
// ---------------------------------------------------------------------------
function CheckItem({
  label,
  ok,
  detail,
}: {
  label: string
  ok: boolean
  detail?: string
}) {
  return (
    <div className="flex items-center gap-2">
      {ok ? (
        <Check size={14} className="text-[var(--success)] shrink-0" />
      ) : (
        <X size={14} className="text-[var(--danger)] shrink-0" />
      )}
      <span className={ok ? 'text-[var(--text)]' : 'text-[var(--danger)]'}>
        {label}
      </span>
      {detail && (
        <span className="text-[var(--text-faint)] text-xs">{detail}</span>
      )}
    </div>
  )
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span>{label}</span>
      <span className="text-[var(--text)] font-medium truncate max-w-[200px] text-right">
        {value}
      </span>
    </div>
  )
}
