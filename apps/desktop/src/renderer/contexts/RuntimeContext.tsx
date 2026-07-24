import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import type { RuntimeStatus } from '../../shared/ipc';
import { sanitizeUiMessage } from '../lib/sanitizeUiMessage';

interface RuntimeLogEntry {
  id: number;
  timestamp: string;
  level: string;
  source: string;
  message: string;
  sessionKey?: string;
}

const hasApi = typeof window !== 'undefined' && !!(window as any).miqi?.runtime;

// Monotonically increasing counter for stable log entry ids.
let _nextLogId = 0;

/** Strip ANSI escape codes (color/bold/reset) that may leak from Python loguru output. */
function stripAnsi(text: string): string {
  return text.replace(/\x1b\[[0-9;]*m/g, '');
}

/** Parse a formatted log line into a RuntimeLogEntry, falling back to sensible defaults. */
function parseLogLine(msg: string): Omit<RuntimeLogEntry, 'id'> {
  // Strip ANSI escape codes as a safety net — the bridge already strips them,
  // but file logs written before the fix may still contain them.
  const clean = stripAnsi(msg);

  // Three-bracket format: [timestamp] [level] [source] message
  const m = clean.match(/^\[([^\]]+)\]\s*\[([^\]]+)\]\s*\[([^\]]+)\]\s*(.*)/s);
  if (m) {
    return { timestamp: m[1], level: m[2], source: m[3], message: m[4] };
  }
  // Single-bracket bridge format: [timestamp] message (no level/source)
  const m1 = clean.match(/^\[([^\]]+)\]\s*(.*)/s);
  if (m1) {
    return {
      timestamp: m1[1],
      level: clean.includes('ERROR') ? 'ERROR' : clean.includes('WARN') ? 'WARN' : 'INFO',
      source: 'bridge',
      message: m1[2],
    };
  }
  return {
    timestamp: new Date().toISOString(),
    level: clean.includes('ERROR') ? 'ERROR' : clean.includes('WARN') ? 'WARN' : 'INFO',
    source: 'bridge',
    message: clean,
  };
}

interface RuntimeContextValue {
  status: RuntimeStatus;
  logs: string[];
  entries: RuntimeLogEntry[];
  lastError: string | null;
  start: () => Promise<RuntimeStatus | undefined>;
  stop: () => Promise<RuntimeStatus | undefined>;
  refreshStatus: () => Promise<void>;
  refreshLogs: () => Promise<void>;
}

const RuntimeContext = createContext<RuntimeContextValue | null>(null);

