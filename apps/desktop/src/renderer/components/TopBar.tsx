import { useRuntime } from '../contexts/RuntimeContext'
import { Cloud, ShieldCheck, RefreshCw, Loader2 } from 'lucide-react'
import { cn } from '../lib/utils'

export function TopBar() {
  const { status } = useRuntime()

  const isRunning = status.state === 'running'
  const isStarting = status.state === 'starting' || status.state === 'stopping'

  return (
    <div
      className="flex items-center justify-between h-10 px-5 shrink-0"
      style={{
        background: 'var(--topbar-bg)',
        borderBottom: '1px solid var(--topbar-border)',
      }}
    >
      {/* Left: logo text */}
      <div className="flex items-center gap-2">
        <span
          className="text-sm font-semibold tracking-tight"
          style={{ color: 'var(--topbar-text)' }}
        >
          MiQi
        </span>
        <span
          className="text-xs font-light opacity-50"
          style={{ color: 'var(--topbar-text)' }}
        >
          Workbench
        </span>
      </div>

      {/* Center: status pills */}
      <div className="flex items-center gap-2">
        {/* Cloud node */}
        <div
          className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium"
          style={{
            background: 'rgba(255,255,255,0.08)',
            color: 'rgba(255,255,255,0.6)',
          }}
        >
          <Cloud size={11} />
          <span>CLOUD NODE</span>
        </div>

        {/* Admin / runtime */}
        <div
          className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium"
          style={{
            background: 'rgba(255,255,255,0.08)',
            color: 'rgba(255,255,255,0.6)',
          }}
        >
          <ShieldCheck size={11} />
          <span>ADMIN ACCESS</span>
        </div>

        {/* Sync state */}
        <div
          className={cn(
            'flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium',
          )}
          style={{
            background: isRunning
              ? 'rgba(45, 122, 74, 0.3)'
              : isStarting
              ? 'rgba(180, 120, 20, 0.3)'
              : 'rgba(180, 60, 60, 0.3)',
            color: isRunning
              ? '#6ee09a'
              : isStarting
              ? '#f0c060'
              : '#f08080',
          }}
        >
          {isStarting ? (
            <Loader2 size={11} className="animate-spin" />
          ) : (
            <RefreshCw size={11} />
          )}
          <span>
            {isRunning ? 'SYNCED' : isStarting ? 'SYNCING' : 'OFFLINE'}
          </span>
        </div>
      </div>

      {/* Right: user avatar */}
      <div className="flex items-center gap-2">
        <div className="text-right hidden sm:block">
          <div className="text-xs font-medium" style={{ color: 'rgba(255,255,255,0.75)' }}>
            MiQi Agent
          </div>
          <div className="text-[10px]" style={{ color: 'rgba(255,255,255,0.4)' }}>
            Core Agent
          </div>
        </div>
        <div
          className="w-7 h-7 rounded-md flex items-center justify-center text-xs font-bold"
          style={{ background: 'rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.8)' }}
        >
          M
        </div>
      </div>
    </div>
  )
}
