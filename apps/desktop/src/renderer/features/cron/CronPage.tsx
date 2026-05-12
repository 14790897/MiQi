import { useState, useEffect, useCallback } from 'react'
import {
  Clock, Plus, RefreshCw, Loader2, Trash2,
  Play, Pause, Power, PowerOff,
  ChevronDown, ChevronRight, X,
} from 'lucide-react'
import { cn } from '../../lib/utils'
import type { CronJob, CronRunEntry } from '../../../shared/ipc'

type ScheduleKind = 'at' | 'every' | 'cron'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatMs(ms: number | null): string {
  if (!ms) return '—'
  const d = new Date(ms)
  return d.toLocaleString()
}

function durationMs(startMs: number): string {
  const elapsed = Date.now() - startMs
  if (elapsed < 1000) return `${elapsed}ms`
  if (elapsed < 60000) return `${(elapsed / 1000).toFixed(1)}s`
  return `${(elapsed / 60000).toFixed(1)}m`
}

function scheduleLabel(job: CronJob): string {
  const s = job.schedule
  if (s.kind === 'at') return `At ${formatMs(s.atMs)}`
  if (s.kind === 'every') return s.everyMs ? `Every ${(s.everyMs / 1000).toFixed(0)}s` : 'Every —'
  if (s.kind === 'cron') return s.expr ?? 'cron —'
  return s.kind
}

// ---------------------------------------------------------------------------
// Create / Edit modal
// ---------------------------------------------------------------------------

interface JobFormData {
  name: string
  scheduleKind: ScheduleKind
  atMs: string
  everyMs: string
  expr: string
  tz: string
  message: string
}

function emptyForm(): JobFormData {
  return { name: '', scheduleKind: 'every', atMs: '', everyMs: '60000', expr: '', tz: '', message: '' }
}

