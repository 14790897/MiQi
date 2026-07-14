import { useEffect, useState } from 'react';
import { useRuntime } from '../contexts/RuntimeContext';
import { AlertTriangle, RefreshCw, Loader2 } from 'lucide-react';
import { cn } from '../lib/utils';
import { MiQiLogo } from './MiQiLogo';

interface ApprovalBypassStatus {
  bypassAll?: boolean;
  bypassCommandApproval?: boolean;
  bypassFileWriteApproval?: boolean;
  bypassToolConfirmation?: boolean;
  bypassNetworkApproval?: boolean;
}

function isBypassEnabled(status: ApprovalBypassStatus | null): boolean {
  if (!status) return false;
  return Boolean(
    status.bypassAll ||
    status.bypassCommandApproval ||
    status.bypassFileWriteApproval ||
    status.bypassToolConfirmation ||
    status.bypassNetworkApproval
  );
}

function getBypassLabel(status: ApprovalBypassStatus | null): string {
  if (status?.bypassAll) return '全部绕过';
  return '绕过';
}

function getBypassTitle(status: ApprovalBypassStatus | null): string {
  if (status?.bypassAll) return '所有审批类别已启用绕过';
  const labels: string[] = [];
  if (status?.bypassCommandApproval) labels.push('命令审批');
  if (status?.bypassFileWriteApproval) labels.push('文件写入审批');
  if (status?.bypassToolConfirmation) labels.push('工具确认');
  if (status?.bypassNetworkApproval) labels.push('网络审批');
  return labels.length > 0
    ? `已绕过: ${labels.join('、')}`
    : '打开审批设置';
}

export function TopBar({ onOpenApprovals }: { onOpenApprovals?: () => void }) {
  const { status } = useRuntime();
  const [approvalBypass, setApprovalBypass] = useState<ApprovalBypassStatus | null>(null);

  const isRunning = status.state === 'running';
  const isStarting = status.state === 'starting' || status.state === 'stopping';
  const bypassEnabled = isBypassEnabled(approvalBypass);

  useEffect(() => {
    let cancelled = false;
    let inFlight = false; // debounce guard: don't pile up requests when bridge is slow

    const loadApprovalBypass = async () => {
      if (inFlight) return; // skip if previous request still pending
      if (!(window as any).miqi?.config?.get) {
        if (!cancelled) setApprovalBypass(null);
        return;
      }
      inFlight = true;
      try {
        const cfg = await window.miqi.config.get();
        const approvals = (cfg.approvals ?? {}) as ApprovalBypassStatus;
        if (!cancelled) {
          setApprovalBypass(approvals);
        }
      } catch {
        // Keep the last known good state — bridge may be temporarily busy
        // Don't clear approvalBypass; a null here cascades into false
        // "runtime not started" UI.  See PR #xxx.
      } finally {
        inFlight = false;
      }
    };
    loadApprovalBypass();
    window.addEventListener('miqi:approval-bypass-updated', loadApprovalBypass);
    const timer = window.setInterval(loadApprovalBypass, 30_000);
    return () => {
      cancelled = true;
      window.removeEventListener('miqi:approval-bypass-updated', loadApprovalBypass);
      window.clearInterval(timer);
    };
  }, []);

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
          Desktop
        </span>
      </div>

      {/* Center: status pills */}
      <div className="flex items-center gap-2">
        {bypassEnabled && (
          <button
            type="button"
            onClick={onOpenApprovals}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold',
              'transition-transform hover:scale-[1.02] focus:outline-none'
            )}
            style={{
              background: 'var(--approval-warning-pill-bg)',
              color: 'var(--approval-warning-pill-text)',
              border: '1px solid var(--approval-warning-border)',
            }}
            title={getBypassTitle(approvalBypass)}
            aria-label={getBypassTitle(approvalBypass)}
          >
            <AlertTriangle size={11} className="shrink-0" />
            <span className="whitespace-nowrap">{getBypassLabel(approvalBypass)}</span>
          </button>
        )}
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
          <span>{isRunning ? '已同步' : isStarting ? '同步中' : '离线'}</span>
        </div>
      </div>

      {/* Right: user avatar */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium hidden sm:block" style={{ color: 'var(--topbar-text)' }}>
          MiQi 智能体
        </span>
        <MiQiLogo size={28} />
      </div>
    </div>
  );
}
