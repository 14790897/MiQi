import { useState } from 'react'
import { cn } from '../lib/utils'
import { useRuntime } from '../contexts/RuntimeContext'
import { useRestartRequired } from '../contexts/RestartRequiredContext'
import { Loader2, RefreshCw } from 'lucide-react'

const STATES: Record<string, { label: string; color: string }> = {
  stopped: { label: '已停止', color: 'var(--text-faint)' },
  starting: { label: '启动中', color: 'var(--warning)' },
  running: { label: '运行中', color: 'var(--success)' },
  stopping: { label: '停止中', color: 'var(--warning)' },
  error: { label: '错误', color: 'var(--danger)' },
}

export function StatusBar() {
  const { status, start, stop } = useRuntime()
  const { restartRequired, clearRestartRequired } = useRestartRequired()
  const s = STATES[status.state] ?? STATES.stopped
  const [restarting, setRestarting] = useState(false)
  const [restartError, setRestartError] = useState<string | null>(null)

  const handleRestart = async () => {
    setRestarting(true)
    setRestartError(null)
    try {
      await stop()
      // Brief pause for the process to exit cleanly
      await new Promise((r) => setTimeout(r, 800))
      const result = await start()
      if (result.state === 'running') {
        clearRestartRequired()
      } else {
        setRestartError(`Runtime is ${result.state}`)
      }
    } catch (err: unknown) {
      setRestartError(err instanceof Error ? err.message : 'Restart failed')
    } finally {
      setRestarting(false)
    }
  }

  return (
    <div className="flex items-center gap-3 h-8 px-4 border-t border-[var(--border-subtle)] bg-[var(--surface)] text-xs text-[var(--text-muted)] shrink-0">
      <span className="flex items-center gap-1.5">
        <span
          className={cn(
            'inline-block w-2 h-2 rounded-full',
            restartRequired && 'animate-pulse',
          )}
          style={{
            backgroundColor: restartRequired ? 'var(--warning)' : s.color,
          }}
        />
        {restartRequired ? '需要重启' : s.label}
      </span>
      {status.configured && !restartRequired && (
        <span className="text-[var(--text-faint)]">已配置</span>
      )}

      {/* Restart prompt */}
      {restartRequired && (
        <span className="flex items-center gap-2 text-[var(--warning)]">
          配置已变更
          <button
            onClick={handleRestart}
            disabled={restarting}
            className="flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-[var(--warning)] text-white hover:brightness-110 transition-all disabled:opacity-60"
          >
            {restarting ? (
              <Loader2 size={10} className="animate-spin" />
            ) : (
              <RefreshCw size={10} />
            )}
            立即重启
          </button>
        </span>
      )}

      {restartError && (
        <span className="text-[var(--danger)]">{restartError}</span>
      )}

      {restartError && (
        <span className="text-[var(--danger)]">{restartError}</span>
      )}

      <span className="ml-auto text-[var(--text-faint)]">MiQi Desktop</span>
    </div>
  )
}
