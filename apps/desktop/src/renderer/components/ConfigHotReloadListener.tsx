import { useEffect, useState, useRef, useCallback } from 'react';
import { CheckCircle2, Info, RefreshCw } from 'lucide-react';
import { invalidateConfigCache } from '../lib/configCache';
import { useRestartRequired } from '../contexts/RestartRequiredContext';
import type { ConfigUpdatedPayload } from '../../shared/ipc';

/**
 * Issue #789: listens for the bridge's `config_updated` broadcast (emitted
 * after any config save) and reacts:
 *
 * 1. Invalidates the frontend config cache so all settings tabs re-read the
 *    new values without a restart.
 * 2. Marks "restart required" (with reasons) only when tier-C paths changed
 *    — tier-A/B saves no longer force the restart banner.
 * 3. Shows a transient toast with the per-tier message:
 *    「已生效」/「已保存，对新建会话生效」/「需要重启」.
 */
export function ConfigHotReloadListener() {
  const { markRestartRequired } = useRestartRequired();
  const [toast, setToast] = useState<{ kind: 'ok' | 'info' | 'warn'; text: string } | null>(null);
  const timerRef = useRef<number | null>(null);

  const showToast = useCallback((kind: 'ok' | 'info' | 'warn', text: string) => {
    setToast({ kind, text });
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => setToast(null), 4000);
  }, []);

  useEffect(() => {
    const off = window.miqi.config.onUpdated((payload: ConfigUpdatedPayload) => {
      // Always refresh the cached config — every save invalidates it.
      invalidateConfigCache();

      const applied = payload.applied ?? [];
      const newSessions = payload.newSessionsOnly ?? [];
      const restart = payload.restartRequired ?? [];
      const reasons = payload.restartReasons ?? [];

      if (restart.length > 0) {
        // Tier C — keep the restart banner (with reasons).
        markRestartRequired(reasons);
        showToast('warn', `已保存，部分配置需要重启后生效：${(reasons[0] ?? '').replace('，修改后需重启应用', '')}`);
      } else if (newSessions.length > 0) {
        showToast('info', '已保存，对新建会话生效');
      } else if (applied.length > 0) {
        showToast('ok', '配置已生效，无需重启');
      }
    });
    return () => {
      off();
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    };
  }, [markRestartRequired, showToast]);

  if (!toast) return null;

  const Icon = toast.kind === 'ok' ? CheckCircle2 : toast.kind === 'warn' ? RefreshCw : Info;
  const color =
    toast.kind === 'ok'
      ? 'var(--success)'
      : toast.kind === 'warn'
        ? 'var(--warning)'
        : 'var(--accent)';

  return (
    <div
      data-testid="config-updated-toast"
      className="fixed bottom-12 left-1/2 -translate-x-1/2 z-[100] flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-medium shadow-[0_4px_20px_rgba(0,0,0,0.18)]"
      style={{ background: 'var(--surface)', border: '1px solid var(--border-subtle)', color: 'var(--text)' }}
    >
      <Icon size={14} style={{ color }} />
      <span>{toast.text}</span>
    </div>
  );
}
