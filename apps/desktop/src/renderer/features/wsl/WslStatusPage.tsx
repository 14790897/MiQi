import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Cpu,
  HardDrive,
  MemoryStick,
  Clock,
  RefreshCw,
  TriangleAlert,
  CheckCircle2,
  Activity,
} from 'lucide-react'
import { cn } from '../../lib/utils'
import type { WslStatsResult } from '../../../shared/ipc'

const REFRESH_MS = 3_000

// ─── Helpers ─────────────────────────────────────────────
//
function pctColor(p: number) {
  if (p > 85) return 'bg-[var(--danger)]'
  if (p > 60) return 'bg-[var(--warning)]'
  return 'bg-[var(--accent)]'
}

function pctColorText(p: number) {
  if (p > 85) return 'text-[var(--danger)]'
  if (p > 60) return 'text-[var(--warning)]'
  return 'text-[var(--accent)]'
}

function fmtUptime(s: number): string {
  if (s < 60) return `${Math.round(s)}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (s < 86400) return `${h}h ${m}m`
  const d = Math.floor(s / 86400)
  return `${d}d ${Math.floor((s % 86400) / 3600)}h`
}

function fmtMem(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`
  return `${mb} MB`
}

// ─── Circular progress ring ───────────────────────────────
//
function CircleRing({
  pct,
  size = 112,
}: {
  pct: number
  size?: number
}) {
  const r = (size - 10) / 2
  const c = 2 * Math.PI * r
  const offset = c * (1 - Math.min(pct, 100) / 100)
  const color =
    pct > 85 ? 'var(--danger)' : pct > 60 ? 'var(--warning)' : 'var(--accent)'

  return (
    <svg width={size} height={size} className="-rotate-90">
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="var(--surface-muted)"
        strokeWidth="9"
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth="9"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={offset}
        className="transition-all duration-700"
      />
    </svg>
  )
}

// ─── Main page ─────────────────────────────────────────────
//
const AISHADOW_PREFIX = 'AIShadow'

