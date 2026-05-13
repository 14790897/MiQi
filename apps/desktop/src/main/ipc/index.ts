import { electron } from '../../shared/electron'
import { spawnSync } from 'child_process'
import { existsSync } from 'fs'
import { homedir } from 'os'
import { join } from 'path'
import type { BridgeManager } from '../bridge'
import { IPC, ChatSendInput, SessionGetInput, SessionDeleteInput, ConfigUpdateInput, ProviderTestInput, ProviderUpdateInput, ChannelsUpdateInput, CronCreateInput, CronUpdateInput, CronToggleInput, CronDeleteInput, CronRunInput, CronRunsInput, MemoryGetInput, MemoryUpdateInput, SkillsGetInput, FilesReadInput, FilesWriteInput } from '../../shared/ipc'

const { ipcMain, dialog } = electron

export function registerIpcHandlers(bridge: BridgeManager): void {
  // Helper: ensure bridge is running before sending a request
  async function ensureBridge(): Promise<void> {
    if (bridge.getStatus().state !== 'running') {
      await bridge.start()
    }
  }

  // -----------------------------------------------------------------------
  // Runtime
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.RUNTIME_START, async () => {
    await bridge.start()
    return bridge.getStatus()
  })

  ipcMain.handle(IPC.RUNTIME_STOP, async () => {
    await bridge.stop()
    return bridge.getStatus()
  })

  ipcMain.handle(IPC.RUNTIME_STATUS, () => {
    return bridge.getStatus()
  })

  ipcMain.handle(IPC.RUNTIME_LOGS, () => {
    return bridge.getLogs()
  })

  // -----------------------------------------------------------------------
  // Chat
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.CHAT_SEND, async (_event, payload: unknown) => {
    const input = ChatSendInput.parse(payload)
    await ensureBridge()

    const mainWindow = _event.sender
    const result = await bridge.send('chat.send', {
      content: input.content,
      session_key: input.session_key ?? 'desktop:default',
    }, (type: string, data: unknown) => {
      if (type === 'progress') {
        mainWindow.send('chat:progress', data)
      } else if (type === 'final') {
        mainWindow.send('chat:final', data)
      } else if (type === 'error') {
        mainWindow.send('chat:error', data)
      } else if (type === 'aborted') {
        mainWindow.send('chat:aborted', data)
      } else if (type === 'approval_request') {
        mainWindow.send('approval:request', data)
      } else if (type === 'approval_cleared') {
        mainWindow.send('approval:cleared', data)
      }
    })

    return result
  })

  ipcMain.handle(IPC.CHAT_ABORT, async () => {
    await ensureBridge()
    return bridge.send('chat.abort')
  })

  // -----------------------------------------------------------------------
  // Sessions
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.SESSIONS_LIST, async () => {
    await ensureBridge()
    return bridge.send('sessions.list')
  })

  ipcMain.handle(IPC.SESSIONS_GET, async (_event, payload: unknown) => {
    await ensureBridge()
    const input = SessionGetInput.parse(payload)
    return bridge.send('sessions.get', { session_key: input.session_key })
  })

  ipcMain.handle(IPC.SESSIONS_DELETE, async (_event, payload: unknown) => {
    await ensureBridge()
    const input = SessionDeleteInput.parse(payload)
    return bridge.send('sessions.delete', { session_key: input.session_key })
  })

  // -----------------------------------------------------------------------
  // Config
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.CONFIG_GET, async () => {
    await ensureBridge()
    return bridge.send('config.get')
  })

  ipcMain.handle(IPC.CONFIG_UPDATE, async (_event, payload: unknown) => {
    await ensureBridge()
    const input = ConfigUpdateInput.parse(payload)
    return bridge.send('config.update', { config: input.config })
  })

  // -----------------------------------------------------------------------
  // Providers
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.PROVIDERS_LIST, async () => {
    await ensureBridge()
    return bridge.send('providers.list')
  })

  ipcMain.handle(IPC.PROVIDERS_TEST, async (_event, payload: unknown) => {
    await ensureBridge()
    const input = ProviderTestInput.parse(payload)
    return bridge.send('providers.test', input as Record<string, unknown>)
  })

  ipcMain.handle(IPC.PROVIDERS_UPDATE, async (_event, payload: unknown) => {
    await ensureBridge()
    const input = ProviderUpdateInput.parse(payload)
    return bridge.send('providers.update', input as Record<string, unknown>)
  })

  // -----------------------------------------------------------------------
  // Channels
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.CHANNELS_LIST, async () => {
    await ensureBridge()
    return bridge.send('channels.list')
  })

  ipcMain.handle(IPC.CHANNELS_UPDATE, async (_event, payload: unknown) => {
    await ensureBridge()
    const input = ChannelsUpdateInput.parse(payload)
    return bridge.send('channels.update', input as Record<string, unknown>)
  })

  // -----------------------------------------------------------------------
  // Python check — runs directly in main process, no bridge needed.
  // This must work BEFORE the bridge starts (e.g. during Setup Wizard).
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.PYTHON_CHECK, () => {
    const projectRoot = bridge.getProjectRoot()
    const issues: string[] = []
    let pythonVersion = 'unknown'

    // Candidate python commands in priority order
    const candidates: string[][] = []
    if (process.env['MIQI_PYTHON_PATH']) {
      candidates.push([process.env['MIQI_PYTHON_PATH']!])
    }
    // uv
    const hasUvLock = existsSync(join(projectRoot, 'uv.lock')) || existsSync(join(projectRoot, 'pyproject.toml'))
    if (hasUvLock) {
      candidates.push(['uv', 'run', 'python'])
    }
    // .venv on Windows
    const venvWin = join(projectRoot, '.venv', 'Scripts', 'python.exe')
    if (existsSync(venvWin)) candidates.push([venvWin])
    // .venv on Unix
    const venvUnix = join(projectRoot, '.venv', 'bin', 'python')
    if (existsSync(venvUnix)) candidates.push([venvUnix])
    // system fallbacks
    candidates.push(['python3'], ['python'])

    let pythonCmd: string[] | null = null
    for (const candidate of candidates) {
      try {
        const r = spawnSync(candidate[0], [...candidate.slice(1), '--version'], { timeout: 5000, encoding: 'utf8' })
        if (r.status === 0) {
          pythonCmd = candidate
          const ver = (r.stdout || r.stderr || '').trim().replace(/^Python\s+/i, '')
          pythonVersion = ver
          // Validate version >= 3.11
          const parts = ver.split('.').map(Number)
          if (parts[0] < 3 || (parts[0] === 3 && (parts[1] ?? 0) < 11)) {
            issues.push(`Python ${ver} is too old (need >= 3.11)`)
          }
          break
        }
      } catch {
        // try next
      }
    }

    if (!pythonCmd) {
      issues.push('Python not found. Install Python >= 3.11 or set MIQI_PYTHON_PATH.')
      pythonVersion = 'not found'
    } else {
      // Check key MiQi dependencies
      const checkScript = `
import importlib, sys
for m in ("pydantic", "httpx", "loguru"):
    try:
        importlib.import_module(m)
    except ImportError:
        print("MISSING:" + m)
`
      try {
        const r = spawnSync(pythonCmd[0], [...pythonCmd.slice(1), '-c', checkScript], { timeout: 8000, encoding: 'utf8' })
        const out = (r.stdout || '').trim()
        for (const line of out.split('\n')) {
          if (line.startsWith('MISSING:')) {
            issues.push(`Missing dependency: ${line.slice(8)}`)
          }
        }
      } catch {
        issues.push('Could not check MiQi dependencies')
      }
    }

    const configExists = existsSync(join(homedir(), '.miqi', 'config.json'))

    return {
      ok: issues.length === 0,
      python_version: pythonVersion,
      issues,
      config_exists: configExists,
    }
  })

  // -----------------------------------------------------------------------
  // Dialog (file open for workspace)
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.DIALOG_OPEN_FILE, async () => {
    const result = await dialog.showOpenDialog({
      properties: ['openFile', 'openDirectory'],
    })
    return result.canceled ? null : result.filePaths[0] ?? null
  })

  // -----------------------------------------------------------------------
  // Approvals
  // -----------------------------------------------------------------------
  ipcMain.handle('approvals:list', async () => {
    await ensureBridge()
    return bridge.send('approvals.list')
  })

  ipcMain.handle('approvals:resolve', async (_event, payload: unknown) => {
    await ensureBridge()
    const p = payload as { approval_id: string; decision: string }
    return bridge.send('approvals.resolve', p as Record<string, unknown>)
  })

  ipcMain.handle('approvals:clear_permanent', async (_event, payload: unknown) => {
    await ensureBridge()
    const p = (payload ?? {}) as { pattern?: string }
    return bridge.send('approvals.clear_permanent', p as Record<string, unknown>)
  })

  // -----------------------------------------------------------------------
  // Cron
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.CRON_LIST, async () => {
    await ensureBridge()
    return bridge.send('cron.list')
  })

  ipcMain.handle(IPC.CRON_CREATE, async (_event, payload: unknown) => {
    await ensureBridge()
    const input = CronCreateInput.parse(payload)
    return bridge.send('cron.create', input as Record<string, unknown>)
  })

  ipcMain.handle(IPC.CRON_UPDATE, async (_event, payload: unknown) => {
    await ensureBridge()
    const input = CronUpdateInput.parse(payload)
    return bridge.send('cron.update', input as Record<string, unknown>)
  })

  ipcMain.handle(IPC.CRON_DELETE, async (_event, payload: unknown) => {
    await ensureBridge()
    const input = CronDeleteInput.parse(payload)
    return bridge.send('cron.delete', input as Record<string, unknown>)
  })

  ipcMain.handle(IPC.CRON_TOGGLE, async (_event, payload: unknown) => {
    await ensureBridge()
    const input = CronToggleInput.parse(payload)
    return bridge.send('cron.toggle', input as Record<string, unknown>)
  })

  ipcMain.handle(IPC.CRON_RUN, async (_event, payload: unknown) => {
    await ensureBridge()
    const input = CronRunInput.parse(payload)
    return bridge.send('cron.run', input as Record<string, unknown>)
  })

  ipcMain.handle(IPC.CRON_RUNS, async (_event, payload: unknown) => {
    await ensureBridge()
    const input = CronRunsInput.parse(payload ?? {})
    return bridge.send('cron.runs', input as Record<string, unknown>)
  })

  // -----------------------------------------------------------------------
  // Memory
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.MEMORY_LIST, async () => {
    await ensureBridge()
    return bridge.send('memory.list')
  })

  ipcMain.handle(IPC.MEMORY_GET, async (_event, payload: unknown) => {
    await ensureBridge()
    const input = MemoryGetInput.parse(payload)
    return bridge.send('memory.get', input as Record<string, unknown>)
  })

  ipcMain.handle(IPC.MEMORY_UPDATE, async (_event, payload: unknown) => {
    await ensureBridge()
    const input = MemoryUpdateInput.parse(payload)
    return bridge.send('memory.update', input as Record<string, unknown>)
  })

  ipcMain.handle(IPC.MEMORY_LESSONS, async () => {
    await ensureBridge()
    return bridge.send('memory.lessons')
  })

  ipcMain.handle(IPC.MEMORY_DELETE, async (_event, payload: unknown) => {
    await ensureBridge()
    const p = payload as { path: string }
    return bridge.send('memory.delete', p as Record<string, unknown>)
  })

  // -----------------------------------------------------------------------
  // Skills
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.SKILLS_LIST, async () => {
    await ensureBridge()
    return bridge.send('skills.list')
  })

  ipcMain.handle(IPC.SKILLS_GET, async (_event, payload: unknown) => {
    await ensureBridge()
    const input = SkillsGetInput.parse(payload)
    return bridge.send('skills.get', input as Record<string, unknown>)
  })

  ipcMain.handle(IPC.SKILLS_OPEN_FOLDER, async (_event, payload: unknown) => {
    await ensureBridge()
    const p = payload as { name: string }
    return bridge.send('skills.open_folder', p as Record<string, unknown>)
  })

  // -----------------------------------------------------------------------
  // Files (Workspace Editor)
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.FILES_TREE, async () => {
    await ensureBridge()
    return bridge.send('files.tree')
  })

  ipcMain.handle(IPC.FILES_READ, async (_event, payload: unknown) => {
    await ensureBridge()
    const input = FilesReadInput.parse(payload)
    return bridge.send('files.read', input as Record<string, unknown>)
  })

  ipcMain.handle(IPC.FILES_WRITE, async (_event, payload: unknown) => {
    await ensureBridge()
    const input = FilesWriteInput.parse(payload)
    return bridge.send('files.write', input as Record<string, unknown>)
  })

  ipcMain.handle(IPC.FILES_DELETE, async (_event, payload: unknown) => {
    await ensureBridge()
    const p = payload as { path: string }
    return bridge.send('files.delete', p as Record<string, unknown>)
  })

  // -----------------------------------------------------------------------
  // Write initial config (no bridge needed — used by Setup Wizard before
  // MiQi has ever been configured or started).
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.CONFIG_WRITE_INITIAL, (_event, payload: unknown) => {
    const {
      provider_name,
      api_key,
      api_base,
      model,
      agent_name,
      workspace,
      soul_preset,
      brave_api_key,
      search_provider,
      search_ollama_api_base,
      search_ollama_api_key,
      fetch_provider,
      fetch_ollama_api_base,
      fetch_ollama_api_key,
      papers_provider,
      semantic_scholar_api_key,
    } = payload as {
      provider_name: string
      api_key?: string | null
      api_base?: string | null
      model?: string | null
      agent_name?: string | null
      workspace?: string | null
      soul_preset?: string | null
      brave_api_key?: string | null
      search_provider?: string | null
      search_ollama_api_base?: string | null
      search_ollama_api_key?: string | null
      fetch_provider?: string | null
      fetch_ollama_api_base?: string | null
      fetch_ollama_api_key?: string | null
      papers_provider?: string | null
      semantic_scholar_api_key?: string | null
    }
    const configDir = join(homedir(), '.miqi')
    const configPath = join(configDir, 'config.json')

    // Load existing config if it exists, so we don't clobber other keys
    let existing: Record<string, unknown> = {}
    try {
      const { readFileSync } = require('fs') as typeof import('fs')
      if (existsSync(configPath)) {
        existing = JSON.parse(readFileSync(configPath, 'utf8'))
      }
    } catch {
      // Start fresh
    }

    // Deep-merge provider key
    const providers = (existing['providers'] as Record<string, unknown> | undefined) ?? {}
    providers[provider_name] = {
      ...(providers[provider_name] as Record<string, unknown> | undefined ?? {}),
      ...(api_key ? { apiKey: api_key } : {}),
      ...(api_base ? { apiBase: api_base } : {}),
    }
    existing['providers'] = providers

    // Set agent defaults (model, name, workspace, soulPreset)
    const agents = (existing['agents'] as Record<string, unknown> | undefined) ?? {}
    const defaults = (agents['defaults'] as Record<string, unknown> | undefined) ?? {}
    if (model) defaults['model'] = model
    if (agent_name) defaults['name'] = agent_name
    if (workspace) defaults['workspace'] = workspace
    if (soul_preset) defaults['soulPreset'] = soul_preset
    agents['defaults'] = defaults
    existing['agents'] = agents

    // Web tools
    const tools = (existing['tools'] as Record<string, unknown> | undefined) ?? {}
    const web = (tools['web'] as Record<string, unknown> | undefined) ?? {}

    // Web Search
    const search = (web['search'] as Record<string, unknown> | undefined) ?? {}
    if (search_provider) search['provider'] = search_provider
    if (brave_api_key) search['apiKey'] = brave_api_key
    if (search_ollama_api_base) search['ollamaApiBase'] = search_ollama_api_base
    if (search_ollama_api_key) search['ollamaApiKey'] = search_ollama_api_key
    web['search'] = search

    // Web Fetch
    const fetch = (web['fetch'] as Record<string, unknown> | undefined) ?? {}
    if (fetch_provider) fetch['provider'] = fetch_provider
    if (fetch_ollama_api_base) fetch['ollamaApiBase'] = fetch_ollama_api_base
    if (fetch_ollama_api_key) fetch['ollamaApiKey'] = fetch_ollama_api_key
    web['fetch'] = fetch

    tools['web'] = web

    // Papers
    const papers = (tools['papers'] as Record<string, unknown> | undefined) ?? {}
    if (papers_provider) papers['provider'] = papers_provider
    if (semantic_scholar_api_key) papers['semanticScholarApiKey'] = semantic_scholar_api_key
    tools['papers'] = papers

    existing['tools'] = tools

    // Ensure directory exists
    const { mkdirSync, writeFileSync } = require('fs') as typeof import('fs')
    mkdirSync(configDir, { recursive: true })
    writeFileSync(configPath, JSON.stringify(existing, null, 2), 'utf8')

    return { saved: true, path: configPath }
  })
}