export function RuntimeProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<RuntimeStatus>(
    hasApi
      ? { state: 'stopped', configured: false }
      : { state: 'error', configured: false, error: 'Preload API 不可用' }
  );
  const [logs, setLogs] = useState<string[]>([]);
  const [entries, setEntries] = useState<RuntimeLogEntry[]>([]);
  const [lastError, setLastError] = useState<string | null>(null);

  const refreshStatus = useCallback(async () => {
    if (!hasApi) return;
    try {
      const s = await window.miqi.runtime.status();
      setStatus(s);
      setLastError(null);
    } catch (e: any) {
      const safe = sanitizeUiMessage(e?.message ?? 'Bridge status fetch failed');
      setStatus((prev) => ({
        ...prev,
        state: 'error' as const,
        error: safe,
      }));
      setLastError(safe);
    }
  }, []);

  const refreshLogs = useCallback(async () => {
    if (!hasApi) return;
    try {
      const bridgeLogs = await window.miqi.runtime.logs();
      setLogs(bridgeLogs);

      // Fetch persisted file logs (renderer/main/backend) and merge with bridge logs.
      let fileLines: string[] = [];
      try {
        fileLines = (await window.miqi.runtime.fileLogs?.()) ?? [];
      } catch {
        /* file logs may not be available */
      }

      const allLines = [...bridgeLogs, ...fileLines];
      setEntries(
        allLines.map((msg: string) => ({
          id: _nextLogId++,
          ...parseLogLine(msg),
        }))
      );
    } catch (e: any) {
      setLastError(sanitizeUiMessage(e?.message ?? 'Failed to fetch runtime logs'));
    }
  }, []);

  const start = useCallback(async () => {
    if (!hasApi) return;
    const s = await window.miqi.runtime.start();
    setStatus(s);
    return s;
  }, []);

  const stop = useCallback(async () => {
    if (!hasApi) return;
    const s = await window.miqi.runtime.stop();
    setStatus(s);
    return s;
  }, []);

  useEffect(() => {
    if (!hasApi) return;
    refreshStatus();
    refreshLogs(); // fetch initial log entries (bridge + backend files)
    const unsubState = window.miqi.runtime.onStateChange((s) => setStatus(s));
    const unsubLog = window.miqi.runtime.onLog((msg) => {
      setLogs((prev) => [...prev.slice(-499), msg]);
      setEntries((prev) => [
        ...prev.slice(-499),
        {
          id: _nextLogId++,
          ...parseLogLine(msg),
        },
      ]);
    });

    // Capture uncaught synchronous errors in the renderer (JS errors only, not resource load failures)
    const onError = (event: ErrorEvent) => {
      // Filter out resource load errors (no .error property, or target is not window)
      if (!event.error && event.target !== window) return;
      const msg =
        event.error instanceof Error
          ? `Uncaught error: ${event.error.message}\n${event.error.stack ?? ''}`
          : `Uncaught error: ${event.message} at ${event.filename}:${event.lineno}`;
      window.miqi.runtime.reportRendererLog?.({
        level: 'ERROR',
        message: msg,
        source: 'renderer',
      });
    };
    window.addEventListener('error', onError);

    // Capture unhandled Promise rejections in the renderer
    const onUnhandledRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      const msg =
        reason instanceof Error
          ? `Unhandled rejection: ${reason.message}\n${reason.stack ?? ''}`
          : `Unhandled rejection: ${String(reason)}`;
      window.miqi.runtime.reportRendererLog?.({
        level: 'ERROR',
        message: msg,
        source: 'renderer',
      });
    };
    window.addEventListener('unhandledrejection', onUnhandledRejection);

    window.miqi.runtime.reportRendererLog?.({
      level: 'INFO',
      message: 'Runtime context initialized',
      source: 'renderer',
    });

    // Record navigation timing metrics after initial render
    const recordPerf = () => {
      try {
        const navEntries = performance.getEntriesByType(
          'navigation'
        ) as PerformanceNavigationTiming[];
        if (navEntries.length > 0) {
          const nav = navEntries[0];
          const metrics = [
            `domInteractive=${Math.round(nav.domInteractive)}ms`,
            `domComplete=${Math.round(nav.domComplete)}ms`,
            `loadComplete=${Math.round(nav.loadEventEnd)}ms`,
            `firstPaint=${Math.round(nav.responseEnd - nav.fetchStart)}ms`,
          ].join(', ');
          window.miqi.runtime.reportRendererLog?.({
            level: 'INFO',
            message: `首屏渲染指标: ${metrics}`,
            source: 'renderer',
          });
        }
      } catch {
        /* Performance API not available */
      }
    };
    // Delay slightly to let loadEventEnd populate
    const perfTimer = setTimeout(recordPerf, 1000);
    return () => {
      unsubState();
      unsubLog();
      clearTimeout(perfTimer);
      window.removeEventListener('error', onError);
      window.removeEventListener('unhandledrejection', onUnhandledRejection);
    };
  }, [refreshStatus, refreshLogs]);

  return (
    <RuntimeContext.Provider
      value={{ status, logs, entries, start, stop, refreshStatus, refreshLogs, lastError }}
    >
      {children}
    </RuntimeContext.Provider>
  );
}

export function useRuntime(): RuntimeContextValue {
  const ctx = useContext(RuntimeContext);
  if (!ctx) throw new Error('useRuntime must be used within RuntimeProvider');
  return ctx;
}
