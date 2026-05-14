import { useState, useEffect, useRef } from 'react'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { ScrollArea } from '../../components/ui/ScrollArea'
import { cn } from '../../lib/utils'
import { RefreshCw, Download, Save, Eye, EyeOff, Check } from 'lucide-react'
import { useRuntime } from '../../contexts/RuntimeContext'
import * as Tabs from '@radix-ui/react-tabs'

// ---- Helpers ----
function getNestedStr(obj: Record<string, unknown>, ...keys: string[]): string {
  let cur: unknown = obj
  for (const k of keys) {
    if (cur == null || typeof cur !== 'object') return ''
    cur = (cur as Record<string, unknown>)[k]
  }
  return cur == null ? '' : String(cur)
}

// ---- General Config Tab ----
function GeneralTab() {
  const [agentName, setAgentName] = useState('')
  const [workspace, setWorkspace] = useState('')
  const [model, setModel] = useState('')
  const [temperature, setTemperature] = useState('')
  const [maxTokens, setMaxTokens] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    window.miqi.config
      .get()
      .then((cfg) => {
        setAgentName(getNestedStr(cfg, 'agents', 'defaults', 'name'))
        setWorkspace(getNestedStr(cfg, 'agents', 'defaults', 'workspace'))
        setModel(getNestedStr(cfg, 'agents', 'defaults', 'model'))
        const temp = getNestedStr(cfg, 'agents', 'defaults', 'temperature')
        setTemperature(temp)
        const mt = getNestedStr(cfg, 'agents', 'defaults', 'maxTokens')
        setMaxTokens(mt)
      })
      .catch(() => {})
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      const defaults: Record<string, unknown> = {}
      if (agentName) defaults['name'] = agentName
      if (workspace) defaults['workspace'] = workspace
      if (model) defaults['model'] = model
      if (temperature) defaults['temperature'] = parseFloat(temperature)
      if (maxTokens) defaults['maxTokens'] = parseInt(maxTokens)
      await window.miqi.config.update({ agents: { defaults } })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch {
      /* ignore */
    }
    setSaving(false)
  }

  return (
    <div className="p-6 max-w-lg flex flex-col gap-4">
      <h3 className="text-sm font-semibold text-[var(--text)]">Agent 配置</h3>

      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)]">
          Agent 名称
        </label>
        <Input
          value={agentName}
          onChange={(e) => setAgentName(e.target.value)}
          placeholder="miqi"
        />
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
            浏览
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)]">
          默认模型
        </label>
        <Input
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder="provider/model-name"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-[var(--text-muted)]">
            Temperature
          </label>
          <Input
            type="number"
            min="0"
            max="2"
            step="0.05"
            value={temperature}
            onChange={(e) => setTemperature(e.target.value)}
            placeholder="0.1"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-[var(--text-muted)]">
            Max Tokens
          </label>
          <Input
            type="number"
            min="256"
            max="200000"
            step="256"
            value={maxTokens}
            onChange={(e) => setMaxTokens(e.target.value)}
            placeholder="8192"
          />
        </div>
      </div>

      <Button
        onClick={handleSave}
        disabled={saving}
        className="self-start mt-2"
      >
        {saved ? <Check size={14} /> : <Save size={14} />}
        {saved ? '已保存' : '保存'}
      </Button>
    </div>
  )
}

