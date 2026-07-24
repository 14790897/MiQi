import { useState, useEffect } from 'react';
import { RuntimeProvider, useRuntime } from './contexts/RuntimeContext';
import { TooltipProvider } from './components/ui/Tooltip';
import { Sidebar } from './components/Sidebar';
import { StatusBar } from './components/StatusBar';
import { TopBar } from './components/TopBar';
import { ApprovalBypassBanner } from './components/ApprovalBypassBanner';
import { SetupWizard } from './features/setup/SetupWizard';
import { ChatConsole } from './features/chat/ChatConsole';
import { SettingsPage, type SettingsTab } from './features/settings/SettingsPage';
import { MCPsPage } from './features/mcps/MCPsPage';
import { ApprovalProvider } from './contexts/ApprovalContext';
import { RestartRequiredProvider } from './contexts/RestartRequiredContext';
import { ApprovalModal } from './features/approvals/ApprovalModal';
import { CronPage } from './features/cron/CronPage';
import { MemoryPage } from './features/memory/MemoryPage';
import { ExperiencePage } from './features/experience/ExperiencePage';
import { SkillsPage } from './features/skills/SkillsPage';
import WslStatusPage from './features/wsl/WslStatusPage';
import AgentPanel from './features/agents/AgentPanel';
import PlanTracker from './features/plan/PlanTracker';
import { ApprovalsPage } from './features/approvals/ApprovalsPage';
import { PermissionsPage } from './features/permissions/PermissionsPage';
import { PluginMarket } from './features/plugins/PluginMarket';
import { SessionExplorer } from './features/sessions/SessionExplorer';
import { WorkspacePage } from './features/workspace/WorkspacePage';

type NavId =
  | 'chat'
  | 'workspace'
  | 'agents'
  | 'plan'
  | 'mcps'
  | 'cron'
  | 'memory'
  | 'experience'
  | 'skills'
  | 'wsl'
  | 'permissions'
  | 'plugins'
  | 'approvals'
  | 'sessions'
  | 'settings';

const PRELOAD_OK = typeof window !== 'undefined' && !!(window as any).miqi;

