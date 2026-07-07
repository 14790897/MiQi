import { useState, useEffect, useRef, useCallback } from 'react';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { ScrollArea } from '../../components/ui/ScrollArea';
import { cn } from '../../lib/utils';
import {
  RefreshCw,
  Download,
  Save,
  Eye,
  EyeOff,
  Check,
  RotateCcw,
  Archive,
  RotateCcw as Unarchive,
  ExternalLink,
  Copy,
} from 'lucide-react';
import { useRuntime } from '../../contexts/RuntimeContext';
import * as Tabs from '@radix-ui/react-tabs';
import { ProvidersPage } from '../providers/ProvidersPage';
import { ChannelsPage } from '../channels/ChannelsPage';
import { ApprovalsPage } from '../approvals/ApprovalsPage';
import { WorkspacePage } from '../workspace/WorkspacePage';
import { CronPage } from '../cron/CronPage';
import { MCPsPage } from '../mcps/MCPsPage';
import { ExperiencePage } from '../experience/ExperiencePage';
import { SkillsPage } from '../skills/SkillsPage';
import { MemoryPage } from '../memory/MemoryPage';
import AgentPanel from '../agents/AgentPanel';
import { PermissionsPage } from '../permissions/PermissionsPage';
import { PluginMarket } from '../plugins/PluginMarket';
import WslStatusPage from '../wsl/WslStatusPage';

export type SettingsTab =
  | 'general'
  | 'providers'
  | 'channels'
  | 'approvals'
  | 'workspace'
  | 'webtools'
  | 'appearance'
  | 'agents'
  | 'skills'
  | 'mcps'
  | 'memory'
  | 'experience'
  | 'permissions'
  | 'plugins'
  | 'wsl'
  | 'logs'
  | 'archived'
  | 'docs';

// ---- Helpers ----
function getNestedStr(obj: Record<string, unknown>, ...keys: string[]): string {
  let cur: unknown = obj;
  for (const k of keys) {
    if (cur == null || typeof cur !== 'object') return '';
    cur = (cur as Record<string, unknown>)[k];
  }
  return cur == null ? '' : String(cur);
}

// ---- General Config Tab ----
function GeneralTab({ onReopenSetup }: { onReopenSetup?: () => void }) {
  const [agentName, setAgentName] = useState('');
  const [workspace, setWorkspace] = useState('');
  const [model, setModel] = useState('');
  const [temperature, setTemperature] = useState('');
  const [maxTokens, setMaxTokens] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    window.miqi.config
      .get()
      .then((cfg) => {
        setAgentName(getNestedStr(cfg, 'agents', 'defaults', 'name'));
        setWorkspace(getNestedStr(cfg, 'agents', 'defaults', 'workspace'));
        setModel(getNestedStr(cfg, 'agents', 'defaults', 'model'));
        const temp = getNestedStr(cfg, 'agents', 'defaults', 'temperature');
        setTemperature(temp);
        const mt = getNestedStr(cfg, 'agents', 'defaults', 'maxTokens');
        setMaxTokens(mt);
      })
      .catch(() => {});
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const defaults: Record<string, unknown> = {};
      if (agentName) defaults['name'] = agentName;
      if (workspace) defaults['workspace'] = workspace;
      if (model) defaults['model'] = model;
      if (temperature) defaults['temperature'] = parseFloat(temperature);
      if (maxTokens) defaults['maxTokens'] = parseInt(maxTokens);
      await window.miqi.config.update({ agents: { defaults } });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {
      /* ignore */
    }
    setSaving(false);
  };

  return (
    <div className="p-6 max-w-lg flex flex-col gap-4">
      <h3 className="text-sm font-semibold text-[var(--text)]">Agent 配置</h3>

      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)]">Agent 名称</label>
        <Input
          value={agentName}
          onChange={(e) => setAgentName(e.target.value)}
          placeholder="miqi"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)]">工作目录</label>
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
              const dir = await window.miqi.dialog.openFile();
              if (dir) setWorkspace(dir);
            }}
          >
            浏览
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)]">默认模型</label>
        <Input
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder="provider/model-name"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-[var(--text-muted)]">Temperature</label>
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
          <label className="text-xs font-medium text-[var(--text-muted)]">Max Tokens</label>
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

      <Button onClick={handleSave} disabled={saving} className="self-start mt-2">
        {saved ? <Check size={14} /> : <Save size={14} />}
        {saved ? '已保存' : '保存'}
      </Button>

      {/* ---- Danger Zone ---- */}
      <div className="mt-6 pt-4 border-t border-[var(--border-subtle)]">
        <h3 className="text-sm font-semibold text-[var(--text)] mb-1">重新配置</h3>
        <p className="text-xs text-[var(--text-faint)] mb-3">
          重新运行配置向导，可修改 Python 路径、WSL2 环境和模型 Provider 等初始设置。
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={onReopenSetup}
          className="text-[var(--warning)] border-[var(--warning)] hover:bg-[var(--warning)] hover:bg-opacity-10"
        >
          <RotateCcw size={14} />
          重新运行配置向导
        </Button>
      </div>
    </div>
  );
}

