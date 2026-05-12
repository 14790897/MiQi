import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'

interface RestartRequiredContextValue {
  restartRequired: boolean
  markRestartRequired: () => void
  clearRestartRequired: () => void
}

const RestartRequiredContext = createContext<RestartRequiredContextValue>({
  restartRequired: false,
  markRestartRequired: () => {},
  clearRestartRequired: () => {},
})

export function RestartRequiredProvider({ children }: { children: ReactNode }) {
  const [restartRequired, setRestartRequired] = useState(false)

  const markRestartRequired = useCallback(() => setRestartRequired(true), [])
  const clearRestartRequired = useCallback(() => setRestartRequired(false), [])

  return (
    <RestartRequiredContext.Provider value={{ restartRequired, markRestartRequired, clearRestartRequired }}>
      {children}
    </RestartRequiredContext.Provider>
  )
}

export function useRestartRequired() {
  return useContext(RestartRequiredContext)
}
