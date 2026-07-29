import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Cpu,
  HardDrive,
  MemoryStick,
  Clock,
  RefreshCw,
  TriangleAlert,
  CheckCircle2,
  Activity,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import type { WslStatsResult } from '../../../shared/ipc';

const REFRESH_MS = 3_000;

function pctColor(p: number) {
  if (p > 85) return 'bg-[var(--danger)]';
  if (p > 60) return 'bg-[var(--warning)]';
  return 'bg-[var(--accent)]';
}

function pctColorText(p: number) {
  if (p > 85) return 'text-[var(--danger)]';
  if (p > 60) return 'text-[var(--warning)]';
  return 'text-[var(--accent)]';
}

function fmtUptime(s: number): string {
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (s < 86400) return `${h}h ${m}m`;
  const d = Math.floor(s / 86400);
  return `${d}d ${Math.floor((s % 86400) / 3600)}h`;
}

function fmtMem(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb} MB`;
}

function CircleRing({ pct, size = 112 }: { pct: number; size?: number }) {
  const r = (size - 10) / 2;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - Math.min(pct, 100) / 100);
  const color = pct > 85 ? 'var(--danger)' : pct > 60 ? 'var(--warning)' : 'var(--accent)';

  return (
    <svg width={size} height={size} className="-rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-muted)" strokeWidth="9" />
      <circle
        cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="9"
        strokeLinecap="round" strokeDasharray={c} strokeDashoffset={offset}
        className="transition-all duration-700"
      />
    </svg>
  );
}

const AISHADOW_PREFIX = 'AIShadow';

export default function WslStatusPage() {
  const [stats, setStats] = useState<WslStatsResult | null>(null);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [distros, setDistros] = useState<string[]>([]);
  const [selected, setSelected] = useState('');
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const initialFetch = useRef(false);

  const fetchDistros = useCallback(async () => {
    try {
      const r = await window.miqi.wsl.check();
      if (r?.installed && r.distros?.length > 0) {
        const sorted = [...r.distros];
        const idx = sorted.findIndex((d: string) => d === AISHADOW_PREFIX || d.startsWith(AISHADOW_PREFIX));
        if (idx > 0) { const [t] = sorted.splice(idx, 1); sorted.unshift(t); }
        setDistros(sorted);

        if (!initialFetch.current) {
          const auto = sorted.find((d: string) => d === AISHADOW_PREFIX || d.startsWith(AISHADOW_PREFIX)) ?? r.defaultDistro;
          if (auto) setSelected(auto);
          initialFetch.current = true;
        }
      }
    } catch { /* ignore */ }
  }, []);

  const fetchStats = useCallback(async (silent = false) => {
    if (!selected) return;
    if (!silent) setFetching(true);
    try {
      const r = await window.miqi.wsl.getStats(selected);
      if (r?.ok) { setStats(r); setError(null); }
      else { setError(r?.error ?? '无法获取 WSL 状态'); }
    } catch (e: any) {
      setError(e?.message ?? 'IPC 调用失败');
    } finally {
      setFetching(false);
    }
  }, [selected]);

  useEffect(() => { fetchDistros(); }, [fetchDistros]);
  useEffect(() => {
    if (selected) {
      setStats(null);
      fetchStats();
    }
  }, [selected]); // eslint-disable-line

  useEffect(() => {
    if (!selected) return;
    timerRef.current = setInterval(() => fetchStats(true), REFRESH_MS);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [selected, fetchStats]);

  const mem = stats?.memory;
  const cpu = stats?.cpu;
  const dsk = stats?.disk;

  return (
    <div className="flex flex-col h-full bg-[var(--background)] overflow-y-auto">
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border-subtle)] bg-[var(--surface)] shrink-0">
        <div>
          <h1 className="text-base font-semibold text-[var(--text)] flex items-center gap-2">
            <Cpu size={16} /> WSL 状态监控
          </h1>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            {stats
              ? `${stats.distro} · 已运行 ${fmtUptime(stats.uptime_sec)}`
              : '实时监控系统资源使用情况'}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {distros.length === 0 ? (
            <span className="text-xs text-[var(--text-faint)]">加载发行版列表...</span>
          ) : distros.length > 1 ? (
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              className="text-xs px-3 py-1.5 rounded-lg bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text)]"
            >
              {distros.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          ) : distros.length === 1 ? (
            <span className="text-xs text-[var(--text-muted)]">{distros[0]}</span>
          ) : (
            <span className="text-xs text-[var(--text-faint)]">未检测到 WSL 发行版</span>
          )}
          <button
            onClick={() => fetchStats()}
            disabled={fetching || !selected}
            className="p-2 rounded-lg bg-[var(--surface-muted)] border border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-[var(--accent)] hover:border-[var(--accent)] transition-colors disabled:opacity-40"
            title="刷新"
          >
            <RefreshCw size={14} className={fetching ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      <div className="flex-1 p-6">
        {error && (
          <div className="flex items-center gap-2 text-sm text-[var(--danger)] bg-[var(--danger)]/10 px-4 py-3 rounded-xl mb-6">
            <TriangleAlert size={14} /> {error}
          </div>
        )}

        {/* Show skeleton/empty state while fetching, never block */}
        {!stats ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            {fetching ? (
              <>
                <RefreshCw size={20} className="animate-spin" style={{ color: 'var(--text-faint)' }} />
                <p className="text-sm text-[var(--text-muted)]">正在获取 {selected || 'WSL'} 状态...</p>
                <p className="text-xs text-[var(--text-faint)]">数据加载中，您可以切换发行版</p>
              </>
            ) : selected ? (
              <>
                <Activity size={20} style={{ color: 'var(--text-faint)' }} />
                <p className="text-sm text-[var(--text-muted)]">暂无数据</p>
                <p className="text-xs text-[var(--text-faint)]">点击刷新按钮获取状态</p>
              </>
            ) : distros.length > 0 ? (
              <>
                <Cpu size={20} style={{ color: 'var(--text-faint)' }} />
                <p className="text-sm text-[var(--text-muted)]">请选择 WSL 发行版</p>
                <p className="text-xs text-[var(--text-faint)]">在上方下拉菜单中选择发行版以查看状态</p>
              </>
            ) : (
              <>
                <Cpu size={20} style={{ color: 'var(--text-faint)' }} />
                <p className="text-sm text-[var(--text-muted)]">未检测到 WSL 发行版</p>
                <p className="text-xs text-[var(--text-faint)]">请确保已安装 WSL2</p>
              </>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            <div className="flex flex-wrap gap-8 justify-center">
              {mem && (
                <div className="flex flex-col items-center gap-3">
                  <div className="relative">
                    <CircleRing pct={mem.used_pct} size={112} />
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <span className={`text-xl font-bold tabular-nums ${pctColorText(mem.used_pct)}`}>{mem.used_pct}%</span>
                      <span className="text-[10px] text-[var(--text-faint)]">内存</span>
                    </div>
                  </div>
                  <div className="text-center">
                    <div className="text-xs text-[var(--text-muted)]">内存使用率</div>
                    <div className="text-xs font-mono text-[var(--text)]">{fmtMem(mem.used_mb)} / {fmtMem(mem.total_mb)}</div>
                  </div>
                </div>
              )}
              {cpu && (
                <div className="flex flex-col items-center gap-3">
                  <div className="relative">
                    <CircleRing pct={cpu.usage_pct} size={112} />
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <span className={`text-xl font-bold tabular-nums ${pctColorText(cpu.usage_pct)}`}>{cpu.usage_pct}%</span>
                      <span className="text-[10px] text-[var(--text-faint)]">CPU</span>
                    </div>
                  </div>
                  <div className="text-center">
                    <div className="text-xs text-[var(--text-muted)]">CPU 使用率</div>
                    <div className="text-xs font-mono text-[var(--text)]">{cpu.cores} 核</div>
                  </div>
                </div>
              )}
              {dsk && (
                <div className="flex flex-col items-center gap-3">
                  <div className="relative">
                    <CircleRing pct={dsk.used_pct} size={112} />
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <span className={`text-xl font-bold tabular-nums ${pctColorText(dsk.used_pct)}`}>{dsk.used_pct}%</span>
                      <span className="text-[10px] text-[var(--text-faint)]">磁盘</span>
                    </div>
                  </div>
                  <div className="text-center">
                    <div className="text-xs text-[var(--text-muted)]">磁盘使用率 (/)</div>
                    <div className="text-xs font-mono text-[var(--text)]">{dsk.used_gb} / {dsk.total_gb} GB</div>
                  </div>
                </div>
              )}
            </div>

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
                    <tr key={String(k)} className={i % 2 === 0 ? 'bg-[var(--surface)]' : 'bg-[var(--surface-muted)]'}>
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
  );
}