// ---- Web Tools Tab ----
function WebToolsTab() {
  // ---- Web Search ----
  const [searchProvider, setSearchProvider] = useState('brave')
  const [braveKey, setBraveKey] = useState('')
  const [searchOllamaBase, setSearchOllamaBase] = useState('')
  const [searchOllamaKey, setSearchOllamaKey] = useState('')

  // ---- Web Fetch ----
  const [fetchProvider, setFetchProvider] = useState('builtin')
  const [fetchOllamaBase, setFetchOllamaBase] = useState('')
  const [fetchOllamaKey, setFetchOllamaKey] = useState('')

  // ---- Papers ----
  const [papersProvider, setPapersProvider] = useState('hybrid')
  const [s2ApiKey, setS2ApiKey] = useState('')

  const [showKeys, setShowKeys] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    window.miqi.config
      .get()
      .then((cfg) => {
        setSearchProvider(
          getNestedStr(cfg, 'tools', 'web', 'search', 'provider') || 'brave',
        )
        setBraveKey(getNestedStr(cfg, 'tools', 'web', 'search', 'apiKey'))
        setSearchOllamaBase(
          getNestedStr(cfg, 'tools', 'web', 'search', 'ollamaApiBase'),
        )
        setSearchOllamaKey(
          getNestedStr(cfg, 'tools', 'web', 'search', 'ollamaApiKey'),
        )
        setFetchProvider(
          getNestedStr(cfg, 'tools', 'web', 'fetch', 'provider') || 'builtin',
        )
        setFetchOllamaBase(
          getNestedStr(cfg, 'tools', 'web', 'fetch', 'ollamaApiBase'),
        )
        setFetchOllamaKey(
          getNestedStr(cfg, 'tools', 'web', 'fetch', 'ollamaApiKey'),
        )
        setPapersProvider(
          getNestedStr(cfg, 'tools', 'papers', 'provider') || 'hybrid',
        )
        setS2ApiKey(
          getNestedStr(cfg, 'tools', 'papers', 'semanticScholarApiKey'),
        )
      })
      .catch(() => {})
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      await window.miqi.config.update({
        tools: {
          web: {
            search: {
              provider: searchProvider,
              apiKey: braveKey || undefined,
              ollamaApiBase: searchOllamaBase || undefined,
              ollamaApiKey: searchOllamaKey || undefined,
            },
            fetch: {
              provider: fetchProvider,
              ollamaApiBase: fetchOllamaBase || undefined,
              ollamaApiKey: fetchOllamaKey || undefined,
            },
          },
          papers: {
            provider: papersProvider,
            semanticScholarApiKey: s2ApiKey || undefined,
          },
        },
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch {
      /* ignore */
    }
    setSaving(false)
  }

  const ModeBtn = ({
    value,
    current,
    set,
    label,
  }: {
    value: string
    current: string
    set: (v: string) => void
    label: string
  }) => (
    <button
      onClick={() => set(value)}
      className={cn(
        'px-3 py-1.5 rounded-lg text-xs border transition-colors',
        current === value
          ? 'bg-[var(--accent)] text-white border-[var(--accent)]'
          : 'bg-[var(--surface)] text-[var(--text-muted)] border-[var(--border)] hover:border-[var(--accent)]',
      )}
    >
      {label}
    </button>
  )

  return (
    <div className="p-6 max-w-lg flex flex-col gap-6">
      {/* ---- Web Search ---- */}
      <section className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-[var(--text)]">Web 搜索</h3>
        <div className="flex gap-2">
          <ModeBtn
            value="brave"
            current={searchProvider}
            set={setSearchProvider}
            label="Brave"
          />
          <ModeBtn
            value="ollama"
            current={searchProvider}
            set={setSearchProvider}
            label="Ollama"
          />
          <ModeBtn
            value="hybrid"
            current={searchProvider}
            set={setSearchProvider}
            label="Hybrid"
          />
        </div>
        {(searchProvider === 'brave' || searchProvider === 'hybrid') && (
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-[var(--text-muted)]">
              Brave Search API Key
            </label>
            <div className="flex gap-2">
              <Input
                type={showKeys ? 'text' : 'password'}
                value={braveKey}
                onChange={(e) => setBraveKey(e.target.value)}
                placeholder="BSA..."
                className="flex-1 font-mono text-xs"
              />
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setShowKeys((v) => !v)}
              >
                {showKeys ? <EyeOff size={14} /> : <Eye size={14} />}
              </Button>
            </div>
          </div>
        )}
        {(searchProvider === 'ollama' || searchProvider === 'hybrid') && (
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
                type={showKeys ? 'text' : 'password'}
                value={searchOllamaKey}
                onChange={(e) => setSearchOllamaKey(e.target.value)}
                placeholder="ollama-key..."
                className="font-mono text-xs"
              />
            </div>
          </div>
        )}
      </section>

      {/* ---- Web Fetch ---- */}
      <section className="flex flex-col gap-3 pt-4 border-t border-[var(--border-subtle)]">
        <h3 className="text-sm font-semibold text-[var(--text)]">Web Fetch</h3>
        <div className="flex gap-2">
          <ModeBtn
            value="builtin"
            current={fetchProvider}
            set={setFetchProvider}
            label="内置"
          />
          <ModeBtn
            value="ollama"
            current={fetchProvider}
            set={setFetchProvider}
            label="Ollama"
          />
          <ModeBtn
            value="hybrid"
            current={fetchProvider}
            set={setFetchProvider}
            label="Hybrid"
          />
        </div>
        {(fetchProvider === 'ollama' || fetchProvider === 'hybrid') && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-[var(--text-muted)]">
                Ollama web_fetch Base URL
              </label>
              <Input
                value={fetchOllamaBase}
                onChange={(e) => setFetchOllamaBase(e.target.value)}
                placeholder="https://ollama.com"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-[var(--text-muted)]">
                Ollama web_fetch API Key
              </label>
              <Input
                type={showKeys ? 'text' : 'password'}
                value={fetchOllamaKey}
                onChange={(e) => setFetchOllamaKey(e.target.value)}
                placeholder="留空则复用 web_search Key"
                className="font-mono text-xs"
              />
            </div>
          </div>
        )}
      </section>

      {/* ---- Papers ---- */}
      <section className="flex flex-col gap-3 pt-4 border-t border-[var(--border-subtle)]">
        <h3 className="text-sm font-semibold text-[var(--text)]">
          论文研究工具
        </h3>
        <div className="flex gap-2">
          <ModeBtn
            value="hybrid"
            current={papersProvider}
            set={setPapersProvider}
            label="Hybrid（推荐）"
          />
          <ModeBtn
            value="semantic_scholar"
            current={papersProvider}
            set={setPapersProvider}
            label="S2"
          />
          <ModeBtn
            value="arxiv"
            current={papersProvider}
            set={setPapersProvider}
            label="arXiv"
          />
        </div>
        {(papersProvider === 'hybrid' ||
          papersProvider === 'semantic_scholar') && (
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-[var(--text-muted)]">
              Semantic Scholar API Key（可选）
            </label>
            <Input
              type={showKeys ? 'text' : 'password'}
              value={s2ApiKey}
              onChange={(e) => setS2ApiKey(e.target.value)}
              placeholder="可选，填写后减少限流"
              className="font-mono text-xs"
            />
          </div>
        )}
      </section>

      <Button onClick={handleSave} disabled={saving} className="self-start">
        {saved ? <Check size={14} /> : <Save size={14} />}
        {saved ? '已保存' : '保存所有 Web 设置'}
      </Button>
    </div>
  )
}

