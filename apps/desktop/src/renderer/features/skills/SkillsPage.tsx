import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Search, Wrench, CheckCircle2, XCircle, AlertTriangle, Copy, Check, FolderOpen } from 'lucide-react'
import type { SkillSummary, SkillDetail } from '../../../shared/ipc'

export function SkillsPage() {
  const [skills, setSkills] = useState<SkillSummary[]>([])
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [detail, setDetail] = useState<SkillDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [copied, setCopied] = useState(false)
  const [openingFolder, setOpeningFolder] = useState(false)

  useEffect(() => {
    window.miqi.skills.list().then((res) => {
      setSkills(res.skills)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selectedName) {
      setDetail(null)
      return
    }
    setDetailLoading(true)
    window.miqi.skills.get(selectedName).then((d) => {
      setDetail(d)
      setDetailLoading(false)
    }).catch(() => setDetailLoading(false))
  }, [selectedName])

  const filtered = skills.filter((s) => {
    if (!query.trim()) return true
    const q = query.toLowerCase()
    return s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q)
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-sm text-[var(--text-muted)]">正在加载技能…</div>
      </div>
    )
  }

  return (
    <div className="flex h-full">
      {/* Left sidebar — skill list */}
      <div className="w-[280px] shrink-0 border-r border-[var(--border-subtle)] bg-[var(--surface)] flex flex-col">
        <div className="px-4 pt-4 pb-2">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-faint)]" />
            <input
              type="text"
              placeholder="搜索技能…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs rounded-md border border-[var(--border)] bg-[var(--background)] text-[var(--text)] placeholder:text-[var(--text-faint)] focus:outline-none focus:border-[var(--accent)]"
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
            <div className="text-sm text-[var(--text-muted)]">正在加载技能详情…</div>
          </div>
        ) : detail ? (
          <div className="flex flex-col h-full overflow-auto">
            {/* Header */}
            <div className="shrink-0 px-6 py-4 border-b border-[var(--border-subtle)]">
              <div className="flex items-center gap-2.5 mb-1">
                <Wrench size={20} className="text-[var(--accent)]" />
                <h2 className="text-lg font-semibold text-[var(--text)]">{detail.name}</h2>
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
                <p className="text-sm text-[var(--text-muted)] mb-2">{detail.description}</p>
              )}
              {!detail.available && detail.missingRequirements && (
                <div className="text-xs text-[var(--danger)] mt-1">
                  缺少：{detail.missingRequirements}
                </div>
              )}
              <div className="text-[11px] text-[var(--text-faint)] mt-1 font-mono">{detail.path}</div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto p-6">
              <div className="text-sm text-[var(--text)] leading-relaxed bg-[var(--surface)] border border-[var(--border-subtle)] rounded-lg p-4 prose prose-sm max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{detail.content}</ReactMarkdown>
              </div>
            </div>

            {/* Metadata footer */}
            {detail.metadata && Object.keys(detail.metadata).length > 0 && (
              <div className="shrink-0 px-6 py-3 border-t border-[var(--border-subtle)]">
                <h3 className="text-xs font-semibold text-[var(--text-muted)] mb-2 uppercase tracking-wider">元数据</h3>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(detail.metadata).map(([key, value]) => (
                    <div key={key} className="text-xs">
                      <span className="text-[var(--text-faint)]">{key}:</span>{' '}
                      <span className="text-[var(--text)] font-mono">
                        {typeof value === 'object' ? JSON.stringify(value) : String(value)}
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
            <div className="text-[11px] text-[var(--text-muted)] truncate mt-0.5">{s.description}</div>
          )}
        </button>
      ))}
    </div>
  )
}
