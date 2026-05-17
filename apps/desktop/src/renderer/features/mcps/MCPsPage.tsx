import { useState, useEffect } from 'react'
import { Plug, Plus, Pencil, Trash2, X } from 'lucide-react'
import type { McpServerInfo, McpServerConfig } from '../../../shared/ipc'

function MCPServerModal({
  open,
  onClose,
  onSave,
  initial,
}: {
  open: boolean
  onClose: () => void
  onSave: (name: string, config: McpServerConfig) => Promise<void>
  initial?: McpServerInfo | null
}) {
  const isEdit = !!initial
  const [name, setName] = useState(initial?.name ?? '')
  const [type, setType] = useState<'stdio' | 'http'>(
    initial?.command ? 'stdio' : initial?.url ? 'http' : 'stdio',
  )
  const [command, setCommand] = useState(initial?.command ?? '')
  const [argsStr, setArgsStr] = useState(initial?.args?.join(', ') ?? '')
  const [url, setUrl] = useState(initial?.url ?? '')
  const [envStr, setEnvStr] = useState(
    initial?.env
      ? Object.entries(initial.env)
          .map(([k, v]) => `${k}=${v}`)
          .join('\n')
      : '',
  )
  const [headersStr, setHeadersStr] = useState(
    initial?.headers
      ? Object.entries(initial.headers)
          .map(([k, v]) => `${k}: ${v}`)
          .join('\n')
      : '',
  )
  const [description, setDescription] = useState(initial?.description ?? '')
  const [toolTimeout, setToolTimeout] = useState(initial?.tool_timeout ?? 30)
  const [lazy, setLazy] = useState(initial?.lazy ?? false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  if (!open) return null

  const handleSave = async () => {
    setError('')
    if (!isEdit && !/^[a-z][a-z0-9-]*$/.test(name)) {
      setError('Name must start with a letter, use lowercase letters, digits, and hyphens')
      return
    }
    setSaving(true)
    try {
      const config: McpServerConfig = { description, tool_timeout: toolTimeout, lazy }
      if (type === 'stdio') {
        config.command = command
        config.args = argsStr
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)
        if (envStr.trim()) {
          config.env = {}
          for (const line of envStr.split('\n')) {
            const eq = line.indexOf('=')
            if (eq > 0) config.env[line.slice(0, eq).trim()] = line.slice(eq + 1).trim()
          }
        }
      } else {
        config.url = url
        if (headersStr.trim()) {
          config.headers = {}
          for (const line of headersStr.split('\n')) {
            const colon = line.indexOf(':')
            if (colon > 0) config.headers[line.slice(0, colon).trim()] = line.slice(colon + 1).trim()
          }
        }
      }
      await onSave(name, config)
      onClose()
    } catch (e: any) {
      setError(e?.message ?? 'Save failed')
    }
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div
        className="rounded-xl shadow-2xl w-full max-w-lg mx-4"
        style={{ background: 'var(--surface)' }}
      >
        <div
          className="flex items-center justify-between px-5 py-4 border-b"
          style={{ borderColor: 'var(--border)' }}
        >
          <h2 className="text-base font-semibold" style={{ color: 'var(--text)' }}>
            {isEdit ? '编辑 MCP 服务器' : '添加 MCP 服务器'}
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
          {/* Name */}
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>
              名称
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isEdit}
              placeholder="my-mcp-server"
              className="w-full px-3 py-2 rounded-lg text-sm border"
              style={{
                background: 'var(--surface-muted)',
                color: 'var(--text)',
                borderColor: 'var(--border)',
              }}
            />
          </div>

          {/* Type toggle */}
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>
              连接类型
            </label>
            <div className="flex gap-2">
              {(['stdio', 'http'] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setType(t)}
                  className="px-4 py-1.5 rounded-lg text-xs font-medium transition-colors"
                  style={{
                    background: type === t ? 'var(--accent)' : 'var(--surface-muted)',
                    color: type === t ? 'white' : 'var(--text-muted)',
                  }}
                >
                  {t.toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {/* Stdio fields */}
          {type === 'stdio' && (
            <>
              <div>
                <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>
                  Command
                </label>
                <input
                  type="text"
                  value={command}
                  onChange={(e) => setCommand(e.target.value)}
                  placeholder="npx"
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
                  Args (逗号分隔)
                </label>
                <input
                  type="text"
                  value={argsStr}
                  onChange={(e) => setArgsStr(e.target.value)}
                  placeholder="-y, @modelcontextprotocol/server-filesystem"
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
                  Env (key=value, 每行一个)
                </label>
                <textarea
                  value={envStr}
                  onChange={(e) => setEnvStr(e.target.value)}
                  rows={3}
                  placeholder="MY_VAR=value"
                  className="w-full px-3 py-2 rounded-lg text-sm border resize-none"
                  style={{
                    background: 'var(--surface-muted)',
                    color: 'var(--text)',
                    borderColor: 'var(--border)',
                  }}
                />
              </div>
            </>
          )}

          {/* HTTP fields */}
          {type === 'http' && (
            <>
              <div>
                <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>
                  URL
                </label>
                <input
                  type="text"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="http://localhost:8080/mcp"
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
                  Headers (key: value, 每行一个)
                </label>
                <textarea
                  value={headersStr}
                  onChange={(e) => setHeadersStr(e.target.value)}
                  rows={3}
                  placeholder="Authorization: Bearer token"
                  className="w-full px-3 py-2 rounded-lg text-sm border resize-none"
                  style={{
                    background: 'var(--surface-muted)',
                    color: 'var(--text)',
                    borderColor: 'var(--border)',
                  }}
                />
              </div>
            </>
          )}

          {/* Description */}
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>
              描述 (可选)
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="简要描述此 MCP 服务器"
              className="w-full px-3 py-2 rounded-lg text-sm border"
              style={{
                background: 'var(--surface-muted)',
                color: 'var(--text)',
                borderColor: 'var(--border)',
              }}
            />
          </div>

          {/* Tool timeout */}
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--text-muted)' }}>
              工具超时 (秒)
            </label>
            <input
              type="number"
              value={toolTimeout}
              onChange={(e) => setToolTimeout(Number(e.target.value))}
              className="w-24 px-3 py-2 rounded-lg text-sm border"
              style={{
                background: 'var(--surface-muted)',
                color: 'var(--text)',
                borderColor: 'var(--border)',
              }}
            />
          </div>

          {/* Lazy */}
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={lazy}
              onChange={(e) => setLazy(e.target.checked)}
              className="rounded"
            />
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              网关模式 — 按需激活工具
            </span>
          </label>

          {error && (
            <div className="text-xs px-3 py-2 rounded" style={{ background: 'var(--danger-bg)', color: 'var(--danger)' }}>
              {error}
            </div>
          )}
        </div>

        <div
          className="flex justify-end gap-2 px-5 py-4 border-t"
          style={{ borderColor: 'var(--border)' }}
        >
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-xs font-medium transition-colors hover:bg-[var(--surface-muted)]"
            style={{ color: 'var(--text-muted)' }}
          >
            取消
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 rounded-lg text-xs font-medium text-white transition-colors"
            style={{ background: 'var(--accent)' }}
          >
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  )
}

