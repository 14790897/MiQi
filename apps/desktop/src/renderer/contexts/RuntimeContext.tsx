import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react'
import type { RuntimeStatus } from '../../shared/ipc'

const hasApi = typeof window !== 'undefined' && !!(window as any).miqi?.runtime

interface RuntimeContextValue {
  status: RuntimeStatus
  logs: string[]
  start: () => Promise<RuntimeStatus | undefined>
  stop: () => Promise<RuntimeStatus | undefined>
  refreshStatus: () => Promise<void>
  refreshLogs: () => Promise<void>
}

const RuntimeContext = createContext<RuntimeContextValue | null>(null)

export function RuntimeProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<RuntimeStatus>(
    hasApi
      ? { state: 'stopped', configured: false }
      : { state: 'error', configured: false, error: 'Preload API 不可用' },
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
    return s
  }, [])

  const stop = useCallback(async () => {
    if (!hasApi) return
    const s = await window.miqi.runtime.stop()
    setStatus(s)
    return s
  }, [])

  useEffect(() => {
    if (!hasApi) return
    refreshStatus()
    const unsubState = window.miqi.runtime.onStateChange((s) => setStatus(s))
    const unsubLog = window.miqi.runtime.onLog((msg) => {
      console.log(`[renderer] Received log: ${msg}`)
      setLogs((prev) => [...prev.slice(-499), msg])
    })
    return () => {
      unsubState()
      unsubLog()
    }
  }, [refreshStatus])

  return (
    <RuntimeContext.Provider
      value={{ status, logs, start, stop, refreshStatus, refreshLogs }}
    >
      {children}
    </RuntimeContext.Provider>
  )
}

export function useRuntime(): RuntimeContextValue {
  const ctx = useContext(RuntimeContext)
  if (!ctx) throw new Error('useRuntime must be used within RuntimeProvider')
  return ctx
}
