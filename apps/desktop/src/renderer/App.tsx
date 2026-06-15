import { useState, useEffect } from 'react'
import { RuntimeProvider, useRuntime } from './contexts/RuntimeContext'
import { TooltipProvider } from './components/ui/Tooltip'
import { Sidebar } from './components/Sidebar'
import { StatusBar } from './components/StatusBar'
import { SetupWizard } from './features/setup/SetupWizard'
import { ChatConsole } from './features/chat/ChatConsole'
import { SettingsPage } from './features/settings/SettingsPage'
import { MCPsPage } from './features/mcps/MCPsPage'
import { ApprovalProvider } from './contexts/ApprovalContext'
import { RestartRequiredProvider } from './contexts/RestartRequiredContext'
import { ApprovalModal } from './features/approvals/ApprovalModal'
import { CronPage } from './features/cron/CronPage'
import { MemoryPage } from './features/memory/MemoryPage'
import { ExperiencePage } from './features/experience/ExperiencePage'
import { SkillsPage } from './features/skills/SkillsPage'
import WslStatusPage from './features/wsl/WslStatusPage'

type NavId =
  | 'chat'
  | 'mcps'
  | 'cron'
  | 'memory'
  | 'experience'
  | 'skills'
  | 'wsl'
  | 'settings'

const PRELOAD_OK = typeof window !== 'undefined' && !!(window as any).miqi

function AppShell() {
  const { status } = useRuntime()
  const [activeNav, setActiveNav] = useState<NavId>('chat')
  const [sessionKey, setSessionKey] = useState('desktop:default')
  const [sessionRefreshKey, setSessionRefreshKey] = useState(0)
  const [runtimeReadyKey, setRuntimeReadyKey] = useState(0)
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null)
  const [canSkipSetup, setCanSkipSetup] = useState(false)  // true when re-running wizard from settings

  // When the bridge becomes ready, trigger a session history reload in ChatConsole
  useEffect(() => {
    if (status.state === 'running') {
      setRuntimeReadyKey((k) => k + 1)
    }
  }, [status.state])

  useEffect(() => {
    if (PRELOAD_OK) {
      const apiKeys = Object.keys(window.miqi).join(', ')
      console.log(`[MiQi] preload OK — exposed namespaces: ${apiKeys}`)
    } else {
      console.error(
        '[MiQi] preload MISSING — window.miqi is undefined. ' +
          'Check that contextBridge.exposeInMainWorld executed.',
      )
      setNeedsSetup(false)
      return
    }

    const check = async () => {
      try {
        const result = await window.miqi.python.check()
        const skipSetup = result.config_exists
        setNeedsSetup(!skipSetup)
        if (skipSetup) {
          window.miqi.runtime.start().catch(() => {})
        }
      } catch {
        setNeedsSetup(true)
      }
    }
    check()
  }, [])

  const handleSetupComplete = () => {
    setNeedsSetup(false)
    setCanSkipSetup(false)
    setActiveNav('chat')
  }

  const handleNewSession = () => {
    if (activeNav !== 'chat') setActiveNav('chat')
    const newKey = `desktop:${Date.now()}`
    setSessionKey(newKey)
    setSessionRefreshKey((k) => k + 1)
  }

  // Loading state
  if (needsSetup === null) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
          background: '#1e1b18',
          fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
        }}
      >
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '12px',
          }}
        >
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '10px',
              background: 'rgba(255,255,255,0.1)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'white',
              fontSize: '20px',
              fontWeight: 700,
            }}
          >
            M
          </div>
          <div style={{ fontSize: '13px', color: 'rgba(255,255,255,0.4)' }}>
            Loading MiQi…
          </div>
        </div>
      </div>
    )
  }

  // Preload missing
  if (!PRELOAD_OK) {
    return (
      <div
        className="flex items-center justify-center h-screen"
        style={{ background: 'var(--background)' }}
      >
        <div className="flex flex-col items-center gap-4 max-w-sm text-center px-6">
          <div
            className="w-12 h-12 rounded-xl flex items-center justify-center"
            style={{ background: 'var(--danger-bg)' }}
          >
            <span
              className="text-xl font-bold"
              style={{ color: 'var(--danger)' }}
            >
              !
            </span>
          </div>
          <div>
            <h2
              className="text-base font-semibold mb-1"
              style={{ color: 'var(--text)' }}
            >
              预加载桥接不可用
            </h2>
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
              应用预加载脚本注入失败。 <br />
              请重启应用。如问题持续，请检查预加载脚本路径或重新安装。{' '}
            </p>
          </div>
          <div className="text-xs" style={{ color: 'var(--text-faint)' }}>
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
        <SetupWizard
          onComplete={handleSetupComplete}
          onExit={canSkipSetup ? () => { setNeedsSetup(false); setCanSkipSetup(false) } : undefined}
        />
      </TooltipProvider>
    )
  }

  // Main app
  return (
    <TooltipProvider>
      <RestartRequiredProvider>
        <ApprovalProvider>
          {/* Full-height flex column */}
          <div
            className="flex flex-col h-screen"
            style={{ background: 'var(--background)' }}
          >
            {/* Body row */}
            <div className="flex flex-1 overflow-hidden">
              <Sidebar
                activeNav={activeNav}
                onNavChange={(id) => setActiveNav(id as NavId)}
                currentSession={sessionKey}
                onSessionSelect={(key) => {
                  setSessionKey(key)
                  setSessionRefreshKey((k) => k + 1)
                }}
                refreshKey={sessionRefreshKey + runtimeReadyKey * 100000}
                onNewSession={handleNewSession}
              />

              <main
                className="flex-1 flex flex-col overflow-hidden"
                style={{ background: 'var(--background)' }}
              >
                <div
                  className={
                    activeNav === 'chat'
                      ? 'flex flex-col flex-1 overflow-hidden'
                      : 'hidden'
                  }
                >
                  <ChatConsole
                    sessionKey={sessionKey}
                    loadTrigger={runtimeReadyKey}
                    onNewSession={(newKey) => {
                      setSessionKey(newKey)
                      setSessionRefreshKey((k) => k + 1)
                    }}
                    onChatFinished={() => setSessionRefreshKey((k) => k + 1)}
                  />
                </div>
                {activeNav === 'mcps' && <MCPsPage />}
                {activeNav === 'cron' && <CronPage />}
                {activeNav === 'memory' && <MemoryPage />}
                {activeNav === 'experience' && <ExperiencePage />}
                {activeNav === 'skills' && <SkillsPage />}
                {activeNav === 'wsl' && <WslStatusPage />}
                {activeNav === 'settings' && <SettingsPage onReopenSetup={() => { setCanSkipSetup(true); setNeedsSetup(true) }} />}
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
