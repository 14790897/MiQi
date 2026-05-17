import { useState, useEffect, useCallback } from 'react'
import { cn } from '../../lib/utils'
import {
  BookOpen,
  Lightbulb,
  History,
  Trash2,
  ToggleLeft,
  ToggleRight,
  Search,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Save,
  Edit3,
  Eye,
  Plus,
  Copy,
  FileText,
  type LucideIcon,
} from 'lucide-react'
import type { ExperienceEntry, MemoryFileInfo, MemoryGetResult } from '../../../shared/ipc'
import ContextMenu from '../../components/ContextMenu'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// ── Types ───────────────────────────────────────────────────────────────────
type TabId = 'facts' | 'rules' | 'history'

const TABS: { id: TabId; label: string; icon: LucideIcon }[] = [
  { id: 'facts', label: '事实', icon: BookOpen },
  { id: 'rules', label: '规则', icon: Lightbulb },
  { id: 'history', label: '历史', icon: History },
]

// ── Files helpers ───────────────────────────────────────────────────────────
function fileScope(path: string): 'agent' | 'workspace' {
  return path.includes('agent-memory') ? 'agent' : 'workspace'
}

function ScopeLabel({ scope }: { scope: 'agent' | 'workspace' }) {
  return (
    <span
      className={cn(
        'inline-flex items-center px-1.5 py-0 text-[11px] font-medium rounded',
        scope === 'agent'
          ? 'text-[var(--accent)] bg-[var(--accent)]/10'
          : 'text-[var(--muted-foreground)] bg-[var(--muted)]/20'
      )}
    >
      {scope === 'agent' ? 'Agent' : '日常'}
    </span>
  )
}

// ── Sub-components ──────────────────────────────────────────────────────────

function SaveConfirmDialog({
  path,
  onConfirm,
  onCancel,
}: {
  path: string
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[var(--surface)] rounded-lg border border-[var(--border)] p-6 max-w-md mx-4 shadow-xl">
        <h3 className="text-lg font-semibold mb-2">确认保存</h3>
        <p className="text-sm text-[var(--muted-foreground)] mb-4">
          文件 <code className="text-[var(--accent)] text-xs">{path}</code> 已经存在。
          <br />
          确定要覆盖保存吗？
        </p>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm rounded-md border border-[var(--border)] hover:bg-[var(--muted)]/30"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 text-sm rounded-md bg-[var(--accent)] text-white hover:opacity-90"
          >
            覆盖保存
          </button>
        </div>
      </div>
    </div>
  )
}

