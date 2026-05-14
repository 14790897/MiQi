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
import { RestartRequiredProvider } from './contexts/RestartRequiredContext'
import { ApprovalModal } from './features/approvals/ApprovalModal'
import { ApprovalsPage } from './features/approvals/ApprovalsPage'
import { CronPage } from './features/cron/CronPage'
import { MemoryPage } from './features/memory/MemoryPage'
import { SkillsPage } from './features/skills/SkillsPage'
import { WorkspacePage } from './features/workspace/WorkspacePage'

type NavId = 'chat' | 'sessions' | 'providers' | 'channels' | 'approvals' | 'cron' | 'memory' | 'skills' | 'workspace' | 'settings'

const PRELOAD_OK = typeof window !== 'undefined' && !!(window as any).miqi

function AppShell() {
  const { status } = useRuntime()
  const [activeNav, setActiveNav] = useState<NavId>('chat')
  const [sessionKey, setSessionKey] = useState('desktop:default')
  const [sessionRefreshKey, setSessionRefreshKey] = useState(0)
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null) // null = checking

  // Check if setup is needed on mount
  useEffect(() => {
    // Preload injection verification: window.miqi must be available.
    // Logs to devtools console so operator can confirm the preload bridge
    // is intact without expanding the API surface.
    if (PRELOAD_OK) {
      const apiKeys = Object.keys(window.miqi).join(', ')
      console.log(`[MiQi] preload OK — exposed namespaces: ${apiKeys}`)
    } else {
      console.error('[MiQi] preload MISSING — window.miqi is undefined. ' +
        'Check that contextBridge.exposeInMainWorld executed.')
      setNeedsSetup(false) // not a setup issue — preload is broken
      return
    }

    const check = async () => {
      try {
        const result = await window.miqi.python.check()
        const skipSetup = result.config_exists
        setNeedsSetup(!skipSetup)
        if (skipSetup) {
          // Config already exists — auto-start bridge
          window.miqi.runtime.start().catch(() => {})
        }
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
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#f7f3ea', fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
          <div style={{ width: '40px', height: '40px', borderRadius: '10px', background: '#c96442', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', fontSize: '18px', fontWeight: 700 }}>
            M
          </div>
          <div style={{ fontSize: '13px', color: '#766b5f' }}>正在加载 MiQi…</div>
        </div>
      </div>
    )
  }

  // Preload is entirely absent — show a visible error panel, not a white screen
  if (!PRELOAD_OK) {
    return (
      <div className="flex items-center justify-center h-screen bg-[var(--background)]">
        <div className="flex flex-col items-center gap-4 max-w-sm text-center px-6">
          <div className="w-12 h-12 rounded-xl bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
            <span className="text-red-600 dark:text-red-400 text-xl font-bold">!</span>
          </div>
          <div>
            <h2 className="text-base font-semibold text-[var(--text)] mb-1">预加载桥接不可用</h2>
            <p className="text-sm text-[var(--text-muted)]">
              应用预加载脚本注入失败。<br />
              请重启应用。如问题持续，请检查预加载脚本路径或重新安装。
            </p>
          </div>
          <div className="text-xs text-[var(--text-faint)]">
            按 Ctrl+Shift+I 打开 DevTools 查看错误。
          </div>
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
      <RestartRequiredProvider>
        <ApprovalProvider>
          <div className="flex flex-col h-screen bg-[var(--background)]">
            <div className="flex flex-1 overflow-hidden">
              <Sidebar
                activeNav={activeNav}
                onNavChange={(id) => setActiveNav(id as NavId)}
                currentSession={sessionKey}
                onSessionSelect={(key) => {
                  setSessionKey(key)
                  setSessionRefreshKey((k) => k + 1)
                }}
              />

              <main className="flex-1 flex flex-col overflow-hidden bg-[var(--background)]">
                {/* ChatConsole is always mounted to preserve message state across navigation */}
                <div className={activeNav === 'chat' ? 'flex flex-col flex-1 overflow-hidden' : 'hidden'}>
                  <ChatConsole
                    sessionKey={sessionKey}
                    onNewSession={(newKey) => {
                      setSessionKey(newKey)
                      setSessionRefreshKey((k) => k + 1)
                    }}
                    onChatFinished={() => setSessionRefreshKey((k) => k + 1)}
                  />
                </div>
                {activeNav === 'sessions' && (
                  <SessionExplorer
                    refreshKey={sessionRefreshKey}
                    onOpenSession={(_key) => {
                      setActiveNav('chat')
                    }}
                  />
                )}
                {activeNav === 'providers' && <ProvidersPage />}
                {activeNav === 'channels' && <ChannelsPage />}
                {activeNav === 'approvals' && <ApprovalsPage />}
                {activeNav === 'cron' && <CronPage />}
                {activeNav === 'memory' && <MemoryPage />}
                {activeNav === 'skills' && <SkillsPage />}
                {activeNav === 'workspace' && <WorkspacePage />}
                {activeNav === 'settings' && <SettingsPage />}
              </main>
            </div>

            <StatusBar />
          </div>
          <ApprovalModal />
        </ApprovalProvider>
      </RestartRequiredProvider>
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
