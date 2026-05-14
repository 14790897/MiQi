import { createContext, useContext, useState, useEffect, useRef, type ReactNode } from 'react'
import type { ApprovalRequest } from '../../shared/ipc'

interface ApprovalContextValue {
  pending: ApprovalRequest | null
  resolve: (decision: 'once' | 'session' | 'always' | 'deny') => Promise<void>
  timeout: number
  remainingSeconds: number | null
}

const ApprovalContext = createContext<ApprovalContextValue>({
  pending: null,
  resolve: async () => {},
  timeout: 60,
  remainingSeconds: null,
})

export function ApprovalProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<ApprovalRequest | null>(null)
  const [timeout, setTimeout_] = useState(60)
  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(null)
  const arrivedAtRef = useRef<number>(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Load timeout value once
  useEffect(() => {
    if (!(window as any).miqi?.approvals) return
    window.miqi.approvals.list().then((r: any) => {
      if (r?.timeout) setTimeout_(r.timeout)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!(window as any).miqi?.approvals) return
    const unsubReq = window.miqi.approvals.onRequest((data: ApprovalRequest) => {
      arrivedAtRef.current = Date.now()
      setPending(data)
      setRemainingSeconds(timeout)

      // Start countdown
      if (timerRef.current) clearInterval(timerRef.current)
      timerRef.current = setInterval(() => {
        const elapsed = (Date.now() - arrivedAtRef.current) / 1000
        const remaining = Math.max(0, Math.ceil(timeout - elapsed))
        setRemainingSeconds(remaining)
        if (remaining <= 0) {
          if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
        }
      }, 200)
    })
    const unsubClear = window.miqi.approvals.onCleared(() => {
      setPending(null)
      setRemainingSeconds(null)
      if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
    })
    return () => {
      unsubReq()
      unsubClear()
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [timeout])

  const resolve = async (decision: 'once' | 'session' | 'always' | 'deny') => {
    if (!pending) return
    const id = pending.approval_id
    setPending(null)
    setRemainingSeconds(null)
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
    try {
      await window.miqi.approvals.resolve(id, decision)
    } catch {
      // best-effort
    }
  }

  return (
    <ApprovalContext.Provider value={{ pending, resolve, timeout, remainingSeconds }}>
      {children}
    </ApprovalContext.Provider>
  )
}

export function useApproval() {
  return useContext(ApprovalContext)
}
