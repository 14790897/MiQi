import { useState, useEffect } from 'react'
import { RuntimeProvider, useRuntime } from './contexts/RuntimeContext'
import { TooltipProvider } from './components/ui/Tooltip'
import { Sidebar } from './components/Sidebar'
import { StatusBar } from './components/StatusBar'
import { SetupWizard } from './features/setup/SetupWizard'
import { ChatConsole } from './features/chat/ChatConsole'
import { SessionExplorer } from './features/sessions/SessionExplorer'
import { SettingsPage } from './features/settings/SettingsPage'
import { ProvidersPage } from './features/providers/ProvidersPage'
import { ChannelsPage } from './features/channels/ChannelsPage'
import { ApprovalProvider } from './contexts/ApprovalContext'
import { ApprovalModal } from './features/approvals/ApprovalModal'
import { ApprovalsPage } from './features/approvals/ApprovalsPage'

type NavId = 'chat' | 'sessions' | 'providers' | 'channels' | 'approvals' | 'settings'

function AppShell() {
  const { status } = useRuntime()
  const [activeNav, setActiveNav] = useState<NavId>('chat')
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null) // null = checking

  // Check if setup is needed on mount
  useEffect(() => {
    // Preload injection verification: window.miqi must be available.
    // Logs to devtools console so operator can confirm the preload bridge
    // is intact without expanding the API surface.
    if (typeof window.miqi === 'object' && window.miqi !== null) {
      const apiKeys = Object.keys(window.miqi).join(', ')
      console.log(`[MiQi] preload OK — exposed namespaces: ${apiKeys}`)
    } else {
      console.error('[MiQi] preload MISSING — window.miqi is undefined. ' +
        'Check that contextBridge.exposeInMainWorld executed.')
    }

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
      <ApprovalProvider>
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
              {activeNav === 'providers' && <ProvidersPage />}
              {activeNav === 'channels' && <ChannelsPage />}
              {activeNav === 'approvals' && <ApprovalsPage />}
              {activeNav === 'settings' && <SettingsPage />}
            </main>
          </div>

          <StatusBar />
        </div>
        <ApprovalModal />
      </ApprovalProvider>
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
