import { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Search,
  Wrench,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Copy,
  Check,
  FolderOpen,
  Plus,
  Upload,
  Trash2,
  Lock,
  X,
  Package,
} from 'lucide-react'
import type { SkillSummary, SkillDetail } from '../../../shared/ipc'
import { SkillHubPage } from './SkillHubPage'

function CreateSkillModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: (name: string) => void
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  if (!open) return null

  const handleCreate = async () => {
    setError('')
    if (!/^[a-z][a-z0-9-]*$/.test(name)) {
      setError('名称必须以字母开头，仅可使用小写字母、数字和连字符')
      return
    }
    setSaving(true)
    try {
      const res = await window.miqi.skills.create(name, description)
      if (res.ok) {
        onCreated(name)
        onClose()
      } else {
        setError(res.error ?? '创建失败')
      }
    } catch (e: any) {
      setError(e?.message ?? '创建失败')
    }
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div
        className="rounded-xl shadow-2xl w-full max-w-md mx-4"
        style={{ background: 'var(--surface)' }}
      >
        <div
          className="flex items-center justify-between px-5 py-4 border-b"
          style={{ borderColor: 'var(--border)' }}
        >
          <h2 className="text-base font-semibold" style={{ color: 'var(--text)' }}>
            新建技能
          </h2>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-[var(--surface-muted)]"
            style={{ color: 'var(--text-muted)' }}
          >
            <X size={16} />
          </button>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>
              技能名称
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="my-skill"
              className="w-full px-3 py-2 rounded-lg text-sm border"
              style={{
                background: 'var(--surface-muted)',
                color: 'var(--text)',
                borderColor: 'var(--border)',
              }}
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>
              描述 (可选)
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="简要描述此技能"
              className="w-full px-3 py-2 rounded-lg text-sm border"
              style={{
                background: 'var(--surface-muted)',
                color: 'var(--text)',
                borderColor: 'var(--border)',
              }}
            />
          </div>
          {error && (
            <div className="text-xs px-3 py-2 rounded" style={{ background: 'var(--danger-bg)', color: 'var(--danger)' }}>
              {error}
            </div>
          )}
        </div>
        <div className="flex justify-end gap-2 px-5 py-4 border-t" style={{ borderColor: 'var(--border)' }}>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-xs font-medium transition-colors hover:bg-[var(--surface-muted)]"
            style={{ color: 'var(--text-muted)' }}
          >
            取消
          </button>
          <button
            onClick={handleCreate}
            disabled={saving}
            className="px-4 py-2 rounded-lg text-xs font-medium text-white transition-colors"
            style={{ background: 'var(--accent)' }}
          >
            {saving ? '创建中...' : '创建'}
          </button>
        </div>
      </div>
    </div>
  )
}

