import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { cn } from '../lib/utils';

interface ApprovalBypassStatus {
  bypassAll?: boolean;
  bypassCommandApproval?: boolean;
  bypassFileWriteApproval?: boolean;
  bypassToolConfirmation?: boolean;
  bypassNetworkApproval?: boolean;
}

function hasApprovalBypass(config: Record<string, unknown>): boolean {
  const approvals = (config.approvals ?? {}) as ApprovalBypassStatus;
  // Never auto-enable from saved config — only show when explicitly enabled this session
  return false;
}

export function ApprovalBypassBanner({ onOpenApprovals }: { onOpenApprovals?: () => void }) {
  const [enabled, setEnabled] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  const load = useCallback(async () => {
    if (!(window as any).miqi?.config?.get) {
      setEnabled(false);
      return;
    }
    try {
      const config = await window.miqi.config.get();
      setEnabled(hasApprovalBypass(config));
    } catch {
      setEnabled(false);
    }
  }, []);

  useEffect(() => {
    load();
    window.addEventListener('miqi:approval-bypass-updated', load);
    return () => window.removeEventListener('miqi:approval-bypass-updated', load);
  }, [load]);

  useEffect(() => {
    if (!enabled) setDismissed(false);
  }, [enabled]);

  // Auto-dismiss after 3 seconds
  useEffect(() => {
    if (!enabled || dismissed) return;
    const t = setTimeout(() => setDismissed(true), 3000);
    return () => clearTimeout(t);
  }, [enabled, dismissed]);

  if (!enabled) return null;

  return (
    <div
      className={cn(
        'approval-bypass-island fixed left-1/2 top-12 z-50 flex max-w-[min(720px,calc(100vw-24px))] items-center gap-2 rounded-full border px-3 py-2 text-xs backdrop-blur',
        'transition-opacity duration-300',
        dismissed ? 'opacity-0 pointer-events-none' : 'opacity-100',
      )}
      style={{
        background: 'color-mix(in srgb, var(--approval-warning-bg) 92%, white)',
        borderColor: 'var(--approval-warning-border)',
        color: 'var(--approval-warning)',
      }}
    >
      <AlertTriangle size={14} className="shrink-0" />
      <span className="min-w-0 truncate font-medium">
        审批绕过已开启，本次会话的部分操作会直接放行。
      </span>
      <button
        type="button"
        onClick={() => {
          // Force navigate to approvals tab via direct state
          onOpenApprovals?.();
          // Fallback: close banner after navigating
          setTimeout(() => setDismissed(true), 500);
        }}
        className="shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold transition-colors hover:bg-[rgba(124,45,18,0.08)]"
      >
        查看设置
      </button>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full hover:bg-[rgba(124,45,18,0.12)] transition-colors"
        title="关闭提醒"
      >
        <X size={13} />
      </button>
    </div>
  );
}