function CreateEditModal({
  job,
  onClose,
  onSaved,
}: {
  job?: CronJob
  onClose: () => void
  onSaved: () => void
}) {
  const isEdit = !!job
  const [form, setForm] = useState<JobFormData>(() => {
    if (job) {
      return {
        name: job.name,
        scheduleKind: job.schedule.kind,
        atMs: job.schedule.atMs ? String(job.schedule.atMs) : '',
        everyMs: job.schedule.everyMs ? String(job.schedule.everyMs) : '',
        expr: job.schedule.expr ?? '',
        tz: job.schedule.tz ?? '',
        message: job.payload.message ?? '',
      }
    }
    return emptyForm()
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const set = (k: keyof JobFormData, v: string) => setForm(prev => ({ ...prev, [k]: v }))

  const handleSubmit = async () => {
    if (!form.name.trim()) {
      setError('Name is required')
      return
    }
    setSaving(true)
    setError(null)

    const payload: Record<string, unknown> = {
      name: form.name.trim(),
      scheduleKind: form.scheduleKind,
      message: form.message,
    }
    if (form.scheduleKind === 'at') {
      const ms = parseInt(form.atMs, 10)
      if (!ms || ms <= Date.now()) {
        setError('atMs must be a future timestamp in milliseconds')
        setSaving(false)
        return
      }
      payload.atMs = ms
    } else if (form.scheduleKind === 'every') {
      const ms = parseInt(form.everyMs, 10)
      if (!ms || ms < 1000) {
        setError('everyMs must be at least 1000 (1 second)')
        setSaving(false)
        return
      }
      payload.everyMs = ms
    } else if (form.scheduleKind === 'cron') {
      if (!form.expr.trim()) {
        setError('expr is required for cron schedules')
        setSaving(false)
        return
      }
      payload.expr = form.expr.trim()
      if (form.tz.trim()) payload.tz = form.tz.trim()
    }

    try {
      if (isEdit) {
        await window.miqi.cron.update({ jobId: job!.id, ...payload })
      } else {
        await window.miqi.cron.create(payload)
      }
      onSaved()
      onClose()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-[var(--surface-elevated)] border border-[var(--border)] rounded-xl shadow-xl w-[520px] max-h-[80vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border-subtle)]">
          <h2 className="text-sm font-semibold text-[var(--text)]">
            {isEdit ? 'Edit Job' : 'Create Job'}
          </h2>
          <button onClick={onClose} className="text-[var(--text-faint)] hover:text-[var(--text)] transition-colors">
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-4 flex flex-col gap-4">
          {/* Name */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">Name</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              placeholder="e.g. Daily report"
              className="w-full px-3 py-2 rounded-lg text-sm bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-[var(--accent)]"
            />
          </div>

          {/* Schedule kind */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">Schedule Kind</label>
            <div className="flex gap-1.5">
              {(['at', 'every', 'cron'] as ScheduleKind[]).map(k => (
                <button
                  key={k}
                  onClick={() => set('scheduleKind', k)}
                  className={cn(
                    'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
                    form.scheduleKind === k
                      ? 'bg-[var(--accent)] text-white'
                      : 'bg-[var(--surface-muted)] text-[var(--text-muted)] hover:text-[var(--text)]',
                  )}
                >
                  {k}
                </button>
              ))}
            </div>
          </div>

          {/* Schedule expression */}
          {form.scheduleKind === 'at' && (
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">At (ms timestamp)</label>
              <input
                type="number"
                value={form.atMs}
                onChange={(e) => set('atMs', e.target.value)}
                placeholder={String(Date.now() + 60000)}
                className="w-full px-3 py-2 rounded-lg text-sm bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-[var(--accent)] font-mono"
              />
            </div>
          )}
          {form.scheduleKind === 'every' && (
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">Every (ms)</label>
              <input
                type="number"
                value={form.everyMs}
                onChange={(e) => set('everyMs', e.target.value)}
                placeholder="60000"
                className="w-full px-3 py-2 rounded-lg text-sm bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-[var(--accent)] font-mono"
              />
              <p className="text-xs text-[var(--text-faint)]">{form.everyMs ? `${(parseInt(form.everyMs) / 1000).toFixed(0)}s` : '—'}</p>
            </div>
          )}
          {form.scheduleKind === 'cron' && (
            <>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">Cron Expression</label>
                <input
                  type="text"
                  value={form.expr}
                  onChange={(e) => set('expr', e.target.value)}
                  placeholder="0 9 * * *"
                  className="w-full px-3 py-2 rounded-lg text-sm bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-[var(--accent)] font-mono"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">
                  Timezone <span className="font-normal text-[var(--text-faint)]">(optional, e.g. Asia/Shanghai)</span>
                </label>
                <input
                  type="text"
                  value={form.tz}
                  onChange={(e) => set('tz', e.target.value)}
                  placeholder="UTC"
                  className="w-full px-3 py-2 rounded-lg text-sm bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-[var(--accent)] font-mono"
                />
              </div>
            </>
          )}

          {/* Message / Prompt */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">
              Message / Prompt
            </label>
            <textarea
              value={form.message}
              onChange={(e) => set('message', e.target.value)}
              placeholder="What the agent should do when the job fires..."
              rows={3}
              className="w-full px-3 py-2 rounded-lg text-sm bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-[var(--accent)] resize-none"
            />
          </div>

          {error && (
            <div className="rounded-lg px-3 py-2 bg-[var(--accent-soft)] text-xs text-[var(--danger)]">{error}</div>
          )}
        </div>

        <div className="flex items-center justify-between px-5 py-3 border-t border-[var(--border-subtle)]">
          <span className="text-xs text-[var(--text-faint)]">
            {isEdit ? 'Update this cron job' : 'Jobs run in the MiQi runtime process'}
          </span>
          <div className="flex items-center gap-2">
            <button onClick={onClose} className="px-3 py-1.5 text-sm text-[var(--text-muted)] hover:text-[var(--text)] transition-colors">
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={saving}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-medium transition-colors disabled:opacity-50"
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
              {isEdit ? 'Save' : 'Create'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function CronPage() {
  const [jobs, setJobs] = useState<CronJob[]>([])
  const [runs, setRuns] = useState<CronRunEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [editJob, setEditJob] = useState<CronJob | null>(null)
  const [expandedJob, setExpandedJob] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [togglingId, setTogglingId] = useState<string | null>(null)
  const [runningId, setRunningId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [jr, rr] = await Promise.all([
        window.miqi.cron.list(),
        window.miqi.cron.runs(),
      ])
      setJobs(jr.jobs)
      setRuns(rr.runs)
      setActionError(null)
    } catch {
      // runtime not running
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleToggle = async (job: CronJob) => {
    setTogglingId(job.id)
    try {
      await window.miqi.cron.toggle(job.id, !job.enabled)
      await load()
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Toggle failed')
    } finally {
      setTogglingId(null)
    }
  }

  const handleRun = async (job: CronJob) => {
    setRunningId(job.id)
    try {
      await window.miqi.cron.run(job.id)
      await load()
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Run failed')
    } finally {
      setRunningId(null)
    }
  }

  const handleDelete = async (job: CronJob) => {
    setDeletingId(job.id)
    try {
      await window.miqi.cron.delete(job.id)
      await load()
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Delete failed')
    } finally {
      setDeletingId(null)
    }
  }

  const handleEdit = (job: CronJob) => {
    setEditJob(job)
  }

  return (
    <div className="flex flex-col h-full bg-[var(--background)]">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border-subtle)] bg-[var(--surface)] shrink-0">
        <div>
          <h1 className="text-base font-semibold text-[var(--text)]">Cron Studio</h1>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            {loading ? 'Loading...' : `${jobs.length} job${jobs.length !== 1 ? 's' : ''}, ${runs.length} recent runs`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="text-xs text-[var(--text-faint)] hover:text-[var(--text-muted)] transition-colors px-2 py-1 rounded">
            <RefreshCw size={14} />
          </button>
          <button
            onClick={() => { setShowCreate(true); setEditJob(null) }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white text-sm font-medium transition-colors"
          >
            <Plus size={14} />
            Create Job
          </button>
        </div>
      </div>

      {/* Error toast */}
      {actionError && (
        <div className="mx-6 mt-3 flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--accent-soft)] text-xs text-[var(--danger)]">
          <span className="flex-1">{actionError}</span>
          <button onClick={() => setActionError(null)} className="text-[var(--text-faint)] hover:text-[var(--text)]">
            <X size={12} />
          </button>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-6">
        {loading ? (
          <div className="flex items-center justify-center h-40 text-sm text-[var(--text-faint)]">
            <Loader2 size={16} className="animate-spin mr-2" /> Loading jobs...
          </div>
        ) : jobs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 gap-3 text-sm text-[var(--text-faint)]">
            <Clock size={28} />
            <span>No cron jobs yet — create your first scheduled task</span>
          </div>
        ) : (
          <>
            {/* Jobs table */}
            <div className="bg-[var(--surface)] border border-[var(--border-subtle)] rounded-xl overflow-hidden">
              <div className="flex items-center gap-3 px-5 py-2.5 border-b border-[var(--border-subtle)] bg-[var(--surface-muted)] text-xs font-semibold uppercase tracking-widest text-[var(--text-faint)]">
                <span className="flex-1">Job</span>
                <span className="w-[120px] shrink-0">Schedule</span>
                <span className="w-[140px] shrink-0">Next Run</span>
                <span className="w-[100px] shrink-0">Last Status</span>
                <span className="w-[140px] shrink-0">Actions</span>
              </div>
              <div className="divide-y divide-[var(--border-subtle)]">
                {jobs.map(job => (
                  <JobRow
                    key={job.id}
                    job={job}
                    isExpanded={expandedJob === job.id}
                    onToggleExpand={() => setExpandedJob(expandedJob === job.id ? null : job.id)}
                    onToggle={() => handleToggle(job)}
                    onRun={() => handleRun(job)}
                    onDelete={() => handleDelete(job)}
                    onEdit={() => handleEdit(job)}
                    toggling={togglingId === job.id}
                    running={runningId === job.id}
                    deleting={deletingId === job.id}
                  />
                ))}
              </div>
            </div>

            {/* Recent runs */}
            {runs.length > 0 && (
              <div className="bg-[var(--surface)] border border-[var(--border-subtle)] rounded-xl overflow-hidden">
                <div className="flex items-center px-5 py-2.5 border-b border-[var(--border-subtle)] bg-[var(--surface-muted)] text-xs font-semibold uppercase tracking-widest text-[var(--text-faint)]">
                  Recent Runs
                  <span className="ml-auto font-normal normal-case tracking-normal">{runs.length}</span>
                </div>
                <div className="divide-y divide-[var(--border-subtle)]">
                  {runs.slice(0, 20).map((r, i) => (
                    <div key={`${r.jobId}-${r.startedAtMs}-${i}`} className="flex items-center gap-3 px-5 py-2.5 hover:bg-[var(--surface-muted)] transition-colors">
                      <span className="flex-1 text-sm text-[var(--text)]">{r.jobName}</span>
                      <span className="w-[160px] shrink-0 text-xs text-[var(--text-faint)] font-mono">{formatMs(r.startedAtMs)}</span>
                      <span className={cn(
                        'w-[70px] shrink-0 text-xs font-medium',
                        r.status === 'ok' ? 'text-[var(--success)]' :
                        r.status === 'error' ? 'text-[var(--danger)]' :
                        'text-[var(--text-faint)]',
                      )}>
                        {r.status ?? '—'}
                      </span>
                      {r.error && (
                        <span className="w-[200px] shrink-0 text-xs text-[var(--danger)] truncate" title={r.error}>{r.error}</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Modals */}
      {showCreate && (
        <CreateEditModal onClose={() => setShowCreate(false)} onSaved={load} />
      )}
      {editJob && (
        <CreateEditModal job={editJob} onClose={() => setEditJob(null)} onSaved={load} />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Single job row
// ---------------------------------------------------------------------------

interface JobRowProps {
  job: CronJob
  isExpanded: boolean
  onToggleExpand: () => void
  onToggle: () => void
  onRun: () => void
  onDelete: () => void
  onEdit: () => void
  toggling: boolean
  running: boolean
  deleting: boolean
}

function JobRow({ job, isExpanded, onToggleExpand, onToggle, onRun, onDelete, onEdit, toggling, running, deleting }: JobRowProps) {
  const statusColor = job.enabled ? 'text-[var(--success)]' : 'text-[var(--text-faint)]'

  return (
    <>
      <div className="flex items-center gap-3 px-5 py-2.5 hover:bg-[var(--surface-muted)] transition-colors group">
        <button onClick={onToggleExpand} className="shrink-0 text-[var(--text-faint)] hover:text-[var(--text)] transition-colors">
          {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <button onClick={onEdit} className="flex-1 text-left min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-[var(--text)]">{job.name}</span>
            <span className={cn('text-xs', statusColor)}>{job.enabled ? 'Running' : 'Disabled'}</span>
          </div>
        </button>
        <span className="w-[120px] shrink-0 text-xs text-[var(--text-faint)] font-mono">{scheduleLabel(job)}</span>
        <span className="w-[140px] shrink-0 text-xs text-[var(--text-faint)] font-mono">
          {job.state.nextRunAtMs ? formatMs(job.state.nextRunAtMs) : '—'}
        </span>
        <span className={cn(
          'w-[100px] shrink-0 text-xs font-medium',
          job.state.lastStatus === 'ok' ? 'text-[var(--success)]' :
          job.state.lastStatus === 'error' ? 'text-[var(--danger)]' :
          'text-[var(--text-faint)]',
        )}>
          {job.state.lastStatus ?? '—'}
        </span>
        <div className="w-[140px] shrink-0 flex items-center gap-1">
          <button
            onClick={onToggle}
            disabled={toggling}
            title={job.enabled ? 'Disable' : 'Enable'}
            className="p-1.5 rounded-md text-[var(--text-faint)] hover:text-[var(--text)] hover:bg-[var(--surface-muted)] transition-colors disabled:opacity-40"
          >
            {toggling ? <Loader2 size={14} className="animate-spin" /> :
             job.enabled ? <Pause size={14} /> : <Play size={14} />}
          </button>
          <button
            onClick={onRun}
            disabled={running}
            title="Run now"
            className="p-1.5 rounded-md text-[var(--text-faint)] hover:text-[var(--accent)] hover:bg-[var(--accent-soft)] transition-colors disabled:opacity-40"
          >
            {running ? <Loader2 size={14} className="animate-spin" /> : <Power size={14} />}
          </button>
          <button
            onClick={onDelete}
            disabled={deleting}
            title="Delete"
            className="p-1.5 rounded-md text-[var(--text-faint)] hover:text-[var(--danger)] hover:bg-[var(--surface-muted)] transition-colors disabled:opacity-40"
          >
            {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
          </button>
        </div>
      </div>
      {/* Expanded detail */}
      {isExpanded && (
        <div className="px-10 py-3 bg-[var(--surface-muted)] text-xs text-[var(--text-muted)] flex flex-col gap-1 border-b border-[var(--border-subtle)]">
          <div><span className="text-[var(--text-faint)]">ID:</span> {job.id}</div>
          <div><span className="text-[var(--text-faint)]">Created:</span> {formatMs(job.createdAtMs)}</div>
          <div><span className="text-[var(--text-faint)]">Message:</span> {job.payload.message || '(empty)'}</div>
          {job.state.lastError && (
            <div className="text-[var(--danger)]">Last error: {job.state.lastError}</div>
          )}
        </div>
      )}
    </>
  )
}