export function SkillsPage() {
  const [tab, setTab] = useState<'local' | 'skillhub'>('local')
  const [skills, setSkills] = useState<SkillSummary[]>([])
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [detail, setDetail] = useState<SkillDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [copied, setCopied] = useState(false)
  const [openingFolder, setOpeningFolder] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const loadSkills = () => {
    window.miqi.skills
      .list()
      .then((res) => setSkills(res.skills))
      .catch(() => {})
  }

  useEffect(() => {
    loadSkills()
    setLoading(false)
  }, [])

  useEffect(() => {
    if (!selectedName) {
      setDetail(null)
      return
    }
    setDetailLoading(true)
    window.miqi.skills
      .get(selectedName)
      .then((d) => {
        setDetail(d)
        setDetailLoading(false)
      })
      .catch(() => setDetailLoading(false))
  }, [selectedName])

  const filtered = skills.filter((s) => {
    if (!query.trim()) return true
    const q = query.toLowerCase()
    return (
      s.name.toLowerCase().includes(q) ||
      s.description.toLowerCase().includes(q)
    )
  })

  const builtin = filtered.filter((s) => s.source === 'builtin')
  const workspace = filtered.filter((s) => s.source === 'workspace')

  const handleCopyContent = () => {
    if (!detail) return
    navigator.clipboard.writeText(detail.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleOpenFolder = async () => {
    if (!selectedName) return
    setOpeningFolder(true)
    try {
      await window.miqi.skills.openFolder(selectedName)
    } catch {
      // ignore
    }
    setOpeningFolder(false)
  }

  const handleCreated = (name: string) => {
    loadSkills()
    setSelectedName(name)
  }

  const handleDelete = async (name: string) => {
    if (!window.confirm(`确认删除技能 "${name}"？`)) return
    try {
      await window.miqi.skills.delete(name)
      if (selectedName === name) {
        setSelectedName(null)
        setDetail(null)
      }
      loadSkills()
    } catch {
      // ignore
    }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const content = await file.text()
      const name = file.name.replace(/\.(yml|yaml|md)$/i, '')
      const res = await window.miqi.skills.upload(name, content)
      if (res.ok) {
        loadSkills()
        setSelectedName(name)
      }
    } catch {
      // ignore
    }
    setUploading(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  if (loading && tab === 'local') {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-sm text-[var(--text-muted)]">正在加载技能…</div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar */}
      <div className="shrink-0 flex items-center gap-0 border-b border-[var(--border-subtle)] bg-[var(--surface)]">
        <button
          onClick={() => setTab('local')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${
            tab === 'local'
              ? 'border-[var(--accent)] text-[var(--accent)]'
              : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text)]'
          }`}
        >
          <Wrench size={14} />
          本地技能
        </button>
        <button
          onClick={() => setTab('skillhub')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${
            tab === 'skillhub'
              ? 'border-[var(--accent)] text-[var(--accent)]'
              : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text)]'
          }`}
        >
          <Package size={14} />
          SkillHub
        </button>
      </div>

      {/* SkillHub view */}
      {tab === 'skillhub' && (
        <SkillHubPage
          installedSkills={skills}
          onSkillInstalled={loadSkills}
        />
      )}

      {/* Local skills view */}
      {tab === 'local' && (
        <div className="flex flex-1 overflow-hidden">
          {/* Left sidebar — skill list */}
          <div className="w-[280px] shrink-0 border-r border-[var(--border-subtle)] bg-[var(--surface)] flex flex-col">
            <div className="px-4 pt-4 pb-2 space-y-2">
              <div className="relative">
                <Search
                  size={14}
                  className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-faint)]"
                />
                <input
                  type="text"
                  placeholder="搜索技能…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="w-full pl-8 pr-3 py-1.5 text-xs rounded-md border border-[var(--border)] bg-[var(--background)] text-[var(--text)] placeholder:text-[var(--text-faint)] focus:outline-none focus:border-[var(--accent)]"
                />
              </div>
              <div className="flex gap-1.5">
                <button
                  onClick={() => setModalOpen(true)}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-md text-[10px] font-medium transition-colors text-white"
                  style={{ background: 'var(--accent)' }}
                >
                  <Plus size={11} />
                  新建技能
                </button>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-md text-[10px] font-medium transition-colors"
                  style={{
                    background: 'var(--surface-muted)',
                    color: 'var(--text-muted)',
                  }}
                >
                  <Upload size={11} />
                  {uploading ? '上传中...' : '上传 .yml'}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".yml,.yaml,.md"
                  className="hidden"
                  onChange={handleFileUpload}
                />
              </div>
            </div>

            <div className="flex-1 overflow-auto px-2 pb-2">
              {filtered.length === 0 && (
                <div className="text-xs text-[var(--text-muted)] text-center mt-8">
                  {query.trim() ? '无匹配技能' : '未找到技能'}
                </div>
              )}

              {builtin.length > 0 && (
                <SkillGroup
                  label="内置"
                  skills={builtin}
                  selectedName={selectedName}
                  onSelect={setSelectedName}
                />
              )}
              {workspace.length > 0 && (
                <SkillGroup
                  label="工作区"
                  skills={workspace}
                  selectedName={selectedName}
                  onSelect={setSelectedName}
                />
              )}
            </div>
          </div>

          {/* Right panel — skill detail */}
          <div className="flex-1 flex flex-col overflow-hidden bg-[var(--background)]">
            {detailLoading ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-sm text-[var(--text-muted)]">
                  正在加载技能详情…
                </div>
              </div>
            ) : detail ? (
              <div className="flex flex-col h-full overflow-auto">
                {/* Header */}
                <div className="shrink-0 px-6 py-4 border-b border-[var(--border-subtle)]">
                  <div className="flex items-center gap-2.5 mb-1">
                    <Wrench size={20} className="text-[var(--accent)]" />
                    <h2 className="text-lg font-semibold text-[var(--text)]">
                      {detail.name}
                    </h2>
                    <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-[var(--surface-muted)] text-[var(--text-muted)] uppercase">
                      {detail.source}
                    </span>
                    {detail.available ? (
                      <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-medium bg-[var(--accent-soft)] text-[var(--accent)]">
                        <CheckCircle2 size={10} />
                        可用
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-medium bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">
                        <AlertTriangle size={10} />
                        不可用
                      </span>
                    )}
                    {/* Action buttons */}
                    <div className="ml-auto flex items-center gap-1">
                      {detail.source === 'builtin' ? (
                        <span
                          className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-medium"
                          style={{ background: 'var(--surface-muted)', color: 'var(--text-muted)' }}
                        >
                          <Lock size={10} />
                          内置
                        </span>
                      ) : (
                        <button
                          onClick={() => handleDelete(detail.name)}
                          className="flex items-center gap-1 px-2 py-1 rounded text-xs text-[var(--danger)] hover:bg-[var(--danger-bg)] transition-colors"
                          title="删除技能"
                        >
                          <Trash2 size={12} />
                          <span>删除</span>
                        </button>
                      )}
                      <button
                        onClick={handleCopyContent}
                        className="flex items-center gap-1 px-2 py-1 rounded text-xs text-[var(--text-muted)] hover:bg-[var(--surface-muted)] hover:text-[var(--text)] transition-colors"
                        title="复制 SKILL.md 内容"
                      >
                        {copied ? <Check size={12} /> : <Copy size={12} />}
                        <span>{copied ? '已复制' : '复制内容'}</span>
                      </button>
                      <button
                        onClick={handleOpenFolder}
                        disabled={openingFolder}
                        className="flex items-center gap-1 px-2 py-1 rounded text-xs text-[var(--text-muted)] hover:bg-[var(--surface-muted)] hover:text-[var(--text)] transition-colors"
                        title="在文件管理器中打开"
                      >
                        <FolderOpen size={12} />
                        <span>{openingFolder ? '打开中…' : '打开目录'}</span>
                      </button>
                    </div>
                  </div>
                  {detail.description && (
                    <p className="text-sm text-[var(--text-muted)] mb-2">
                      {detail.description}
                    </p>
                  )}
                  {!detail.available && detail.missingRequirements && (
                    <div className="text-xs text-[var(--danger)] mt-1">
                      缺少：{detail.missingRequirements}
                    </div>
                  )}
                  <div className="text-[11px] text-[var(--text-faint)] mt-1 font-mono">
                    {detail.path}
                  </div>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-auto p-6">
                  <div className="text-sm text-[var(--text)] leading-relaxed bg-[var(--surface)] border border-[var(--border-subtle)] rounded-lg p-4 prose prose-sm max-w-none">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {detail.content}
                    </ReactMarkdown>
                  </div>
                </div>

                {/* Metadata footer */}
                {detail.metadata && Object.keys(detail.metadata).length > 0 && (
                  <div className="shrink-0 px-6 py-3 border-t border-[var(--border-subtle)]">
                    <h3 className="text-xs font-semibold text-[var(--text-muted)] mb-2 uppercase tracking-wider">
                      元数据
                    </h3>
                    <div className="grid grid-cols-2 gap-2">
                      {Object.entries(detail.metadata).map(([key, value]) => (
                        <div key={key} className="text-xs">
                          <span className="text-[var(--text-faint)]">{key}:</span>{' '}
                          <span className="text-[var(--text)] font-mono">
                            {typeof value === 'object'
                              ? JSON.stringify(value)
                              : String(value)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full gap-3 text-[var(--text-muted)]">
                <Wrench size={32} strokeWidth={1.5} />
                <div className="text-sm">从左侧选择技能查看详情</div>
              </div>
            )}
          </div>

          <CreateSkillModal
            open={modalOpen}
            onClose={() => setModalOpen(false)}
            onCreated={handleCreated}
          />
        </div>
      )}
    </div>
  )
}

function SkillGroup({
  label,
  skills,
  selectedName,
  onSelect,
}: {
  label: string
  skills: SkillSummary[]
  selectedName: string | null
  onSelect: (name: string) => void
}) {
  return (
    <div className="mb-3">
      <div className="text-[10px] font-semibold text-[var(--text-faint)] uppercase tracking-wider px-2 mb-1">
        {label}
      </div>
      {skills.map((s) => (
        <button
          key={s.name}
          onClick={() => onSelect(s.name)}
          className={`w-full text-left px-2.5 py-2 rounded-lg text-sm transition-colors mb-0.5 ${
            selectedName === s.name
              ? 'bg-[var(--accent-soft)] text-[var(--accent)] font-medium'
              : 'text-[var(--text)] hover:bg-[var(--surface-muted)]'
          }`}
        >
          <div className="flex items-center gap-2">
            <span className="truncate flex-1">{s.name}</span>
            {!s.available && (
              <XCircle size={12} className="text-[var(--danger)] shrink-0" />
            )}
          </div>
          {s.description && (
            <div className="text-[11px] text-[var(--text-muted)] truncate mt-0.5">
              {s.description}
            </div>
          )}
        </button>
      ))}
    </div>
  )
}
