import { useState, useEffect, useCallback } from 'react'
import { Shield, Trash2, Loader2 } from 'lucide-react'
import type { ApprovalsListResult } from '../../../shared/ipc'

export function ApprovalsPage() {
  const [data, setData] = useState<ApprovalsListResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [clearing, setClearing] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const result = await window.miqi.approvals.list()
      setData(result)
    } catch {
      // runtime not running
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const clearOne = async (pattern: string) => {
    setClearing(pattern)
    try {
      await window.miqi.approvals.clearPermanent(pattern)
      await load()
    } finally {
      setClearing(null)
    }
  }

  const clearAll = async () => {
    setClearing('all')
    try {
      await window.miqi.approvals.clearPermanent()
      await load()
    } finally {
      setClearing(null)
    }
  }

  return (
    <div className="flex flex-col h-full bg-[var(--background)]">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border-subtle)] bg-[var(--surface)] shrink-0">
        <div>
          <h1 className="text-base font-semibold text-[var(--text)]">命令审批</h1>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            Agent 执行危险 shell 命令前需要授权。此页管理永久白名单。
          </p>
        </div>
        <button
          onClick={load}
          className="text-xs text-[var(--text-faint)] hover:text-[var(--text-muted)] transition-colors px-2 py-1 rounded"
        >
          刷新
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-6">
        {loading ? (
          <div className="flex items-center justify-center h-40 text-sm text-[var(--text-faint)]">
            <Loader2 size={16} className="animate-spin mr-2" /> 加载中…
          </div>
        ) : !data ? (
          <div className="flex flex-col items-center justify-center h-40 gap-2 text-sm text-[var(--text-faint)]">
            <Shield size={24} />
            <span>MiQi 运行时未启动</span>
          </div>
        ) : (
          <>
            {/* Status */}
            <div className="bg-[var(--surface)] border border-[var(--border-subtle)] rounded-xl px-5 py-3 flex items-center gap-4 text-sm">
              <div className="flex items-center gap-2">
                <Shield size={14} className={data.enabled ? 'text-[var(--success)]' : 'text-[var(--text-faint)]'} />
                <span className="text-[var(--text-muted)]">审批系统</span>
                <span className={data.enabled ? 'text-[var(--success)]' : 'text-[var(--text-faint)]'}>
                  {data.enabled ? '已启用' : '已禁用'}
                </span>
              </div>
              <div className="text-[var(--text-faint)]">·</div>
              <span className="text-[var(--text-muted)]">超时：{data.timeout}秒</span>
              <div className="text-[var(--text-faint)]">·</div>
              <span className="text-[var(--text-muted)]">
                {data.pending_ids.length} 个待审批
              </span>
            </div>

            {/* Permanent allowlist */}
            <div className="bg-[var(--surface)] border border-[var(--border-subtle)] rounded-xl overflow-hidden">
              <div className="flex items-center justify-between px-5 py-2 border-b border-[var(--border-subtle)] bg-[var(--surface-muted)]">
                <span className="text-xs font-semibold uppercase tracking-widest text-[var(--text-faint)]">
                  永久白名单（{data.permanent_allowlist.length}）
                </span>
                {data.permanent_allowlist.length > 0 && (
                  <button
                    onClick={clearAll}
                    disabled={clearing === 'all'}
                    className="text-xs text-[var(--danger)] hover:underline disabled:opacity-50"
                  >
                    {clearing === 'all' ? '清除中…' : '全部清除'}
                  </button>
                )}
              </div>
              {data.permanent_allowlist.length === 0 ? (
                <div className="px-5 py-6 text-sm text-[var(--text-faint)] text-center">
                  暂无永久白名单记录
                </div>
              ) : (
                <div className="divide-y divide-[var(--border-subtle)]">
                  {data.permanent_allowlist.map((pattern) => (
                    <div key={pattern} className="flex items-center gap-3 px-5 py-2.5 hover:bg-[var(--surface-muted)] transition-colors">
                      <code className="flex-1 text-xs font-mono text-[var(--text)]">{pattern}</code>
                      <button
                        onClick={() => clearOne(pattern)}
                        disabled={clearing === pattern}
                        title="从白名单移除"
                        className="shrink-0 p-1 rounded text-[var(--text-faint)] hover:text-[var(--danger)] transition-colors disabled:opacity-50"
                      >
                        {clearing === pattern
                          ? <Loader2 size={13} className="animate-spin" />
                          : <Trash2 size={13} />}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
