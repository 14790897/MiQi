import { useRuntime } from '../contexts/RuntimeContext';
import { Cloud, ShieldCheck, RefreshCw, Loader2 } from 'lucide-react';
import { cn } from '../lib/utils';

export function TopBar() {
  const { status } = useRuntime();

  const isRunning = status.state === 'running';
  const isStarting = status.state === 'starting' || status.state === 'stopping';

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
        <span className="text-xs font-light opacity-50" style={{ color: 'var(--topbar-text)' }}>
          Workbench
        </span>
      </div>

      {/* Center: status pills */}
      <div className="flex items-center gap-2">
        {/* Sync state */}
        <div
          className={cn('flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium')}
          style={{
            background: isRunning
              ? 'var(--success-bg)'
              : isStarting
                ? 'var(--warning-bg)'
                : 'var(--danger-bg)',
            color: isRunning ? 'var(--success)' : isStarting ? 'var(--warning)' : 'var(--danger)',
          }}
        >
          {isStarting ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
          <span>{isRunning ? 'SYNCED' : isStarting ? 'SYNCING' : 'OFFLINE'}</span>
        </div>
      </div>

      {/* Right: user avatar */}
      <div className="flex items-center gap-2">
        <div className="text-right hidden sm:block">
          <div className="text-xs font-medium" style={{ color: 'var(--topbar-text)' }}>
            MiQi Agent
          </div>
          <div className="text-[10px]" style={{ color: 'var(--topbar-muted-text)' }}>
            Core Agent
          </div>
        </div>
        <div
          className="w-7 h-7 rounded-md flex items-center justify-center text-xs font-bold"
          style={{
            background: 'var(--avatar-dark)',
            color: '#fff',
          }}
        >
          M
        </div>
      </div>
    </div>
  );
}
