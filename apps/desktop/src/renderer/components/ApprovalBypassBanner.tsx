import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { cn } from '../lib/utils';

const SESSION_KEY = 'miqi:bypass:enabled';

export function ApprovalBypassBanner() {
  const [visible, setVisible] = useState(() => sessionStorage.getItem(SESSION_KEY) === 'true');

  const show = useCallback(() => {
    sessionStorage.setItem(SESSION_KEY, 'true');
    setVisible(true);
  }, []);

  const dismiss = useCallback(() => {
    sessionStorage.removeItem(SESSION_KEY);
    setVisible(false);
  }, []);

  useEffect(() => {
    const handler = () => show();
    window.addEventListener('miqi:approval-bypass-updated', handler);
    return () => window.removeEventListener('miqi:approval-bypass-updated', handler);
  }, [show]);

  // Auto-dismiss after 3 seconds
  useEffect(() => {
    if (!visible) return;
    const t = setTimeout(dismiss, 3000);
    return () => clearTimeout(t);
  }, [visible, dismiss]);

  return (
    <div
      className={cn(
        'approval-bypass-island fixed left-1/2 top-12 z-50 flex max-w-[min(720px,calc(100vw-24px))] items-center gap-2 rounded-full border px-3 py-2 text-xs backdrop-blur',
        'transition-all duration-300',
        visible ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-2 pointer-events-none',
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
          window.dispatchEvent(new Event('miqi:navigate:approvals'));
          dismiss();
        }}
        className="shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold transition-colors hover:bg-[rgba(124,45,18,0.08)]"
      >
        查看设置
      </button>
      <button
        type="button"
        onClick={dismiss}
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full hover:bg-[rgba(124,45,18,0.12)] transition-colors"
        title="关闭提醒"
      >
        <X size={13} />
      </button>
    </div>
  );
}
