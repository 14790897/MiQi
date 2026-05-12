import { Shield, Terminal, X } from 'lucide-react'
import { useApproval } from '../../contexts/ApprovalContext'

export function ApprovalModal() {
  const { pending, resolve } = useApproval()
  if (!pending) return null

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center pb-8 px-4 pointer-events-none">
      <div
        className="pointer-events-auto w-full max-w-[600px] bg-[var(--surface-elevated)] border border-[var(--danger)] rounded-xl shadow-2xl overflow-hidden"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="approval-title"
      >
        {/* Header */}
        <div className="flex items-center gap-2 px-5 py-3 bg-[color-mix(in_srgb,var(--danger)_12%,transparent)] border-b border-[var(--danger)]">
          <Shield size={16} className="text-[var(--danger)] shrink-0" />
          <span id="approval-title" className="text-sm font-semibold text-[var(--danger)]">
            Dangerous Command
          </span>
          <span className="ml-2 text-xs text-[var(--text-muted)] font-normal">
            {pending.description}
          </span>
          <button
            onClick={() => resolve('deny')}
            className="ml-auto text-[var(--text-faint)] hover:text-[var(--text)] transition-colors"
            title="Deny"
          >
            <X size={14} />
          </button>
        </div>

        {/* Command */}
        <div className="px-5 py-3">
          <div className="flex items-start gap-2">
            <Terminal size={13} className="text-[var(--text-faint)] mt-1 shrink-0" />
            <pre className="text-xs font-mono text-[var(--text)] bg-[var(--surface-muted)] rounded-lg px-3 py-2 flex-1 overflow-x-auto whitespace-pre-wrap break-all">
              {pending.command}
            </pre>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 px-5 py-3 border-t border-[var(--border-subtle)]">
          <span className="text-xs text-[var(--text-faint)] flex-1">
            Choose how to handle this command:
          </span>
          <button
            onClick={() => resolve('deny')}
            className="px-3 py-1.5 rounded-lg text-sm font-medium bg-[color-mix(in_srgb,var(--danger)_15%,transparent)] text-[var(--danger)] hover:bg-[color-mix(in_srgb,var(--danger)_25%,transparent)] transition-colors"
          >
            Deny
          </button>
          <button
            onClick={() => resolve('once')}
            className="px-3 py-1.5 rounded-lg text-sm font-medium bg-[var(--surface-muted)] text-[var(--text)] hover:bg-[var(--border-subtle)] transition-colors"
          >
            Allow once
          </button>
          <button
            onClick={() => resolve('session')}
            className="px-3 py-1.5 rounded-lg text-sm font-medium bg-[var(--surface-muted)] text-[var(--text)] hover:bg-[var(--border-subtle)] transition-colors"
          >
            Allow session
          </button>
          {pending.allow_permanent && (
            <button
              onClick={() => resolve('always')}
              className="px-3 py-1.5 rounded-lg text-sm font-medium bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors"
            >
              Always allow
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
