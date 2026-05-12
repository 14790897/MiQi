import { useState, useEffect } from 'react'
import { RuntimeProvider, useRuntime } from './contexts/RuntimeContext'
import { TooltipProvider } from './components/ui/Tooltip'
import { Sidebar } from './components/Sidebar'
import { StatusBar } from './components/StatusBar'
import { SetupWizard } from './features/setup/SetupWizard'
import { ChatConsole } from './features/chat/ChatConsole'
import { SessionExplorer } from './features/sessions/SessionExplorer'
import { SettingsPage } from './features/settings/SettingsPage'

type NavId = 'chat' | 'sessions' | 'settings'

function AppShell() {
  const { status } = useRuntime()
  const [activeNav, setActiveNav] = useState<NavId>('chat')
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null) // null = checking

  // Check if setup is needed on mount
  useEffect(() => {
    const check = async () => {
      try {
        const result = await window.miqi.python.check()
        setNeedsSetup(!result.config_exists)
      } catch {
        setNeedsSetup(true)
      }
    }
    check()
  }, [])

  // Handle setup completion
  const handleSetupComplete = () => {
    setNeedsSetup(false)
    setActiveNav('chat')
  }

  // Loading state
  if (needsSetup === null) {
    return (
      <div className="flex items-center justify-center h-screen bg-[var(--background)]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[var(--accent)] flex items-center justify-center text-white text-lg font-bold">
            M
          </div>
          <div className="text-sm text-[var(--text-muted)]">Loading MiQi Desktop...</div>
        </div>
      </div>
    )
  }

  // Setup wizard
  if (needsSetup) {
    return (
      <TooltipProvider>
        <SetupWizard onComplete={handleSetupComplete} />
      </TooltipProvider>
    )
  }

  // Main app
  return (
    <TooltipProvider>
      <div className="flex flex-col h-screen bg-[var(--background)]">
        <div className="flex flex-1 overflow-hidden">
          <Sidebar activeNav={activeNav} onNavChange={(id) => setActiveNav(id as NavId)} />

          <main className="flex-1 flex flex-col overflow-hidden bg-[var(--background)]">
            {activeNav === 'chat' && <ChatConsole />}
            {activeNav === 'sessions' && (
              <SessionExplorer onOpenSession={(key) => {
                // Navigate to chat with this session — for M1, just switch to chat
                setActiveNav('chat')
              }} />
            )}
            {activeNav === 'settings' && <SettingsPage />}
          </main>
        </div>

        <StatusBar />
      </div>
    </TooltipProvider>
  )
}

export default function App() {
  return (
    <RuntimeProvider>
      <AppShell />
    </RuntimeProvider>
  )
}