export default function WslStatusPage() {
  const [stats, setStats] = useState<WslStatsResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [distros, setDistros] = useState<string[]>([])
  const [selected, setSelected] = useState('')
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Fetch distro list (AIShadowSandbox first) ──────────
  const fetchDistros = useCallback(async () => {
    try {
      const r = await window.miqi.wsl.check()
      if (r?.installed && r.distros?.length > 0) {
        // Prioritize AIShadowSandbox: move it to index 0
        const sorted = [...r.distros]
        const idx = sorted.findIndex(
          (d: string) => d === AISHADOW_PREFIX || d.startsWith(AISHADOW_PREFIX)
        )
        if (idx > 0) {
          const [target] = sorted.splice(idx, 1)
          sorted.unshift(target)
        }
        setDistros(sorted)

        // Auto-select: AIShadowSandbox > defaultDistro
        if (!selected) {
          const auto =
            sorted.find((d: string) => d === AISHADOW_PREFIX || d.startsWith(AISHADOW_PREFIX)) ??
            r.defaultDistro
          if (auto) setSelected(auto)
        }
      }
    } catch { /* ignore */ }
  }, [selected])

  // ── Fetch stats ───────────────────────────────
  const fetchStats = useCallback(async () => {
    if (!selected) return
    setLoading(true)
    try {
      const r = await window.miqi.wsl.getStats(selected)
      if (r?.ok) {
        setStats(r)
        setError(null)
      } else {
        setError(r?.error ?? '无法获取 WSL 状态')
      }
    } catch (e: any) {
      setError(e?.message ?? 'IPC 调用失败')
    } finally {
      setLoading(false)
    }
  }, [selected])

  // Init: load distro list
  useEffect(() => { fetchDistros() }, [fetchDistros])

  // When selected distro changes
  useEffect(() => {
    if (selected) fetchStats()
  }, [selected, fetchStats])

  // Polling: refresh every REFRESH_MS
  useEffect(() => {
    if (!selected) return
    timerRef.current = setInterval(fetchStats, REFRESH_MS)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [selected, fetchStats])

  // ── Derived values ──────────────────────────────────
  const mem = stats?.memory
  const cpu = stats?.cpu
  const dsk = stats?.disk

  return (
    <div className="flex flex-col h-full bg-[var(--background)] overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border-subtle)] bg-[var(--surface)] shrink-0">
        <div>
          <h1 className="text-base font-semibold text-[var(--text)] flex items-center gap-2">
            <Cpu size={16} />
            WSL 状态监控
          </h1>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            {stats
              ? `${stats.distro}  · 已运行 ${fmtUptime(stats.uptime_sec)}`
              : '实时监控系统资源使用情况'}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {distros.length > 1 && (
            <select
              value={selected}
              onChange={e => setSelected(e.target.value)}
              className="text-xs px-3 py-1.5 rounded-lg bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)]"
            >
              <option value="">选择发行版</option>
              {distros.map(d => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
          )}
          <button
            onClick={fetchStats}
            disabled={loading || !selected}
            className="p-2 rounded-lg bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-[var(--accent)] hover:border-[var(--accent)] transition-colors disabled:opacity-40"
            title="刷新"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 p-6">
        {/* No distro selected */}
        {!selected && distros.length > 0 && (
          <div className="flex items-center justify-center h-40 text-sm text-[var(--text-faint)]">
            请在右上角选择 WSL 发行版
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 text-sm text-[var(--danger)] bg-[var(--danger)_10%] px-4 py-3 rounded-xl mb-6">
            <TriangleAlert size={14} />
            {error}
          </div>
        )}

        {/* Loading */}
        {loading && !stats && selected && (
          <div className="flex items-center gap-2 text-sm text-[var(--text-faint)] py-8 justify-center">
            <RefreshCw size={14} className="animate-spin" />
            正在获取 WSL 状态...
          </div>
        )}

        {/* Stats display */}
        {stats && (
          <div className="flex flex-col gap-6">
            {/* Circular rings row */}
            <div className="flex flex-wrap gap-8 justify-center">
              {/* Memory ring */}
              {mem && (
                <div className="flex flex-col items-center gap-3">
                  <div className="relative">
                    <CircleRing pct={mem.used_pct} size={112} />
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <span className={`text-xl font-bold tabular-nums ${pctColorText(mem.used_pct)}`}>
                        {mem.used_pct}%
                      </span>
                      <span className="text-[10px] text-[var(--text-faint)]">内存</span>
                    </div>
                  </div>
                  <div className="text-center">
                    <div className="text-xs text-[var(--text-muted)]">内存使用率</div>
                    <div className="text-xs font-mono text-[var(--text)]">
                      {fmtMem(mem.used_mb)} / {fmtMem(mem.total_mb)}
                    </div>
                  </div>
                </div>
              )}

              {/* CPU ring */}
              {cpu && (
                <div className="flex flex-col items-center gap-3">
                  <div className="relative">
                    <CircleRing pct={cpu.usage_pct} size={112} />
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <span className={`text-xl font-bold tabular-nums ${pctColorText(cpu.usage_pct)}`}>
                        {cpu.usage_pct}%
                      </span>
                      <span className="text-[10px] text-[var(--text-faint)]">CPU</span>
                    </div>
                  </div>
                  <div className="text-center">
                    <div className="text-xs text-[var(--text-muted)]">CPU 使用率</div>
                    <div className="text-xs font-mono text-[var(--text)]">
                      {cpu.cores} 核
                    </div>
                  </div>
                </div>
              )}

              {/* Disk ring */}
              {dsk && (
                <div className="flex flex-col items-center gap-3">
                  <div className="relative">
                    <CircleRing pct={dsk.used_pct} size={112} />
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <span className={`text-xl font-bold tabular-nums ${pctColorText(dsk.used_pct)}`}>
                        {dsk.used_pct}%
                      </span>
                      <span className="text-[10px] text-[var(--text-faint)]">磁盘</span>
                    </div>
                  </div>
                  <div className="text-center">
                    <div className="text-xs text-[var(--text-muted)]">磁盘使用率 (/)</div>
                    <div className="text-xs font-mono text-[var(--text)]">
                      {dsk.used_gb} / {dsk.total_gb} GB
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Detail table */}
            <div className="bg-[var(--surface)] border border-[var(--border-subtle)] rounded-2xl overflow-hidden">
              <div className="px-5 py-3 border-b border-[var(--border-subtle)] bg-[var(--surface-muted)]">
                <span className="text-xs font-semibold text-[var(--text)]">详细信息</span>
              </div>
              <table className="w-full text-sm">
                <tbody>
                  {[
                    ['发行版', stats.distro],
                    ['状态', <span className="flex items-center gap-1 text-[var(--accent)]"><CheckCircle2 size={11} /> 运行中</span>],
                    ['运行时间', fmtUptime(stats.uptime_sec)],
                    ['CPU 核心数', `${cpu?.cores ?? 0} 核`],
                    ['内存总量', fmtMem(mem?.total_mb ?? 0)],
                    ['内存已用', `${fmtMem(mem?.used_mb ?? 0)} (${mem?.used_pct ?? 0}%)`],
                    ['内存可用', fmtMem(mem?.free_mb ?? 0)],
                    ['磁盘总量', `${dsk?.total_gb ?? 0} GB`],
                    ['磁盘已用', `${dsk?.used_gb ?? 0} GB (${dsk?.used_pct ?? 0}%)`],
                    ['磁盘可用', `${dsk?.free_gb ?? 0} GB`],
                  ].map(([k, v], i) => (
                    <tr key={k} className={i % 2 === 0 ? 'bg-[var(--surface)]' : 'bg-[var(--surface-muted)]'}>
                      <td className="px-5 py-2.5 text-xs text-[var(--text-muted)] w-40">{k}</td>
                      <td className="px-5 py-2.5 text-xs text-[var(--text)] font-mono">{v}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
