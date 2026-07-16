import { useCallback, useEffect, useState } from 'react';
import { useRuntime } from '../contexts/RuntimeContext';
import { AlertTriangle, RefreshCw, Loader2 } from 'lucide-react';
import { cn } from '../lib/utils';
import { MiQiLogo } from './MiQiLogo';

export function TopBar({ onNavigateSettings }: { onNavigateSettings: () => void }) {
  const { status } = useRuntime();
  const [bypassEnabled, setBypassEnabled] = useState(false);
  const [pressed, setPressed] = useState(false);

  useEffect(() => {
    const handler = () => {
      setBypassEnabled(sessionStorage.getItem('miqi:bypass:enabled') === 'true');
    };
    window.addEventListener('miqi:approval-bypass-updated', handler);
    return () => window.removeEventListener('miqi:approval-bypass-updated', handler);
  }, []);

  const handleClick = useCallback(() => {
    setPressed(true);
    setTimeout(() => setPressed(false), 600);
    onNavigateSettings();
  }, [onNavigateSettings]);

  const isRunning = status.state === 'running';
  const isStarting = status.state === 'starting' || status.state === 'stopping';

  return (
    <div className="flex items-center justify-between h-10 px-5 shrink-0"
      style={{ background: 'var(--topbar-bg)', borderBottom: '1px solid var(--topbar-border)' }}>
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold tracking-tight" style={{ color: 'var(--topbar-text)' }}>MiQi</span>
        <span className="text-xs font-light opacity-50" style={{ color: 'var(--topbar-text)' }}>Desktop</span>
      </div>
      <div className="flex items-center gap-2">
        {bypassEnabled && (
          <button type="button" onClick={handleClick}
            className={cn(
              'bypass-pill flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold',
              'transition-all duration-200 hover:-translate-y-px hover:shadow-sm',
              'focus:outline-none',
              pressed && 'bypass-pill-pressed',
            )}
            style={{
              background: 'var(--approval-warning-pill-bg)',
              color: 'var(--approval-warning-pill-text)',
              border: '1px solid var(--approval-warning-pill-border, var(--approval-warning-border))',
            }}
            title="审批绕过已开启" aria-label="审批绕过已开启">
            <AlertTriangle size={11} className="shrink-0" />
            <span className="whitespace-nowrap">绕过</span>
          </button>
        )}
        <div className={cn('flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium')}
          style={{
            background: isRunning ? 'var(--success-bg)' : isStarting ? 'var(--warning-bg)' : 'var(--danger-bg)',
            color: isRunning ? 'var(--success)' : isStarting ? 'var(--warning)' : 'var(--danger)',
          }}>
          {isStarting ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
          <span>{isRunning ? '已同步' : isStarting ? '同步中' : '离线'}</span>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium hidden sm:block" style={{ color: 'var(--topbar-text)' }}>MiQi 智能体</span>
        <MiQiLogo size={28} />
      </div>
    </div>
  );
}
