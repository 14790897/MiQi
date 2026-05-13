import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import type { RuntimeState, RuntimeStatus } from '../../shared/ipc'

const hasApi = typeof window !== 'undefined' && !!(window as any).miqi?.runtime

interface RuntimeContextValue {
  status: RuntimeStatus
  logs: string[]
  start: () => Promise<void>
  stop: () => Promise<void>
  refreshStatus: () => Promise<void>
  refreshLogs: () => Promise<void>
}

const RuntimeContext = createContext<RuntimeContextValue | null>(null)

export function RuntimeProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<RuntimeStatus>(
    hasApi
      ? { state: 'stopped', configured: false }
      : { state: 'error', configured: false, error: 'Preload API unavailable' },
  )
  const [logs, setLogs] = useState<string[]>([])

  const refreshStatus = useCallback(async () => {
    if (!hasApi) return
    try {
      const s = await window.miqi.runtime.status()
      setStatus(s)
    } catch {
      // Bridge not available yet
    }
  }, [])

  const refreshLogs = useCallback(async () => {
    if (!hasApi) return
    try {
      const l = await window.miqi.runtime.logs()
      setLogs(l)
    } catch {
      // Bridge not available yet
    }
  }, [])

  const start = useCallback(async () => {
    if (!hasApi) return
    const s = await window.miqi.runtime.start()
    setStatus(s)
  }, [])

  const stop = useCallback(async () => {
    if (!hasApi) return
    const s = await window.miqi.runtime.stop()
    setStatus(s)
  }, [])

  useEffect(() => {
    if (!hasApi) return
    refreshStatus()
    const unsubState = window.miqi.runtime.onStateChange((s) => setStatus(s))
    const unsubLog = window.miqi.runtime.onLog((msg) => setLogs((prev) => [...prev.slice(-499), msg]))
    return () => { unsubState(); unsubLog() }
  }, [refreshStatus])

  return (
    <RuntimeContext.Provider value={{ status, logs, start, stop, refreshStatus, refreshLogs }}>
      {children}
    </RuntimeContext.Provider>
  )
}

export function useRuntime(): RuntimeContextValue {
  const ctx = useContext(RuntimeContext)
  if (!ctx) throw new Error('useRuntime must be used within RuntimeProvider')
  return ctx
}
