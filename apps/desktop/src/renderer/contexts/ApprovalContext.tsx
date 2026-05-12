import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'
import type { ApprovalRequest } from '../../shared/ipc'

interface ApprovalContextValue {
  pending: ApprovalRequest | null
  resolve: (decision: 'once' | 'session' | 'always' | 'deny') => Promise<void>
}

const ApprovalContext = createContext<ApprovalContextValue>({
  pending: null,
  resolve: async () => {},
})

export function ApprovalProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<ApprovalRequest | null>(null)

  useEffect(() => {
    const unsub = window.miqi.approvals.onRequest((data) => {
      setPending(data)
    })
    return unsub
  }, [])

  const resolve = async (decision: 'once' | 'session' | 'always' | 'deny') => {
    if (!pending) return
    const id = pending.approval_id
    setPending(null)
    try {
      await window.miqi.approvals.resolve(id, decision)
    } catch {
      // best-effort
    }
  }

  return (
    <ApprovalContext.Provider value={{ pending, resolve }}>
      {children}
    </ApprovalContext.Provider>
  )
}

export function useApproval() {
  return useContext(ApprovalContext)
}