// ---- Web Tools Tab ----
function WebToolsTab() {
  // ---- Web Search ----
  const [searchProvider, setSearchProvider] = useState('ddgs');
  const [braveKey, setBraveKey] = useState('');

  // ---- Web Fetch ----
  const [fetchProvider, setFetchProvider] = useState('builtin');
  const [fetchOllamaBase, setFetchOllamaBase] = useState('');
  const [fetchOllamaKey, setFetchOllamaKey] = useState('');

  // ---- Papers ----
  const [papersProvider, setPapersProvider] = useState('hybrid');
  const [s2ApiKey, setS2ApiKey] = useState('');

  const [showKeys, setShowKeys] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    window.miqi.config
      .get()
      .then((cfg) => {
        const storedSearchProvider =
          getNestedStr(cfg, 'tools', 'web', 'search', 'provider') || 'ddgs';
        setSearchProvider(storedSearchProvider === 'ollama' ? 'ddgs' : storedSearchProvider);
        setBraveKey(getNestedStr(cfg, 'tools', 'web', 'search', 'apiKey'));
        setFetchProvider(getNestedStr(cfg, 'tools', 'web', 'fetch', 'provider') || 'builtin');
        setFetchOllamaBase(getNestedStr(cfg, 'tools', 'web', 'fetch', 'ollamaApiBase'));
        setFetchOllamaKey(getNestedStr(cfg, 'tools', 'web', 'fetch', 'ollamaApiKey'));
        setPapersProvider(getNestedStr(cfg, 'tools', 'papers', 'provider') || 'hybrid');
        setS2ApiKey(getNestedStr(cfg, 'tools', 'papers', 'semanticScholarApiKey'));
      })
      .catch(() => {});
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await window.miqi.config.update({
        tools: {
          web: {
            search: {
              provider: searchProvider,
              apiKey: braveKey || undefined,
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
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {
      /* ignore */
    }
    setSaving(false);
  };

  const ModeBtn = ({
    value,
    current,
    set,
    label,
  }: {
    value: string;
    current: string;
    set: (v: string) => void;
    label: string;
  }) => (
    <button
      onClick={() => set(value)}
      className={cn(
        'px-3 py-1.5 rounded-lg text-xs border transition-colors',
        current === value
          ? 'bg-[var(--accent)] text-white border-[var(--accent)]'
          : 'bg-[var(--surface)] text-[var(--text-muted)] border-[var(--border)] hover:border-[var(--accent)]'
      )}
    >
      {label}
    </button>
  );

  return (
    <div className="p-6 max-w-lg flex flex-col gap-6">
      {/* ---- Web Search ---- */}
      <section className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-[var(--text)]">Web 搜索</h3>
        <div className="flex gap-2">
          <ModeBtn value="ddgs" current={searchProvider} set={setSearchProvider} label="DuckDuckGo" />
          <ModeBtn value="brave" current={searchProvider} set={setSearchProvider} label="Brave" />
          <ModeBtn value="hybrid" current={searchProvider} set={setSearchProvider} label="Hybrid" />
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
              <Button variant="ghost" size="icon" onClick={() => setShowKeys((v) => !v)}>
                {showKeys ? <EyeOff size={14} /> : <Eye size={14} />}
              </Button>
            </div>
          </div>
        )}
      </section>

      {/* ---- Web Fetch ---- */}
      <section className="flex flex-col gap-3 pt-4 border-t border-[var(--border-subtle)]">
        <h3 className="text-sm font-semibold text-[var(--text)]">Web Fetch</h3>
        <div className="flex gap-2">
          <ModeBtn value="builtin" current={fetchProvider} set={setFetchProvider} label="内置" />
          <ModeBtn value="ollama" current={fetchProvider} set={setFetchProvider} label="Ollama" />
          <ModeBtn value="hybrid" current={fetchProvider} set={setFetchProvider} label="Hybrid" />
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
                placeholder="ollama-key..."
                className="font-mono text-xs"
              />
            </div>
          </div>
        )}
      </section>

      {/* ---- Papers ---- */}
      <section className="flex flex-col gap-3 pt-4 border-t border-[var(--border-subtle)]">
        <h3 className="text-sm font-semibold text-[var(--text)]">论文研究工具</h3>
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
          <ModeBtn value="arxiv" current={papersProvider} set={setPapersProvider} label="arXiv" />
        </div>
        {(papersProvider === 'hybrid' || papersProvider === 'semantic_scholar') && (
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
  );
}

// ---- Appearance Tab ----
type ThemeMode = 'light' | 'dark' | 'system';

function AppearanceTab() {
  const [theme, setTheme] = useState<ThemeMode>(() => {
    return (localStorage.getItem('miqi-theme') as ThemeMode) ?? 'system';
  });

  const applyTheme = (mode: ThemeMode) => {
    setTheme(mode);
    localStorage.setItem('miqi-theme', mode);
    const root = document.documentElement;
    if (mode === 'dark') {
      root.classList.add('dark');
    } else if (mode === 'light') {
      root.classList.remove('dark');
    } else {
      // system
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      root.classList.toggle('dark', prefersDark);
    }
  };

  return (
    <div className="p-6 max-w-lg flex flex-col gap-4">
      <h3 className="text-sm font-semibold text-[var(--text)]">外观</h3>
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)]">主题</label>
        <div className="flex gap-2">
          {(['light', 'dark', 'system'] as ThemeMode[]).map((m) => (
            <button
              key={m}
              onClick={() => applyTheme(m)}
              className={cn(
                'px-4 py-2 rounded-lg text-xs border transition-colors',
                theme === m
                  ? 'bg-[var(--accent)] text-white border-[var(--accent)]'
                  : 'bg-[var(--surface)] text-[var(--text-muted)] border-[var(--border)] hover:border-[var(--accent)] hover:text-[var(--text)]'
              )}
            >
              {m === 'light' ? '浅色' : m === 'dark' ? '深色' : '跟随系统'}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---- Logs Tab (existing) ----
function LogsTab() {
  const { logs, refreshLogs } = useRuntime();
  const [autoScroll, setAutoScroll] = useState(true);
  const [copiedLogs, setCopiedLogs] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(logs.join('\n'));
    setCopiedLogs(true);
    setTimeout(() => setCopiedLogs(false), 1500);
  };

  const handleExport = () => {
    const text = logs.join('\n');
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `miqi-logs-${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

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
        <Button variant="outline" size="sm" onClick={handleCopy}>
          {copiedLogs ? <Check size={14} /> : <Copy size={14} />}
          {copiedLogs ? '已复制' : '复制日志'}
        </Button>
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
                      : 'text-[var(--text-muted)]'
                )}
              >
                {line}
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

// ---- Archived Sessions Tab ----
function ArchivedTab({ onRestore }: { onRestore?: (key: string) => void }) {
  const [sessions, setSessions] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await window.miqi.sessions.listArchived();
      setSessions(r?.sessions ?? []);
    } catch {
      /* ignore */
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleRestore = async (key: string, title: string) => {
    await window.miqi.sessions.unarchive(key);
    await load();
    onRestore?.(key);
  };

  const handleDelete = async (key: string, title: string) => {
    if (!window.confirm(`永久删除对话「${title}」？此操作不可撤销。`)) return;
    await window.miqi.sessions.delete(key);
    await load();
  };

  function formatTime(iso?: string): string {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  return (
    <div className="p-6 max-w-2xl flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--text)]">已归档对话</h3>
        <Button variant="ghost" size="icon" onClick={load} disabled={loading}>
          <RefreshCw size={14} className={cn(loading && 'animate-spin')} />
        </Button>
      </div>

      {sessions.length === 0 ? (
        <div className="text-xs text-[var(--text-faint)] text-center py-12">暂无已归档的对话</div>
      ) : (
        <div className="flex flex-col border border-[var(--border-subtle)] rounded-lg overflow-hidden">
          {sessions.map((s) => (
            <div
              key={s.key}
              className="flex items-center gap-3 px-4 py-3 border-b border-[var(--border-subtle)] last:border-b-0"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm truncate text-[var(--text)]">{s.title || s.key}</p>
                <p className="text-xs text-[var(--text-faint)]">{formatTime(s.updated_at)}</p>
              </div>
              <button
                onClick={() => handleRestore(s.key, s.title || s.key)}
                className="flex items-center gap-1 px-2 py-1 rounded text-xs text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-muted)] transition-colors"
                title="恢复对话"
              >
                <Unarchive size={12} />
                恢复
              </button>
              <button
                onClick={() => handleDelete(s.key, s.title || s.key)}
                className="flex items-center gap-1 px-2 py-1 rounded text-xs text-[var(--text-faint)] hover:text-[var(--danger)] hover:bg-[var(--surface-muted)] transition-colors"
                title="永久删除"
              >
                <Archive size={12} />
                删除
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---- Docs Tab ----
const DOCS_BASE = 'https://mygithub.sixiangjia.de/MiQi/';

interface DocLink {
  label: string;
  href: string;
  children?: DocLink[];
}

const DOCS_TREE: DocLink[] = [
  { label: '🚀 快速开始', href: 'getting-started/' },
  {
    label: '🏗️ 系统架构',
    href: 'architecture/',
    children: [
      { label: '整体架构', href: 'architecture/' },
      { label: '数据流', href: 'architecture/data-flow/' },
      { label: '项目结构', href: 'architecture/project-structure/' },
    ],
  },
  {
    label: '🐍 Python 后端',
    href: 'backend/agent/',
    children: [
      { label: 'Agent 引擎', href: 'backend/agent/' },
      { label: '工具系统', href: 'backend/tools/' },
      { label: 'Provider 系统', href: 'backend/providers/' },
      { label: '记忆系统', href: 'backend/memory/' },
      { label: '会话管理', href: 'backend/session/' },
      { label: '任务追踪', href: 'backend/trace/' },
      { label: 'Bridge 通信', href: 'backend/bridge/' },
    ],
  },
  {
    label: '💻 Electron 前端',
    href: 'frontend/overview/',
    children: [
      { label: '前端概览', href: 'frontend/overview/' },
      { label: 'IPC 通信', href: 'frontend/ipc/' },
      { label: '功能页面', href: 'frontend/features/' },
      { label: 'SkillHub', href: 'frontend/skillhub/' },
    ],
  },
  { label: '🔌 MCP 集成', href: 'mcp-integration/' },
  {
    label: '⚙️ 配置与部署',
    href: 'configuration/',
    children: [
      { label: '配置参考', href: 'configuration/' },
      { label: 'Docker 部署', href: 'deployment/docker/' },
      { label: '桌面打包', href: 'deployment/packaging/' },
    ],
  },
  {
    label: '🛠️ 开发指南',
    href: 'developer-guide/',
    children: [
      { label: '开发环境搭建', href: 'developer-guide/' },
      { label: '贡献指南', href: 'contributing/' },
    ],
  },
  { label: '📝 更新日志', href: 'changelog/' },
];

function DocsTab() {
  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-6 pt-5 pb-3 shrink-0">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-[var(--text)]">MiQi Desktop 文档</h3>
          <a
            href={DOCS_BASE}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors"
          >
            <ExternalLink size={12} />
            完整文档站点
          </a>
        </div>
        <p className="text-xs text-[var(--text-faint)] mt-1">点击章节在浏览器中打开对应文档页面</p>
      </div>

      <div className="px-6 pb-6 flex flex-col gap-3">
        {DOCS_TREE.map((section) => (
          <div
            key={section.href}
            className="border border-[var(--border-subtle)] rounded-lg overflow-hidden"
          >
            <a
              href={DOCS_BASE + section.href}
              target="_blank"
              rel="noopener noreferrer"
              className="block px-4 py-2.5 text-xs font-semibold text-[var(--text)] bg-[var(--surface-muted)] hover:bg-[var(--accent)]/10 transition-colors"
            >
              {section.label}
            </a>
            {section.children && (
              <div className="flex flex-col">
                {section.children.map((child) => (
                  <a
                    key={child.href}
                    href={DOCS_BASE + child.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block px-4 py-2 text-xs text-[var(--text-muted)] hover:text-[var(--accent)] hover:bg-[var(--surface-muted)] transition-colors border-t border-[var(--border-subtle)]"
                  >
                    {child.label}
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}

        <div className="mt-2 pt-4 border-t border-[var(--border-subtle)]">
          <a
            href="https://github.com/14790897/miqi"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 text-xs text-[var(--text-faint)] hover:text-[var(--accent)] transition-colors"
          >
            <ExternalLink size={12} />
            GitHub 仓库：14790897/miqi
          </a>
        </div>
      </div>
    </div>
  );
}

// ---- Main ----
export function SettingsPage({ onReopenSetup, tab = 'general' }: { onReopenSetup?: () => void; tab?: SettingsTab }) {
  const [activeTab, setActiveTab] = useState<SettingsTab>(tab);

  useEffect(() => { setActiveTab(tab); }, [tab]);

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-4 border-b border-[var(--border-subtle)]">
        <h2 className="text-sm font-semibold text-[var(--text)]">设置</h2>
        <p className="text-xs text-[var(--text-faint)] mt-0.5">配置 MiQi Agent 和外观</p>
      </div>

      <Tabs.Root
        value={activeTab}
        onValueChange={(v) => setActiveTab(v as SettingsTab)}
        className="flex flex-col flex-1 min-h-0"
      >
        <Tabs.List className="flex gap-0 px-4 border-b border-[var(--border-subtle)] shrink-0 overflow-x-auto">
          {[
            { value: 'general', label: '通用' },
            { value: 'providers', label: '模型' },
            { value: 'channels', label: '渠道' },
            { value: 'agents', label: 'Agents' },
            { value: 'skills', label: '技能' },
            { value: 'mcps', label: 'MCPs' },
            { value: 'memory', label: '记忆' },
            { value: 'experience', label: '经验' },
            { value: 'approvals', label: '审批' },
            { value: 'workspace', label: '工作区' },
            { value: 'webtools', label: 'Web 工具' },
            { value: 'permissions', label: '权限' },
            { value: 'plugins', label: '插件' },
            { value: 'wsl', label: 'WSL' },
            { value: 'appearance', label: '外观' },
            { value: 'logs', label: '日志' },
            { value: 'archived', label: '已归档' },
            { value: 'docs', label: '文档' },
          ].map((tab) => (
            <Tabs.Trigger
              key={tab.value}
              value={tab.value}
              className={cn(
                'px-4 py-2.5 text-xs font-medium border-b-2 -mb-px transition-colors whitespace-nowrap',
                'text-[var(--text-muted)] border-transparent',
                'hover:text-[var(--text)]',
                'data-[state=active]:text-[var(--accent)] data-[state=active]:border-[var(--accent)]'
              )}
            >
              {tab.label}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        <Tabs.Content value="general" className="flex-1 overflow-y-auto">
          <GeneralTab onReopenSetup={onReopenSetup} />
        </Tabs.Content>
        <Tabs.Content value="providers" className="flex-1 overflow-y-auto">
          <ProvidersPage />
        </Tabs.Content>
        <Tabs.Content value="channels" className="flex-1 overflow-y-auto">
          <ChannelsPage />
        </Tabs.Content>
        <Tabs.Content value="approvals" className="flex-1 overflow-y-auto">
          <ApprovalsPage />
        </Tabs.Content>
        <Tabs.Content value="workspace" className="flex-1 overflow-y-auto">
          <WorkspacePage />
        </Tabs.Content>
        <Tabs.Content value="agents" className="flex-1 overflow-y-auto">
          <AgentPanel />
        </Tabs.Content>
        <Tabs.Content value="skills" className="flex-1 overflow-y-auto">
          <SkillsPage />
        </Tabs.Content>
        <Tabs.Content value="mcps" className="flex-1 overflow-y-auto">
          <MCPsPage />
        </Tabs.Content>
        <Tabs.Content value="memory" className="flex-1 overflow-y-auto">
          <MemoryPage />
        </Tabs.Content>
        <Tabs.Content value="experience" className="flex-1 overflow-y-auto">
          <ExperiencePage />
        </Tabs.Content>
        <Tabs.Content value="permissions" className="flex-1 overflow-y-auto">
          <PermissionsPage />
        </Tabs.Content>
        <Tabs.Content value="plugins" className="flex-1 overflow-y-auto">
          <PluginMarket />
        </Tabs.Content>
        <Tabs.Content value="wsl" className="flex-1 overflow-y-auto">
          <WslStatusPage />
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
        <Tabs.Content value="archived" className="flex-1 overflow-y-auto">
          <ArchivedTab />
        </Tabs.Content>
        <Tabs.Content value="docs" className="flex-1 min-h-0 flex flex-col">
          <DocsTab />
        </Tabs.Content>
      </Tabs.Root>
    </div>
  );
}