// ---- Appearance Tab ----
type ThemeMode = 'light' | 'dark' | 'system'

function AppearanceTab() {
  const [theme, setTheme] = useState<ThemeMode>(() => {
    return (localStorage.getItem('miqi-theme') as ThemeMode) ?? 'system'
  })

  const applyTheme = (mode: ThemeMode) => {
    setTheme(mode)
    localStorage.setItem('miqi-theme', mode)
    const root = document.documentElement
    if (mode === 'dark') {
      root.classList.add('dark')
    } else if (mode === 'light') {
      root.classList.remove('dark')
    } else {
      // system
      const prefersDark = window.matchMedia(
        '(prefers-color-scheme: dark)',
      ).matches
      root.classList.toggle('dark', prefersDark)
    }
  }

  return (
    <div className="p-6 max-w-lg flex flex-col gap-4">
      <h3 className="text-sm font-semibold text-[var(--text)]">外观</h3>
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)]">
          主题
        </label>
        <div className="flex gap-2">
          {(['light', 'dark', 'system'] as ThemeMode[]).map((m) => (
            <button
              key={m}
              onClick={() => applyTheme(m)}
              className={cn(
                'px-4 py-2 rounded-lg text-xs border transition-colors',
                theme === m
                  ? 'bg-[var(--accent)] text-white border-[var(--accent)]'
                  : 'bg-[var(--surface)] text-[var(--text-muted)] border-[var(--border)] hover:border-[var(--accent)] hover:text-[var(--text)]',
              )}
            >
              {m === 'light' ? '浅色' : m === 'dark' ? '深色' : '跟随系统'}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

// ---- Logs Tab (existing) ----
function LogsTab() {
  const { logs, refreshLogs } = useRuntime()
  const [autoScroll, setAutoScroll] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  const handleExport = () => {
    const text = logs.join('\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `miqi-logs-${new Date().toISOString().slice(0, 10)}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-6 py-3 border-b border-[var(--border-subtle)]">
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] cursor-pointer">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="rounded"
            />
            自动滚动
          </label>
          <Button variant="ghost" size="icon" onClick={refreshLogs}>
            <RefreshCw size={14} />
          </Button>
        </div>
        <Button variant="outline" size="sm" onClick={handleExport}>
          <Download size={14} /> 导出日志
        </Button>
      </div>
      <ScrollArea className="flex-1">
        <div
          ref={scrollRef}
          className="p-4 font-mono text-xs leading-relaxed text-[var(--text)] overflow-y-auto h-full"
        >
          {logs.length === 0 ? (
            <div className="flex items-center justify-center h-full text-[var(--text-muted)] py-16">
              暂无日志。启动运行时后将在此显示输出。
            </div>
          ) : (
            logs.map((line, i) => (
              <div
                key={i}
                className={cn(
                  'py-0.5',
                  line.includes('[ERROR]') || line.includes('ERROR')
                    ? 'text-[var(--danger)]'
                    : line.includes('[WARNING]') || line.includes('WARNING')
                      ? 'text-[var(--warning)]'
                      : 'text-[var(--text-muted)]',
                )}
              >
                {line}
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  )
}

// ---- Main ----
export function SettingsPage() {
  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-4 border-b border-[var(--border-subtle)]">
        <h2 className="text-sm font-semibold text-[var(--text)]">设置</h2>
        <p className="text-xs text-[var(--text-faint)] mt-0.5">
          配置 MiQi Agent 和外观
        </p>
      </div>

      <Tabs.Root
        defaultValue="general"
        className="flex flex-col flex-1 min-h-0"
      >
        <Tabs.List className="flex gap-0 px-4 border-b border-[var(--border-subtle)] shrink-0">
          {[
            { value: 'general', label: '通用' },
            { value: 'webtools', label: 'Web 工具' },
            { value: 'appearance', label: '外观' },
            { value: 'logs', label: '运行日志' },
          ].map((tab) => (
            <Tabs.Trigger
              key={tab.value}
              value={tab.value}
              className={cn(
                'px-4 py-2.5 text-xs font-medium border-b-2 -mb-px transition-colors',
                'text-[var(--text-muted)] border-transparent',
                'hover:text-[var(--text)]',
                'data-[state=active]:text-[var(--accent)] data-[state=active]:border-[var(--accent)]',
              )}
            >
              {tab.label}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        <Tabs.Content value="general" className="flex-1 overflow-y-auto">
          <GeneralTab />
        </Tabs.Content>
        <Tabs.Content value="webtools" className="flex-1 overflow-y-auto">
          <WebToolsTab />
        </Tabs.Content>
        <Tabs.Content value="appearance" className="flex-1 overflow-y-auto">
          <AppearanceTab />
        </Tabs.Content>
        <Tabs.Content value="logs" className="flex-1 min-h-0 flex flex-col">
          <LogsTab />
        </Tabs.Content>
      </Tabs.Root>
    </div>
  )
}
