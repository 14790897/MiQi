import { useState, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  FolderOpen,
  FileText,
  Folder,
  ChevronRight,
  ChevronDown,
  Save,
  AlertCircle,
} from 'lucide-react'
import type { FileNode } from '../../../shared/ipc'

export function WorkspacePage() {
  const [tree, setTree] = useState<FileNode | null>(null)
  const [loading, setLoading] = useState(true)
  const [currentPath, setCurrentPath] = useState<string | null>(null)
  const [content, setContent] = useState('')
  const [savedContent, setSavedContent] = useState('')
  const [fileLoading, setFileLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pendingPath, setPendingPath] = useState<string | null>(null)
  const [showConfirm, setShowConfirm] = useState(false)
  const [previewMode, setPreviewMode] = useState(false)

  const isUnsaved = content !== savedContent

  useEffect(() => {
    window.miqi.files.tree().then((res) => {
      setTree(res.root)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const openFile = useCallback((path: string) => {
    if (isUnsaved && path !== currentPath) {
      setPendingPath(path)
      setShowConfirm(true)
      return
    }
    loadFile(path)
  }, [isUnsaved, currentPath])

  const loadFile = useCallback((path: string) => {
    setFileLoading(true)
    setError(null)
    setCurrentPath(path)
    window.miqi.files.read(path).then((res) => {
      setContent(res.content)
      setSavedContent(res.content)
      setFileLoading(false)
    }).catch((err) => {
      setError(String(err?.message ?? err))
      setContent('')
      setSavedContent('')
      setFileLoading(false)
    })
  }, [])

  const confirmSwitch = useCallback((ok: boolean) => {
    setShowConfirm(false)
    if (ok && pendingPath) {
      loadFile(pendingPath)
    }
    setPendingPath(null)
  }, [pendingPath, loadFile])

  const handleSave = useCallback(() => {
    if (!currentPath) return
    setSaving(true)
    setError(null)
    window.miqi.files.write(currentPath, content).then(() => {
      setSavedContent(content)
      setSaving(false)
    }).catch((err) => {
      setError(String(err?.message ?? err))
      setSaving(false)
    })
  }, [currentPath, content])

  // Keyboard shortcut: Ctrl+S to save
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault()
        if (isUnsaved && currentPath) handleSave()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isUnsaved, currentPath, handleSave])

  const isMdFile = currentPath?.endsWith('.md')

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-sm text-[var(--text-muted)]">正在加载工作区…</div>
      </div>
    )
  }

  return (
    <div className="flex h-full">
      {/* Left sidebar — file tree */}
      <div className="w-[260px] shrink-0 border-r border-[var(--border-subtle)] bg-[var(--surface)] flex flex-col">
        <div className="px-3 py-3 border-b border-[var(--border-subtle)]">
          <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
            工作区文件
          </div>
        </div>
        <div className="flex-1 overflow-auto px-1.5 py-1.5">
          {tree ? (
            <FileTree node={tree} onSelect={openFile} selectedPath={currentPath} />
          ) : (
            <div className="text-xs text-[var(--text-muted)] text-center mt-8">
              未找到文件
            </div>
          )}
        </div>
      </div>

      {/* Right panel — editor */}
      <div className="flex-1 flex flex-col overflow-hidden bg-[var(--background)]">
        {currentPath ? (
          <>
            {/* Toolbar */}
            <div className="shrink-0 flex items-center justify-between px-4 py-2 border-b border-[var(--border-subtle)] bg-[var(--surface)]">
              <div className="flex items-center gap-2 min-w-0">
                <FileText size={14} className="text-[var(--text-muted)] shrink-0" />
                <span className="text-xs font-mono text-[var(--text)] truncate">{currentPath}</span>
                {isUnsaved && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 shrink-0">
                    未保存
                  </span>
                )}
              </div>
              <button
                onClick={handleSave}
                disabled={!isUnsaved || saving}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  isUnsaved
                    ? 'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)]'
                    : 'bg-[var(--surface-muted)] text-[var(--text-muted)] cursor-not-allowed'
                }`}
              >
                <Save size={12} />
                {saving ? '保存中…' : '保存'}
              </button>
              {isMdFile && (
                <div className="flex items-center gap-1 rounded-md border border-[var(--border-subtle)] overflow-hidden">
                  <button
                    onClick={() => setPreviewMode(false)}
                    className={`px-2 py-0.5 text-xs ${!previewMode ? 'bg-[var(--accent)] text-white' : 'text-[var(--text-muted)] hover:bg-[var(--surface-muted)]'}`}
                  >
                    编辑
                  </button>
                  <button
                    onClick={() => setPreviewMode(true)}
                    className={`px-2 py-0.5 text-xs ${previewMode ? 'bg-[var(--accent)] text-white' : 'text-[var(--text-muted)] hover:bg-[var(--surface-muted)]'}`}
                  >
                    预览
                  </button>
                </div>
              )}
            </div>
            {error && (
              <div className="shrink-0 flex items-center gap-2 px-4 py-2 bg-red-50 dark:bg-red-900/20 border-b border-red-200 dark:border-red-900/30 text-xs text-[var(--danger)]">
                <AlertCircle size={12} />
                {error}
              </div>
            )}

            {/* Editor area */}
            <div className="flex-1 overflow-hidden">
              {fileLoading ? (
                <div className="flex items-center justify-center h-full">
                  <div className="text-sm text-[var(--text-muted)]">正在加载文件…</div>
                </div>
              ) : isMdFile && previewMode ? (
                <div className="w-full h-full overflow-y-auto px-5 py-4 text-[15px] leading-[1.7] text-[var(--text)] prose prose-sm max-w-none bg-transparent">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
                </div>
              ) : (
                <textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  className={`w-full h-full resize-none bg-transparent text-[var(--text)] outline-none font-mono p-5 leading-relaxed ${
                    isMdFile ? 'text-[15px] leading-[1.7]' : 'text-[13px]'
                  }`}
                  placeholder="文件为空"
                  spellCheck={false}
                />
              )}
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-[var(--text-muted)]">
            <FolderOpen size={32} strokeWidth={1.5} />
            <div className="text-sm">从左侧选择文件进行编辑</div>
          </div>
        )}
      </div>

      {/* Unsaved-switch confirmation dialog */}
      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20">
          <div className="bg-[var(--surface-elevated)] border border-[var(--border)] rounded-xl shadow-lg p-5 max-w-sm w-full mx-4">
            <h3 className="text-sm font-semibold text-[var(--text)] mb-2">有未保存的更改</h3>
            <p className="text-xs text-[var(--text-muted)] mb-4">
              文件 <span className="font-mono">{currentPath}</span> 有未保存的更改，确认丢弃并打开其他文件？
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => confirmSwitch(false)}
                className="px-3 py-1.5 text-xs rounded-lg text-[var(--text-muted)] hover:bg-[var(--surface-muted)] transition-colors"
              >
                取消
              </button>
              <button
                onClick={() => confirmSwitch(true)}
                className="px-3 py-1.5 text-xs rounded-lg bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors"
              >
                丢弃并切换
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// FileTree recursive component
// ---------------------------------------------------------------------------

function FileTree({
  node,
  onSelect,
  selectedPath,
  depth = 0,
}: {
  node: FileNode
  onSelect: (path: string) => void
  selectedPath: string | null
  depth?: number
}) {
  const [open, setOpen] = useState(depth < 1)

  if (node.is_dir) {
    const children = node.children ?? []
    return (
      <div>
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1.5 w-full text-left px-1.5 py-1 rounded-md text-xs text-[var(--text-muted)] hover:bg-[var(--surface-muted)] transition-colors"
        >
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          <Folder size={12} />
          <span className="truncate font-medium">{node.name}</span>
        </button>
        {open && children.length > 0 && (
          <div className="ml-3 border-l border-[var(--border-subtle)] pl-1.5">
            {children.map((child) => (
              <FileTree
                key={child.path}
                node={child}
                onSelect={onSelect}
                selectedPath={selectedPath}
                depth={depth + 1}
              />
            ))}
          </div>
        )}
        {open && children.length === 0 && (
          <div className="ml-7 text-[10px] text-[var(--text-faint)] py-0.5">（空）</div>
        )}
      </div>
    )
  }

  const isSelected = selectedPath === node.path
  return (
    <button
      onClick={() => onSelect(node.path)}
      className={`flex items-center gap-1.5 w-full text-left px-1.5 py-1 rounded-md text-xs transition-colors ${
        isSelected
          ? 'bg-[var(--accent-soft)] text-[var(--accent)] font-medium'
          : 'text-[var(--text)] hover:bg-[var(--surface-muted)]'
      }`}
    >
      <FileText size={12} className="shrink-0" />
      <span className="truncate">{node.name}</span>
    </button>
  )
}