function ConfirmDialog({
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  title: string
  message: string
  confirmLabel?: string
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[var(--surface)] rounded-lg border border-[var(--border)] p-6 max-w-md mx-4 shadow-xl">
        <h3 className="text-lg font-semibold mb-2">{title}</h3>
        <p className="text-sm text-[var(--muted-foreground)] mb-4">{message}</p>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm rounded-md border border-[var(--border)] hover:bg-[var(--muted)]/30"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 text-sm rounded-md bg-red-600 text-white hover:opacity-90"
          >
            {confirmLabel || '删除'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Facts Tab ────────────────────────────────────────────────────────────────
function FactsTab() {
  const [files, setFiles] = useState<MemoryFileInfo[]>([])
  const [activeFile, setActiveFile] = useState<string | null>(null)
  const [fileContent, setFileContent] = useState('')
  const [editorContent, setEditorContent] = useState('')
  const [dirty, setDirty] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [previewMode, setPreviewMode] = useState(false)
  const [showSaveConfirm, setShowSaveConfirm] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(null)
  const [showNewFileDialog, setShowNewFileDialog] = useState(false)
  const [newFileName, setNewFileName] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [copiedAll, setCopiedAll] = useState(false)

  const loadFiles = useCallback(async () => {
    try {
      const res = await window.miqi.memory.list()
      setFiles(res.files || [])
    } catch {
      // Ignore
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadFiles() }, [loadFiles])

  const selectFile = useCallback(async (path: string) => {
    setActiveFile(path)
    setDirty(false)
    setError('')
    setSuccess('')
    try {
      const res = await window.miqi.memory.get(path)
      setFileContent(res.content)
      setEditorContent(res.content)
    } catch {
      setFileContent('')
      setEditorContent('')
    }
  }, [])

  const save = useCallback(async () => {
    if (!activeFile) return
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const res = await window.miqi.memory.update(activeFile, editorContent)
      if (res.saved) {
        setFileContent(editorContent)
        setDirty(false)
        setSuccess('已保存')
      }
    } catch (e: any) {
      setError(e?.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }, [activeFile, editorContent])

  const createFile = useCallback(async () => {
    if (!newFileName.trim()) return
    const name = newFileName.trim().endsWith('.md') ? newFileName.trim() : newFileName.trim() + '.md'
    setShowNewFileDialog(false)
    setNewFileName('')
    try {
      await window.miqi.memory.update(name, '')
      await loadFiles()
      selectFile(name)
    } catch (e: any) {
      setError(e?.message || '创建失败')
    }
  }, [newFileName, loadFiles, selectFile])

  const deleteFile = useCallback(async (path: string) => {
    try {
      await window.miqi.memory.delete(path)
      setShowDeleteConfirm(null)
      if (activeFile === path) {
        setActiveFile(null)
        setFileContent('')
        setEditorContent('')
      }
      await loadFiles()
    } catch (e: any) {
      setError(e?.message || '删除失败')
    }
  }, [activeFile, loadFiles])

  const agentFiles = files.filter(f => fileScope(f.path) === 'agent')
  const workspaceFiles = files.filter(f => fileScope(f.path) === 'workspace')

  return (
    <div className="flex h-full">
      {/* Left sidebar */}
      <div className="w-[240px] border-r border-[var(--border)] flex flex-col flex-shrink-0">
        <div className="p-2 border-b border-[var(--border)]">
          <button
            onClick={() => setShowNewFileDialog(true)}
            className="w-full flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md
                       bg-[var(--accent)]/10 hover:bg-[var(--accent)]/20 text-[var(--accent)] transition-colors"
          >
            <Plus size={14} /> 新建笔记
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {agentFiles.length > 0 && (
            <div>
              <div className="px-3 py-1.5 text-[11px] font-semibold text-[var(--muted-foreground)] uppercase tracking-wider">
                Agent 记忆
              </div>
              {agentFiles.map(f => (
                <ContextMenu
                  key={f.path}
                  items={[{ label: '删除', danger: true, onSelect: () => setShowDeleteConfirm(f.path) }]}
                >
                  <div
                    onClick={() => selectFile(f.path)}
                    className={cn(
                      'px-3 py-1.5 text-sm cursor-pointer truncate hover:bg-[var(--muted)]/20 transition-colors',
                      activeFile === f.path && 'bg-[var(--accent)]/10 text-[var(--accent)]'
                    )}
                  >
                    {f.path.split('/').pop()?.replace('.md', '') || f.path}
                  </div>
                </ContextMenu>
              ))}
            </div>
          )}
          {workspaceFiles.length > 0 && (
            <div>
              <div className="px-3 py-1.5 text-[11px] font-semibold text-[var(--muted-foreground)] uppercase tracking-wider">
                日常笔记
              </div>
              {workspaceFiles.map(f => (
                <ContextMenu
                  key={f.path}
                  items={[{ label: '删除', danger: true, onSelect: () => setShowDeleteConfirm(f.path) }]}
                >
                  <div
                    onClick={() => selectFile(f.path)}
                    className={cn(
                      'px-3 py-1.5 text-sm cursor-pointer truncate hover:bg-[var(--muted)]/20 transition-colors',
                      activeFile === f.path && 'bg-[var(--accent)]/10 text-[var(--accent)]'
                    )}
                  >
                    {f.path.split('/').pop()?.replace('.md', '') || f.path}
                  </div>
                </ContextMenu>
              ))}
            </div>
          )}
          {files.length === 0 && !loading && (
            <div className="p-4 text-xs text-[var(--muted-foreground)] text-center">暂无记忆文件</div>
          )}
        </div>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex flex-col min-w-0">
        {activeFile ? (
          <>
            <div className="flex items-center gap-2 px-4 py-2 border-b border-[var(--border)]">
              <FileText size={14} className="text-[var(--muted-foreground)]" />
              <span className="text-xs text-[var(--muted-foreground)] truncate flex-1">{activeFile}</span>
              <button
                onClick={() => { navigator.clipboard.writeText(editorContent); setCopiedAll(true); setTimeout(() => setCopiedAll(false), 2000) }}
                className="p-1 rounded hover:bg-[var(--muted)]/20 text-[var(--muted-foreground)]"
                title="拷贝全部"
              >
                {copiedAll ? <CheckCircle size={14} className="text-green-400" /> : <Copy size={14} />}
              </button>
              <button
                onClick={() => setPreviewMode(!previewMode)}
                className={cn('p-1 rounded hover:bg-[var(--muted)]/20', previewMode ? 'text-[var(--accent)]' : 'text-[var(--muted-foreground)]')}
              >
                {previewMode ? <Edit3 size={14} /> : <Eye size={14} />}
              </button>
              <button
                onClick={save}
                disabled={!dirty || saving}
                className={cn(
                  'flex items-center gap-1 px-3 py-1 text-xs rounded-md transition-colors',
                  dirty
                    ? 'bg-[var(--accent)] text-white hover:opacity-90'
                    : 'bg-[var(--muted)]/20 text-[var(--muted-foreground)]'
                )}
              >
                <Save size={12} /> {saving ? '保存中...' : '保存'}
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {previewMode ? (
                <div className="prose prose-sm prose-invert max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{editorContent}</ReactMarkdown>
                </div>
              ) : (
                <textarea
                  value={editorContent}
                  onChange={e => { setEditorContent(e.target.value); setDirty(e.target.value !== fileContent) }}
                  className="w-full h-full min-h-[300px] bg-transparent text-sm font-mono resize-none
                             outline-none text-[var(--foreground)] placeholder:text-[var(--muted-foreground)]"
                  placeholder="输入内容..."
                  spellCheck={false}
                />
              )}
            </div>
            {error && <div className="px-4 py-1 text-xs text-red-400">{error}</div>}
            {success && <div className="px-4 py-1 text-xs text-green-400">{success}</div>}
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-sm text-[var(--muted-foreground)]">
            选择一个文件查看或编辑
          </div>
        )}
      </div>

      {/* Dialogs */}
      {showSaveConfirm && (
        <SaveConfirmDialog
          path={activeFile!}
          onConfirm={() => { setShowSaveConfirm(false); save() }}
          onCancel={() => setShowSaveConfirm(false)}
        />
      )}
      {showDeleteConfirm && (
        <ConfirmDialog
          title="删除文件"
          message={`确定要删除 "${showDeleteConfirm}" 吗？此操作不可撤销。`}
          onConfirm={() => deleteFile(showDeleteConfirm)}
          onCancel={() => setShowDeleteConfirm(null)}
        />
      )}
      {showNewFileDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[var(--surface)] rounded-lg border border-[var(--border)] p-6 max-w-md mx-4 shadow-xl">
            <h3 className="text-lg font-semibold mb-4">新建笔记</h3>
            <input
              autoFocus
              value={newFileName}
              onChange={e => setNewFileName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && createFile()}
              placeholder="文件名（如 notes.md）"
              className="w-full px-3 py-2 text-sm bg-[var(--muted)]/20 rounded-md border border-[var(--border)]
                         outline-none focus:border-[var(--accent)] mb-4"
            />
            <div className="flex gap-3 justify-end">
              <button onClick={() => { setShowNewFileDialog(false); setNewFileName('') }}
                className="px-4 py-2 text-sm rounded-md border border-[var(--border)] hover:bg-[var(--muted)]/30">
                取消
              </button>
              <button onClick={createFile}
                className="px-4 py-2 text-sm rounded-md bg-[var(--accent)] text-white hover:opacity-90">
                创建
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Rules Tab ────────────────────────────────────────────────────────────────
function RulesTab() {
  const [entries, setEntries] = useState<ExperienceEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [filterScope, setFilterScope] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await window.miqi.experience.list({ type: 'rule', limit: 200 })
      setEntries(res.entries || [])
    } catch {
      // Ignore
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleDelete = useCallback(async (id: string) => {
    await window.miqi.experience.delete('rule', id)
    await load()
  }, [load])

  const handleToggle = useCallback(async (id: string, enabled: boolean) => {
    await window.miqi.experience.toggle('rule', id, enabled)
    await load()
  }, [load])

  const filtered = entries.filter(e => {
    if (filterScope !== 'all' && e.scope !== filterScope) return false
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      return e.title.toLowerCase().includes(q) || e.content.toLowerCase().includes(q)
    }
    return true
  })

  return (
    <div className="flex flex-col h-full">
      {/* Filters */}
      <div className="flex items-center gap-2 p-3 border-b border-[var(--border)]">
        <div className="flex gap-0.5 bg-[var(--muted)]/10 rounded-md p-0.5">
          {['all', 'global', 'session'].map(s => (
            <button
              key={s}
              onClick={() => setFilterScope(s)}
              className={cn(
                'px-2.5 py-1 text-xs rounded-sm transition-colors',
                filterScope === s ? 'bg-[var(--surface)] text-[var(--accent)] shadow-sm' : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]'
              )}
            >
              {s === 'all' ? '全部' : s === 'global' ? '全局' : '会话'}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <div className="relative">
          <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]" />
          <input
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="搜索规则..."
            className="w-[160px] pl-7 pr-3 py-1 text-xs rounded-md bg-[var(--muted)]/10 border border-[var(--border)]
                       outline-none focus:border-[var(--accent)]"
          />
        </div>
        <button
          onClick={load}
          className="p-1.5 rounded hover:bg-[var(--muted)]/20 text-[var(--muted-foreground)]"
          title="刷新"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Rule list */}
      <div className="flex-1 overflow-y-auto">
        {loading && entries.length === 0 && (
          <div className="p-8 text-center text-sm text-[var(--muted-foreground)]">加载中...</div>
        )}
        {!loading && filtered.length === 0 && (
          <div className="p-8 text-center text-sm text-[var(--muted-foreground)]">暂无规则</div>
        )}
        {filtered.map(entry => (
          <div key={entry.id} className="border-b border-[var(--border)] last:border-0">
            <div className="flex items-center gap-2 px-4 py-2.5 hover:bg-[var(--muted)]/5 cursor-pointer"
                 onClick={() => setExpandedId(expandedId === entry.id ? null : entry.id)}>
              <div
                className={cn(
                  'w-2 h-2 rounded-full flex-shrink-0',
                  entry.enabled ? 'bg-green-400' : 'bg-[var(--muted-foreground)]'
                )}
              />
              <span className="text-xs px-1.5 py-0 rounded bg-[var(--muted)]/10 text-[var(--muted-foreground)] flex-shrink-0">
                {entry.metadata?.state as string || 'active'}
              </span>
              <span className="text-sm truncate flex-1">{entry.title}</span>
              {/* Confidence bar */}
              <div className="flex items-center gap-1 flex-shrink-0">
                <div className="w-12 h-1 bg-[var(--muted)]/20 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${Math.min(100, (entry.confidence / 10) * 100)}%`,
                      backgroundColor:
                        entry.confidence >= 7 ? 'var(--accent)' :
                        entry.confidence >= 4 ? '#f59e0b' : 'var(--muted-foreground)',
                    }}
                  />
                </div>
                <span className="text-[11px] text-[var(--muted-foreground)] w-4 text-right">{entry.confidence}</span>
              </div>
              <button
                onClick={e => { e.stopPropagation(); handleToggle(entry.id, !entry.enabled) }}
                className="p-1 rounded hover:bg-[var(--muted)]/20"
                title={entry.enabled ? '禁用' : '启用'}
              >
                {entry.enabled ? (
                  <ToggleRight size={16} className="text-green-400" />
                ) : (
                  <ToggleLeft size={16} className="text-[var(--muted-foreground)]" />
                )}
              </button>
              <button
                onClick={e => { e.stopPropagation(); handleDelete(entry.id) }}
                className="p-1 rounded hover:bg-red-500/10 text-[var(--muted-foreground)] hover:text-red-400"
                title="删除"
              >
                <Trash2 size={14} />
              </button>
              {expandedId === entry.id ? <ChevronDown size={14} className="text-[var(--muted-foreground)]" /> : <ChevronRight size={14} className="text-[var(--muted-foreground)]" />}
            </div>
            {expandedId === entry.id && (
              <div className="px-4 pb-3 pl-10 space-y-1.5 text-xs">
                <div>
                  <span className="text-[var(--muted-foreground)]">错误行为: </span>
                  <span className="text-red-300">{entry.metadata?.bad_action as string}</span>
                </div>
                <div>
                  <span className="text-[var(--muted-foreground)]">正确行为: </span>
                  <span className="text-green-300">{entry.metadata?.better_action as string}</span>
                </div>
                <div className="flex gap-4 text-[var(--muted-foreground)]">
                  <span>来源: {entry.source}</span>
                  <span>范围: {entry.scope}</span>
                  <span>命中: {entry.metadata?.hits as number || 0}</span>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── History Tab ──────────────────────────────────────────────────────────────
function HistoryTab() {
  const [entries, setEntries] = useState<ExperienceEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [page, setPage] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await window.miqi.experience.list({ type: 'trace', limit: 100 })
      setEntries(res.entries || [])
    } catch {
      // Ignore
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = entries.filter(e => {
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      return e.title.toLowerCase().includes(q) || e.content.toLowerCase().includes(q)
    }
    return true
  })

  const pageSize = 20
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const pagedEntries = filtered.slice(page * pageSize, (page + 1) * pageSize)

  const outcomeIcon = (outcome: string) => {
    switch (outcome) {
      case 'success': return <CheckCircle size={14} className="text-green-400" />
      case 'failure': return <XCircle size={14} className="text-red-400" />
      default: return <AlertTriangle size={14} className="text-yellow-400" />
    }
  }

  const formatRelativeTime = (ts: number) => {
    const diff = Date.now() - ts * 1000
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return '刚刚'
    if (mins < 60) return `${mins} 分钟前`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours} 小时前`
    const days = Math.floor(hours / 24)
    return `${days} 天前`
  }

  return (
    <div className="flex flex-col h-full">
      {/* Search bar */}
      <div className="flex items-center gap-2 p-3 border-b border-[var(--border)]">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]" />
          <input
            value={searchQuery}
            onChange={e => { setSearchQuery(e.target.value); setPage(0) }}
            placeholder="搜索历史..."
            className="w-full pl-7 pr-3 py-1.5 text-xs rounded-md bg-[var(--muted)]/10 border border-[var(--border)]
                       outline-none focus:border-[var(--accent)]"
          />
        </div>
        <button
          onClick={load}
          className="p-1.5 rounded hover:bg-[var(--muted)]/20 text-[var(--muted-foreground)]"
          title="刷新"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Trace list */}
      <div className="flex-1 overflow-y-auto">
        {loading && entries.length === 0 && (
          <div className="p-8 text-center text-sm text-[var(--muted-foreground)]">加载中...</div>
        )}
        {!loading && pagedEntries.length === 0 && (
          <div className="p-8 text-center text-sm text-[var(--muted-foreground)]">暂无历史记录</div>
        )}
        {pagedEntries.map(entry => (
          <div key={entry.id} className="border-b border-[var(--border)] last:border-0">
            <div
              className="flex items-center gap-3 px-4 py-2.5 hover:bg-[var(--muted)]/5 cursor-pointer"
              onClick={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
            >
              {outcomeIcon(entry.metadata?.outcome as string || 'partial')}
              <div className="flex-1 min-w-0">
                <div className="text-sm truncate">{entry.title}</div>
                <div className="text-[11px] text-[var(--muted-foreground)] truncate">{entry.content}</div>
              </div>
              <span className="text-[11px] text-[var(--muted-foreground)] flex-shrink-0">
                {formatRelativeTime(entry.created_at)}
              </span>
              <span className="text-[11px] px-1.5 py-0 rounded bg-[var(--muted)]/10 text-[var(--muted-foreground)] flex-shrink-0">
                {entry.metadata?.tool_count !== undefined ? `${entry.metadata.tool_count} tools` : ''}
              </span>
              {expandedId === entry.id ? <ChevronDown size={14} className="text-[var(--muted-foreground)]" /> : <ChevronRight size={14} className="text-[var(--muted-foreground)]" />}
            </div>
            {expandedId === entry.id && (
              <div className="px-4 pb-3 pl-11 space-y-2">
                {entry.metadata?.outcome_notes && (
                  <div className="text-xs text-[var(--muted-foreground)]">{entry.metadata.outcome_notes as string}</div>
                )}
                {entry.metadata?.tool_calls && Array.isArray(entry.metadata.tool_calls) && (entry.metadata.tool_calls as Array<{tool_name: string; args_summary: string; result_summary: string}>).map((step: any, i: number) => (
                  <div key={i} className="bg-[var(--muted)]/5 rounded-md p-2 text-xs">
                    <div className="font-medium text-[var(--accent)]">{step.tool_name}</div>
                    <div className="text-[var(--muted-foreground)] mt-0.5">
                      <span className="text-[11px] text-[var(--muted-foreground)]">args: </span>
                      {step.args_summary}
                    </div>
                    <div className="text-[var(--muted-foreground)] mt-0.5">
                      <span className="text-[11px] text-[var(--muted-foreground)]">result: </span>
                      {step.result_summary}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-1 p-2 border-t border-[var(--border)]">
          {Array.from({ length: totalPages }, (_, i) => (
            <button
              key={i}
              onClick={() => setPage(i)}
              className={cn(
                'w-7 h-7 text-xs rounded transition-colors',
                i === page
                  ? 'bg-[var(--accent)] text-white'
                  : 'hover:bg-[var(--muted)]/20 text-[var(--muted-foreground)]'
              )}
            >
              {i + 1}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── ExperiencePage ───────────────────────────────────────────────────────────
export function ExperiencePage() {
  const [activeTab, setActiveTab] = useState<TabId>('facts')

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-4 px-5 py-3 border-b border-[var(--border)] flex-shrink-0">
        <h2 className="text-lg font-semibold">经验</h2>
        {/* Tab bar */}
        <div className="flex gap-0.5 bg-[var(--muted)]/10 rounded-lg p-0.5">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md transition-colors',
                activeTab === tab.id
                  ? 'bg-[var(--surface)] text-[var(--accent)] shadow-sm'
                  : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]'
              )}
            >
              <tab.icon size={15} />
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0">
        {activeTab === 'facts' && <FactsTab />}
        {activeTab === 'rules' && <RulesTab />}
        {activeTab === 'history' && <HistoryTab />}
      </div>
    </div>
  )
}