export function MCPsPage() {
  const [servers, setServers] = useState<McpServerInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingServer, setEditingServer] = useState<McpServerInfo | null>(null)

  const loadServers = async () => {
    try {
      const res = await window.miqi.mcps.list()
      setServers(res.servers ?? [])
    } catch {
      // bridge not available
    }
    setLoading(false)
  }

  useEffect(() => {
    loadServers()
  }, [])

  const handleSave = async (name: string, config: McpServerConfig) => {
    await window.miqi.mcps.upsert(name, config)
    await loadServers()
  }

  const handleDelete = async (name: string) => {
    if (!window.confirm(`确认删除 MCP 服务器 "${name}"？`)) return
    await window.miqi.mcps.delete(name)
    await loadServers()
  }

  const handleEdit = (s: McpServerInfo) => {
    setEditingServer(s)
    setModalOpen(true)
  }

  const handleAdd = () => {
    setEditingServer(null)
    setModalOpen(true)
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between px-6 py-4 border-b shrink-0"
        style={{ borderColor: 'var(--border)' }}
      >
        <h1 className="text-lg font-semibold" style={{ color: 'var(--text)' }}>
          MCP 服务器
        </h1>
        <button
          onClick={handleAdd}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white transition-colors"
          style={{ background: 'var(--accent)' }}
        >
          <Plus size={14} />
          添加服务器
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="w-5 h-5 border-2 border-[var(--border)] border-t-[var(--accent)] rounded-full animate-spin" />
          </div>
        ) : servers.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <Plug size={36} style={{ color: 'var(--text-faint)' }} />
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
              尚未配置 MCP 服务器
            </p>
            <p className="text-xs" style={{ color: 'var(--text-faint)' }}>
              点击「添加服务器」开始配置 MCP 连接
            </p>
          </div>
        ) : (
          <div className="grid gap-3">
            {servers.map((srv) => (
              <div
                key={srv.name}
                className="rounded-xl border p-4 transition-colors"
                style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className="font-mono text-sm font-semibold"
                        style={{ color: 'var(--text)' }}
                      >
                        {srv.name}
                      </span>
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase"
                        style={{
                          background: srv.command ? 'var(--accent-bg)' : 'var(--info-bg)',
                          color: srv.command ? 'var(--accent)' : 'var(--info)',
                        }}
                      >
                        {srv.command ? 'stdio' : 'http'}
                      </span>
                    </div>
                    {srv.description && (
                      <p className="text-xs mb-2" style={{ color: 'var(--text-muted)' }}>
                        {srv.description}
                      </p>
                    )}
                    <p
                      className="text-xs font-mono truncate"
                      style={{ color: 'var(--text-faint)' }}
                    >
                      {srv.command
                        ? `${srv.command} ${(srv.args ?? []).join(' ')}`
                        : srv.url ?? ''}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => handleEdit(srv)}
                      className="p-1.5 rounded-lg transition-colors hover:bg-[var(--surface-muted)]"
                      style={{ color: 'var(--text-muted)' }}
                      title="编辑"
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      onClick={() => handleDelete(srv.name)}
                      className="p-1.5 rounded-lg transition-colors hover:bg-[var(--danger-bg)]"
                      style={{ color: 'var(--danger)' }}
                      title="删除"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <MCPServerModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSave={handleSave}
        initial={editingServer}
      />
    </div>
  )
}
