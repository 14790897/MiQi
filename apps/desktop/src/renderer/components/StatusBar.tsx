import { cn } from '../lib/utils'
import { useRuntime } from '../contexts/RuntimeContext'

const STATES: Record<string, { label: string; color: string }> = {
  stopped: { label: 'Stopped', color: 'var(--text-faint)' },
  starting: { label: 'Starting', color: 'var(--warning)' },
  running: { label: 'Running', color: 'var(--success)' },
  stopping: { label: 'Stopping', color: 'var(--warning)' },
  error: { label: 'Error', color: 'var(--danger)' },
}

export function StatusBar() {
  const { status } = useRuntime()
  const s = STATES[status.state] ?? STATES.stopped

  return (
    <div className="flex items-center gap-3 h-8 px-4 border-t border-[var(--border-subtle)] bg-[var(--surface)] text-xs text-[var(--text-muted)] shrink-0">
      <span className="flex items-center gap-1.5">
        <span
          className="inline-block w-2 h-2 rounded-full"
          style={{ backgroundColor: s.color }}
        />
        {s.label}
      </span>
      {status.configured && (
        <span className="text-[var(--text-faint)]">Configured</span>
      )}
      <span className="ml-auto text-[var(--text-faint)]">MiQi Desktop</span>
    </div>
  )
}
