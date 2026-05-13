import { useState, useEffect, useCallback } from 'react'
import {
  BookOpen, FileText, RefreshCw, Save, Loader2,
  AlertTriangle, Lightbulb, Shield, X,
  ChevronRight, type LucideIcon,
} from 'lucide-react'
import { cn } from '../../lib/utils'
import type { MemoryFileInfo, MemoryLessonEntry } from '../../../shared/ipc'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SCOPE_ICONS: Record<string, LucideIcon> = {
  workspace: FileText,
  agent: BookOpen,
}

const SCOPE_LABELS: Record<string, string> = {
  workspace: '日常笔记',
  agent: 'Agent 记忆',
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} kB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatTime(ms: number): string {
  const d = new Date(ms)
  return d.toLocaleString()
}

// ---------------------------------------------------------------------------
// Save confirm dialog
// ---------------------------------------------------------------------------

function SaveConfirmDialog({
  filePath,
  onConfirm,
  onCancel,
}: {
  filePath: string
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-[var(--surface-elevated)] border border-[var(--border)] rounded-xl shadow-xl w-[400px]">
        <div className="flex items-center gap-2 px-5 py-4 border-b border-[var(--border-subtle)]">
          <AlertTriangle size={16} className="text-[var(--warning)]" />
          <h2 className="text-sm font-semibold text-[var(--text)]">覆盖文件</h2>
        </div>
        <div className="px-5 py-4 text-sm text-[var(--text-muted)]">
          此操作将覆盖 <code className="text-[var(--text)] font-mono">{filePath}</code> 的内容，此操作不可撤销。
        </div>
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-[var(--border-subtle)]">
          <button onClick={onCancel} className="px-3 py-1.5 text-sm text-[var(--text-muted)] hover:text-[var(--text)] transition-colors">
            取消
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-1.5 rounded-lg bg-[var(--warning)] hover:brightness-110 text-white text-sm font-medium transition-all"
          >
            确认覆盖
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function MemoryPage() {
  const [files, setFiles] = useState<MemoryFileInfo[]>([])
  const [lessons, setLessons] = useState<MemoryLessonEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [activeFile, setActiveFile] = useState<MemoryFileInfo | null>(null)
  const [fileContent, setFileContent] = useState<string | null>(null)
  const [editorContent, setEditorContent] = useState('')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [showSaveConfirm, setShowSaveConfirm] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [fl, ll] = await Promise.all([
        window.miqi.memory.list(),
        window.miqi.memory.lessons(),
      ])
      setFiles(fl.files)
      setLessons(ll.lessons)
    } catch {
      // runtime not running
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Load file content when switching active file
  const selectFile = useCallback(async (info: MemoryFileInfo) => {
    // Warn if dirty
    if (dirty && activeFile && info.path !== activeFile.path) {
      const ok = confirm(`文件 ${activeFile.path} 有未保存的更改，确认丢弃？`)
      if (!ok) return
    }

    setActiveFile(info)
    setDirty(false)
    setEditorContent('')
    setError(null)
    setSuccess(null)

    try {
      const result = await window.miqi.memory.get(info.path)
      setFileContent(result.content)
      setEditorContent(result.content)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '加载文件失败')
    }
  }, [dirty, activeFile])

  const handleSave = async () => {
    if (!activeFile) return
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      await window.miqi.memory.update(activeFile.path, editorContent)
      setFileContent(editorContent)
      setDirty(false)
      setSuccess(`已保存 ${activeFile.path}`)
      setTimeout(() => setSuccess(null), 2000)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const requestSave = () => {
    setShowSaveConfirm(true)
  }

  // Group files by scope
  const workspaceFiles = files.filter(f => f.scope === 'workspace')
  const agentFiles = files.filter(f => f.scope === 'agent')

  const hasUnsaved = dirty && activeFile

  return (
    <div className="flex flex-col h-full bg-[var(--background)]">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border-subtle)] bg-[var(--surface)] shrink-0">
        <div>
          <h1 className="text-base font-semibold text-[var(--text)]">记忆</h1>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            {loading ? '加载中…' : `${files.length} 个文件，${lessons.length} 条 Lesson`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {success && (
            <span className="text-xs text-[var(--success)]">{success}</span>
          )}
          {error && (
            <span className="text-xs text-[var(--danger)] flex items-center gap-1">
              <AlertTriangle size={12} /> {error}
              <button onClick={() => setError(null)} className="hover:text-[var(--text)]">
                <X size={12} />
              </button>
            </span>
          )}
          <button onClick={load} className="text-xs text-[var(--text-faint)] hover:text-[var(--text-muted)] transition-colors px-2 py-1 rounded">
            <RefreshCw size={14} />
          </button>
          <button
            onClick={requestSave}
            disabled={!hasUnsaved || saving}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
              hasUnsaved
                ? 'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)]'
                : 'bg-[var(--surface-muted)] text-[var(--text-faint)]',
              'disabled:opacity-50',
            )}
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            {hasUnsaved ? '保存 *' : '保存'}
          </button>
        </div>
      </div>

      {/* Body: left files + right editor */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar: file list */}
        <div className="w-[240px] shrink-0 border-r border-[var(--border-subtle)] bg-[var(--surface)] overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center h-20 text-xs text-[var(--text-faint)]">
              <Loader2 size={14} className="animate-spin mr-1.5" /> Loading...
            </div>
          ) : files.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-20 gap-1.5 text-xs text-[var(--text-faint)]">
              <FileText size={16} />
              <span>暂无记忆文件</span>
            </div>
          ) : (
            <div className="py-1">
              <FileGroup
                label="Agent 记忆"
                icon={BookOpen}
                files={agentFiles}
                activePath={activeFile?.path ?? null}
                onSelect={selectFile}
              />
              <FileGroup
                label="日常笔记"
                icon={FileText}
                files={workspaceFiles}
                activePath={activeFile?.path ?? null}
                onSelect={selectFile}
              />
            </div>
          )}
        </div>

        {/* Right: editor + lessons */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {!activeFile ? (
            <div className="flex flex-col items-center justify-center flex-1 gap-3 text-sm text-[var(--text-faint)]">
              <BookOpen size={28} />
              <span>从左侧选择文件查看和编辑</span>
            </div>
          ) : (
            <>
              {/* Editor header */}
              <div className="flex items-center gap-2 px-5 py-2 border-b border-[var(--border-subtle)] bg-[var(--surface-muted)] shrink-0">
                <span className="text-xs font-medium text-[var(--text)]">{activeFile.path}</span>
                <span className="text-xs text-[var(--text-faint)]">{formatSize(activeFile.size)}</span>
                <span className="text-xs text-[var(--text-faint)]">{formatTime(activeFile.updatedAtMs)}</span>
                {dirty && (
                  <span className="text-xs text-[var(--warning)] font-medium ml-auto">未保存</span>
                )}
              </div>

              {/* Editor */}
              <div className="flex-1 overflow-hidden">
                <textarea
                  value={editorContent}
                  onChange={(e) => {
                    setEditorContent(e.target.value)
                    setDirty(e.target.value !== fileContent)
                  }}
                  className="w-full h-full px-5 py-4 resize-none text-sm font-mono bg-[var(--background)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none leading-relaxed"
                  spellCheck={false}
                  placeholder="文件内容…"
                />
              </div>

              {/* Lessons section */}
              <div className="border-t border-[var(--border-subtle)] shrink-0">
                <div className="flex items-center gap-2 px-5 py-2 bg-[var(--surface-muted)] border-b border-[var(--border-subtle)]">
                  <Lightbulb size={13} className="text-[var(--warning)]" />
                  <span className="text-xs font-semibold uppercase tracking-widest text-[var(--text-faint)]">
                    自我优化 Lessons
                  </span>
                  <span className="text-xs text-[var(--text-faint)] ml-auto">
                    {lessons.length} total
                  </span>
                </div>
                <div className="max-h-[200px] overflow-y-auto">
                  {lessons.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 gap-2 text-xs text-[var(--text-faint)]">
                      <Lightbulb size={18} />
                      <span>暂无 Lesson 记录。</span>
                      <span>Agent 收到用户纠正后会自动记录 Lesson。</span>
                    </div>
                  ) : (
                    <div className="divide-y divide-[var(--border-subtle)]">
                      {lessons.map((lesson) => (
                        <LessonRow key={lesson.id} lesson={lesson} />
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Save confirm dialog */}
      {showSaveConfirm && activeFile && (
        <SaveConfirmDialog
          filePath={activeFile.path}
          onConfirm={() => {
            setShowSaveConfirm(false)
            handleSave()
          }}
          onCancel={() => setShowSaveConfirm(false)}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// File group
// ---------------------------------------------------------------------------

function FileGroup({
  label,
  icon: Icon,
  files,
  activePath,
  onSelect,
}: {
  label: string
  icon: LucideIcon
  files: MemoryFileInfo[]
  activePath: string | null
  onSelect: (f: MemoryFileInfo) => void
}) {
  if (files.length === 0) return null
  return (
    <div>
      <div className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold uppercase tracking-widest text-[var(--text-faint)]">
        <Icon size={12} />
        {label}
      </div>
      <div>
        {files.map(f => {
          const isActive = activePath === f.path
          return (
            <button
              key={f.path}
              onClick={() => onSelect(f)}
              className={cn(
                'flex items-center gap-2 w-full px-3 py-1.5 text-left text-sm transition-colors',
                isActive
                  ? 'bg-[var(--accent-soft)] text-[var(--accent)] font-medium'
                  : 'text-[var(--text-muted)] hover:bg-[var(--surface-muted)] hover:text-[var(--text)]',
              )}
            >
              <ChevronRight size={10} className={cn('shrink-0', isActive ? 'text-[var(--accent)]' : 'text-[var(--text-faint)]')} />
              <span className="truncate flex-1">{f.path}</span>
              <span className="text-xs text-[var(--text-faint)] shrink-0">{formatSize(f.size)}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Lesson row
// ---------------------------------------------------------------------------

function LessonRow({ lesson }: { lesson: MemoryLessonEntry }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="hover:bg-[var(--surface-muted)] transition-colors">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full px-5 py-2 text-left text-xs"
      >
        <div className={cn(
          'w-1.5 h-1.5 rounded-full shrink-0',
          lesson.scope === 'global' ? 'bg-[var(--accent)]' : 'bg-[var(--text-faint)]',
        )} />
        <span className="flex-1 text-[var(--text)] truncate">{lesson.trigger}</span>
        <span className={cn(
          'text-xs shrink-0',
          lesson.effectiveConfidence >= 3 ? 'text-[var(--success)]' :
          lesson.effectiveConfidence >= 1 ? 'text-[var(--warning)]' :
          'text-[var(--text-faint)]',
        )}>
          c:{lesson.effectiveConfidence}
        </span>
        <span className="text-[var(--text-faint)] shrink-0">{lesson.hits}h</span>
        {!lesson.enabled && (
          <Shield size={11} className="text-[var(--text-faint)]" />
        )}
      </button>
      {expanded && (
        <div className="px-8 pb-2 flex flex-col gap-1 text-xs text-[var(--text-muted)]">
          {lesson.badAction && (
            <div><span className="text-[var(--text-faint)]">Bad:</span> {lesson.badAction}</div>
          )}
          <div><span className="text-[var(--text-faint)]">Better:</span> {lesson.betterAction}</div>
          <div className="flex items-center gap-3 mt-1">
            <span className="text-[var(--text-faint)]">Scope: {lesson.scope}</span>
            <span className="text-[var(--text-faint)]">Source: {lesson.source}</span>
            <span className="text-[var(--text-faint)]">Confidence: {lesson.confidence}</span>
          </div>
        </div>
      )}
    </div>
  )
}
