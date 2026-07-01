import { useState } from 'react';
import { cn } from '../lib/utils';
import { useRuntime } from '../contexts/RuntimeContext';
import { useRestartRequired } from '../contexts/RestartRequiredContext';
import { Loader2, RefreshCw } from 'lucide-react';

const STATES: Record<string, { label: string; color: string }> = {
  stopped: { label: '已停止', color: 'var(--text-faint)' },
  starting: { label: '启动中', color: 'var(--warning)' },
  running: { label: '运行中', color: 'var(--success)' },
  stopping: { label: '停止中', color: 'var(--warning)' },
  error: { label: '错误', color: 'var(--danger)' },
};

export function StatusBar() {
  const { status, start, stop } = useRuntime();
  const { restartRequired, clearRestartRequired } = useRestartRequired();
  const s = STATES[status.state] ?? STATES.stopped;
  const [restarting, setRestarting] = useState(false);
  const [restartError, setRestartError] = useState<string | null>(null);

  const handleRestart = async () => {
    setRestarting(true);
    setRestartError(null);
    try {
      await stop();
      await new Promise((r) => setTimeout(r, 800));
      const result = await start();
      if (result?.state === 'running') {
        clearRestartRequired();
      } else if (result) {
        setRestartError(`Runtime is ${result.state}`);
      }
    } catch (err: unknown) {
      setRestartError(err instanceof Error ? err.message : 'Restart failed');
    } finally {
      setRestarting(false);
    }
  };

  return (
    <div
      className="flex items-center gap-3 h-7 px-4 shrink-0 text-xs"
      style={{
        background: 'var(--surface-muted)',
        borderTop: '1px solid var(--border-subtle)',
        color: 'var(--text-faint)',
      }}
    >
      <span className="flex items-center gap-1.5">
        <span
          className={cn(
            'inline-block w-1.5 h-1.5 rounded-full',
            restartRequired && 'animate-pulse'
          )}
          style={{
            backgroundColor: restartRequired ? 'var(--warning)' : s.color,
          }}
        />
        <span style={{ color: 'var(--text-muted)' }}>{restartRequired ? '需要重启' : s.label}</span>
      </span>

      {status.configured && !restartRequired && (
        <span style={{ color: 'var(--text-faint)' }}>已配置</span>
      )}

      {restartRequired && (
        <span className="flex items-center gap-2" style={{ color: 'var(--warning)' }}>
          配置已变更
          <button
            onClick={handleRestart}
            disabled={restarting}
            className="flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium transition-all disabled:opacity-60"
            style={{ background: 'var(--accent)', color: 'var(--accent-text)' }}
          >
            {restarting ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />}
            立即重启
          </button>
        </span>
      )}

      {restartError && <span style={{ color: 'var(--danger)' }}>{restartError}</span>}

      <span className="ml-auto" style={{ color: 'var(--text-faint)' }}>
        MiQi Desktop v0.8
      </span>
    </div>
  );
}