function AppShell() {
  const { status } = useRuntime();
  const [activeNav, setActiveNav] = useState<NavId>('chat');
  const [sessionKey, setSessionKey] = useState(() => {
    try {
      return localStorage.getItem('miqi:lastSession') || 'desktop:default';
    } catch {
      return 'desktop:default';
    }
  });
  const [sessionRefreshKey, setSessionRefreshKey] = useState(0);
  const [runtimeReadyKey, setRuntimeReadyKey] = useState(0);
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(() => {
    // Blocking python.check() stalls the render tree on cold starts
    // (see load_config() cache in miqi/config/loader.py).  Restore
    // the persisted setup flag so the UI becomes interactive immediately.
    try {
      const stored = localStorage.getItem('miqi:configReady');
      if (stored === 'true') return false;
      if (stored === 'false') return true;
    } catch { /* localStorage unavailable */ }
    return null; // first launch — must check
  });
  const [canSkipSetup, setCanSkipSetup] = useState(false); // true when re-running wizard from settings
  const [settingsTab, setSettingsTab] = useState<SettingsTab>('general');

  // Persist last active session so the app restores it on next launch
  useEffect(() => {
    try {
      localStorage.setItem('miqi:lastSession', sessionKey);
    } catch {
      /* localStorage unavailable */
    }
  }, [sessionKey]);

  // When the bridge becomes ready, trigger a session history reload in ChatConsole
  useEffect(() => {
    if (status.state === 'running') {
      setRuntimeReadyKey((k) => k + 1);
    }
  }, [status.state]);

  useEffect(() => {
    if (PRELOAD_OK) {
      const apiKeys = Object.keys(window.miqi).join(', ');
      console.log(`[MiQi] preload OK — exposed namespaces: ${apiKeys}`);
    } else {
      console.error(
        '[MiQi] preload MISSING — window.miqi is undefined. ' +
          'Check that contextBridge.exposeInMainWorld executed.'
      );
      setNeedsSetup(false);
      return;
    }

    const check = async () => {
      try {
        const result = await window.miqi.python.check();
        const skipSetup = result.config_exists;
        setNeedsSetup(!skipSetup);
        try {
          localStorage.setItem('miqi:configReady', String(skipSetup));
        } catch { /* localStorage unavailable */ }
        if (skipSetup) {
          window.miqi.runtime.start().catch(() => {});
        }
      } catch {
        setNeedsSetup(true);
      }
    };
    check();
  }, []);

  const handleSetupComplete = () => {
    setNeedsSetup(false);
    setCanSkipSetup(false);
    setActiveNav('chat');
    try { localStorage.setItem('miqi:configReady', 'true'); } catch { /* ignore */ }
  };

  const handleNewSession = () => {
    if (activeNav !== 'chat') setActiveNav('chat');
    const newKey = `desktop:${Date.now()}`;
    setSessionKey(newKey);
    setSessionRefreshKey((k) => k + 1);
  };

  const openApprovalSettings = () => {
    setSettingsTab('approvals');
    setActiveNav('settings');
  };

  // Loading state
  if (needsSetup === null) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
          background: 'var(--avatar-dark)',
          fontFamily: 'Inter, "PingFang SC", "Microsoft YaHei", ui-sans-serif, system-ui, sans-serif',
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
          <div style={{ fontSize: '13px', color: 'rgba(255,255,255,0.4)' }}>Loading MiQi…</div>
        </div>
      </div>
    );
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
            <span className="text-xl font-bold" style={{ color: 'var(--danger)' }}>
              !
            </span>
          </div>
          <div>
            <h2 className="text-base font-semibold mb-1" style={{ color: 'var(--text)' }}>
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
    );
  }

  // Setup wizard
  if (needsSetup) {
    return (
      <TooltipProvider>
        <SetupWizard
          onComplete={handleSetupComplete}
          onExit={
            canSkipSetup
              ? () => {
                  setNeedsSetup(false);
                  setCanSkipSetup(false);
                }
              : undefined
          }
        />
      </TooltipProvider>
    );
  }

  // Main app
  return (
    <TooltipProvider>
      <RestartRequiredProvider>
        <ApprovalProvider>
          {/* Full-height flex column */}
          <div className="flex flex-col h-screen" style={{ background: 'var(--background)' }}>
            <TopBar onOpenApprovals={openApprovalSettings} />
            <ApprovalBypassBanner onOpenApprovals={openApprovalSettings} />
            {/* Body row */}
            <div className="flex flex-1 overflow-hidden">
              <Sidebar
                currentSession={sessionKey}
                onSessionSelect={(key) => {
                  setSessionKey(key);
                  setActiveNav('chat');
                  setSessionRefreshKey((k) => k + 1);
                }}
                onNavChange={(id) => {
                  if (id === 'settings') setSettingsTab('general');
                  setActiveNav(id as NavId);
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
                    activeNav === 'chat' ? 'flex flex-col flex-1 overflow-hidden' : 'hidden'
                  }
                >
                  <ChatConsole
                    key={sessionKey}
                    sessionKey={sessionKey}
                    loadTrigger={runtimeReadyKey}
                    onNewSession={(newKey) => {
                      setSessionKey(newKey);
                      setSessionRefreshKey((k) => k + 1);
                    }}
                    onChatFinished={() => setSessionRefreshKey((k) => k + 1)}
                    onOpenProviderSettings={() => {
                      setSettingsTab('providers');
                      setActiveNav('settings');
                    }}
                    onOpenApprovals={() => {
                      setSettingsTab('approvals');
                      setActiveNav('settings');
                    }}
                  />
                </div>
                {activeNav === 'workspace' && <WorkspacePage />}
                {activeNav === 'mcps' && <SettingsPage tab="mcps" />}
                {activeNav === 'cron' && <CronPage />}
                {activeNav === 'memory' && <SettingsPage tab="memory" />}
                {activeNav === 'experience' && <SettingsPage tab="experience" />}
                {activeNav === 'skills' && <SettingsPage tab="skills" />}
                {activeNav === 'wsl' && <SettingsPage tab="wsl" />}
                {activeNav === 'agents' && <SettingsPage tab="agents" />}
                {activeNav === 'plan' && <PlanTracker />}
                {activeNav === 'approvals' && <ApprovalsPage />}
                {activeNav === 'permissions' && <SettingsPage tab="permissions" />}
                {activeNav === 'plugins' && <SettingsPage tab="plugins" />}
                {activeNav === 'sessions' && (
                  <SessionExplorer
                    onOpenSession={(key: string) => {
                      setSessionKey(key);
                      setActiveNav('chat');
                    }}
                  />
                )}
                {activeNav === 'settings' && (
                  <SettingsPage
                    tab={settingsTab}
                    onReopenSetup={() => {
                      setCanSkipSetup(true);
                      setNeedsSetup(true);
                    }}
                  />
                )}
              </main>
            </div>

            <StatusBar />
          </div>
          <ApprovalModal />
        </ApprovalProvider>
      </RestartRequiredProvider>
    </TooltipProvider>
  );
}

export default function App() {
  return (
    <RuntimeProvider>
      <AppShell />
    </RuntimeProvider>
  );
}
