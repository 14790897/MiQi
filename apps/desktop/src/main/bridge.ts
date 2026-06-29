import { ChildProcess, spawn, execSync } from 'child_process'
import { EventEmitter } from 'events'
import { createInterface, Interface } from 'readline'
import { existsSync, watch } from 'fs'
import { join, extname } from 'path'
import { randomUUID } from 'crypto'
import { BrowserWindow } from 'electron'
import { createTypedAppClient } from '../shared/app-client'
import type { TypedAppClient } from '../shared/app-client'
import type { RuntimeState, RuntimeStatus } from '../shared/ipc'
import { IPC_EVENTS } from '../shared/ipc'

export interface BridgeRequest {
  id: string
  method: string
  params?: Record<string, unknown>
}

interface BridgeResponse {
  id?: string | null
  request_id?: string | null
  result?: unknown
  error?: string
  code?: string
  recoverable?: boolean
  type?: string
  event?: string
  data?: unknown
}

interface SendOptions {
  allowStarting?: boolean
  timeoutMs?: number
}

export interface NormalizedBridgeMessage {
  requestId: string | null
  result?: unknown
  error?: string
  code?: string
  recoverable?: boolean
  eventType?: string
  data?: unknown
}

export interface InitializeParams {
  clientId: string
  clientInfo: {
    name: string
    title: string
    version: string
  }
  capabilities: {
    experimentalApi: boolean
    optOutNotificationMethods: string[]
  }
}

/** Terminal event types that resolve/reject a streaming pending entry. */
const TERMINAL_EVENT_TYPES = new Set(['final', 'error', 'aborted'])

export function normalizeBridgeMessage(resp: BridgeResponse): NormalizedBridgeMessage {
  const requestId =
    typeof resp.id === 'string'
      ? resp.id
      : typeof resp.request_id === 'string'
        ? resp.request_id
        : null

  const eventType =
    typeof resp.type === 'string'
      ? resp.type
      : typeof resp.event === 'string'
        ? resp.event
        : undefined

  return {
    requestId,
    result: resp.result,
    error: resp.error,
    code: resp.code,
    recoverable: resp.recoverable,
    eventType,
    data: resp.data,
  }
}

export function buildInitializeParams(version: string): InitializeParams {
  return {
    clientId: 'miqi-desktop',
    clientInfo: {
      name: 'miqi_desktop',
      title: 'MiQi Desktop',
      version,
    },
    capabilities: {
      experimentalApi: true,
      optOutNotificationMethods: [],
    },
  }
}

function findBridgeExecutable(projectRoot: string): {
  command: string
  args: string[]
} {
  // If user set MIQI_PYTHON_PATH, use it directly with the script
  const envPath = process.env['MIQI_PYTHON_PATH']
  if (envPath) {
    const bridgeScript = join(projectRoot, 'miqi', 'bridge', 'server.py')
    return { command: envPath, args: [bridgeScript] }
  }

  // Check for bundled miqi-bridge executable (packaged app)
  // In asar, __dirname is inside the archive, so use process.resourcesPath
  const bundledBridge = process.resourcesPath
    ? join(process.resourcesPath, 'miqi-bridge.exe')
    : null
  if (bundledBridge && existsSync(bundledBridge)) {
    return { command: bundledBridge, args: [] }
  }

  // If project has uv.lock, use uv run python
  if (
    existsSync(join(projectRoot, 'uv.lock')) ||
    existsSync(join(projectRoot, 'pyproject.toml'))
  ) {
    try {
      execSync('uv --version', { stdio: 'ignore', windowsHide: true })
      const bridgeScript = join(projectRoot, 'miqi', 'bridge', 'server.py')
      return { command: 'uv', args: ['run', 'python', bridgeScript] }
    } catch {
      // uv not available, fall through
    }
  }

  // Try .venv
  const venvPython = join(projectRoot, '.venv', 'Scripts', 'python.exe')
  if (existsSync(venvPython)) {
    const bridgeScript = join(projectRoot, 'miqi', 'bridge', 'server.py')
    return { command: venvPython, args: [bridgeScript] }
  }

  // Fallback
  const bridgeScript = join(projectRoot, 'miqi', 'bridge', 'server.py')
  return { command: 'python3', args: [bridgeScript] }
}

export class BridgeManager extends EventEmitter {
  private process: ChildProcess | null = null
  private rl: Interface | null = null
  private pending: Map<
    string,
    {
      resolve: (value: unknown) => void
      reject: (reason: Error) => void
      onEvent?: (type: string, data: unknown) => void
    }
  > = new Map()

  private state: RuntimeState = 'stopped'
  private logs: string[] = []
  private maxLogs: number = 500
  private projectRoot: string
  private fileWatcher: ReturnType<typeof watch> | null = null
  private hotReloadEnabled: boolean = false
  private lastReloadTime: number = 0
  private reloadCooldown: number = 1000 // 1 second cooldown between reloads
  private initialized: boolean = false
  private clientId: string = 'miqi-desktop'

  constructor(projectRoot?: string) {
    super()
    // In dev: __dirname = apps/desktop/out/main → projectRoot is 4 levels up
    this.projectRoot = projectRoot || join(__dirname, '..', '..', '..', '..')
    // Enable hot reload in development mode
    this.hotReloadEnabled =
      process.env['NODE_ENV'] === 'development' ||
      process.env['ELECTRON_RENDERER_URL'] !== undefined
  }

  /** Whether the bridge has completed the initialize/initialized handshake. */
  isInitialized(): boolean {
    return this.initialized
  }

  getStatus(): RuntimeStatus {
    return {
      state: this.state,
      configured: this.state === 'running',
      error:
        this.state === 'error'
          ? 'Bridge process exited unexpectedly'
          : undefined,
    }
  }

  getProjectRoot(): string {
    return this.projectRoot
  }

  getLogs(): string[] {
    return [...this.logs]
  }

  async start(): Promise<void> {
    if (this.state === 'running' || this.state === 'starting') return

    this.state = 'starting'
    this.emitState()

    const { command, args } = findBridgeExecutable(this.projectRoot)

    this.addLog(`Starting MiQi bridge: ${command} ${args.join(' ')}`)
    this.addLog(`Working directory: ${this.projectRoot}`)

    // Start file watcher for hot reload
    this.startFileWatcher()

    try {
      this.process = spawn(command, args, {
        cwd: this.projectRoot,
        stdio: ['pipe', 'pipe', 'pipe'],
        env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONUTF8: '1' },
        windowsHide: true,
      })

      this.rl = createInterface({
        input: this.process.stdout!,
        crlfDelay: Infinity,
      })

      this.rl.on('line', (line: string) => {
        try {
          const raw: BridgeResponse = JSON.parse(line)
          const resp = normalizeBridgeMessage(raw)

          if (resp.eventType) {
            if (resp.requestId) {
              const pending = this.pending.get(resp.requestId)
              // Terminal events resolve/reject the streaming promise
              if (pending && TERMINAL_EVENT_TYPES.has(resp.eventType)) {
                if (resp.eventType === 'error') {
                  // Error: single channel — only reject; do NOT call onEvent
                  const msg: string =
                    typeof resp.error === 'string' ? resp.error
                    : (resp.data && typeof resp.data === 'object' && 'message' in resp.data && typeof (resp.data as Record<string,unknown>).message === 'string')
                      ? (resp.data as Record<string,unknown>).message as string
                    : typeof resp.data === 'string' ? resp.data
                    : 'Stream error'
                  const err = new Error(msg)
                  if (resp.code) (err as Error & { code?: string }).code = resp.code
                  pending.reject(err)
                } else {
                  // final / aborted: call onEvent then resolve
                  pending.onEvent?.(resp.eventType, resp.data)
                  pending.resolve(resp.data)
                }
                // Terminal: skip bridge-event
                return
              }
              // Non-terminal events: call onEvent for tracked requests.
              // Skip bridge-event when a pending exists — onEvent already
              // delivers to the IPC handler. bridge-event is only for
              // global events without a tracked request (e.g. fs/changed).
              if (pending) {
                pending.onEvent?.(resp.eventType, resp.data)
                return
              }
            }
            this.emit('bridge-event', {
              requestId: resp.requestId,
              type: resp.eventType,
              data: resp.data,
            })
            return
          }

          if (!resp.requestId) {
            this.addLog(`[Bridge] Ignoring response without id/request_id: ${line}`)
            return
          }

          const pending = this.pending.get(resp.requestId)
          if (!pending) {
            this.addLog(`[Bridge] No pending request for response ${resp.requestId}`)
            return
          }

          if (resp.error) {
            const err = new Error(resp.code ? `${resp.error} (${resp.code})` : resp.error)
            ;(err as Error & { code?: string; recoverable?: boolean }).code = resp.code
            ;(err as Error & { code?: string; recoverable?: boolean }).recoverable = resp.recoverable
            this.addLog(
              `[Bridge] ${resp.requestId} failed: ${resp.error}` +
                (resp.code ? ` (${resp.code})` : ''),
            )
            pending.reject(err)
          } else if (pending.onEvent) {
            // Streaming mode: notify via onEvent, keep pending alive for future events
            pending.onEvent('response', resp.result)
          } else {
            pending.resolve(resp.result)
          }
        } catch {
          this.addLog(`[Bridge] Ignoring non-JSON stdout line: ${line}`)
        }
      })

      this.process.stderr!.on('data', (data: Buffer) => {
        const text = data.toString().trim()
        if (text) {
          console.log(`[MIQI BRIDGE STDERR] ${text}`)
          this.addLog(text)
        }
      })

      this.process.on('error', (err) => {
        this.addLog(`Bridge process error: ${err.message}`)
        this.state = 'error'
        this.process = null
        this.emitState()
      })

      // ── Ready handshake ────────────────────────────────────────────
      // Wait for the bridge to send {"type":"ready"} on stdout.
      // PyInstaller onefile exe first-run extraction to %TEMP% can take
      // 5-15+ seconds — the old 1500 ms blind sleep was not enough.
      // Fallback: 60 s timeout (generous for slow disks / first run).
      // ───────────────────────────────────────────────────────────────
      await new Promise<void>((_resolve, _reject) => {
        let settled = false

        const done = (err?: Error) => {
          if (settled) return
          settled = true
          clearTimeout(timeout)
          this.rl?.removeListener('line', onReadyLine)
          this.process?.removeListener('close', onClose)
          if (err) _reject(err)
          else _resolve()
        }

        const onReadyLine = (line: string) => {
          try {
            const msg = JSON.parse(line)
            if (msg.type === 'ready') {
              done()
            }
          } catch {
            // Non-JSON line (e.g. stray print) — ignore
          }
        }

        const onClose = (code: number | null) => {
          done(
            new Error(
              `Bridge process exited with code ${code} before ready signal`,
            ),
          )
        }

        const timeout = setTimeout(() => {
          done(
            new Error(
              'Bridge did not send ready signal within 60 s (PyInstaller extraction may be stuck)',
            ),
          )
        }, 60_000)

        this.rl!.on('line', onReadyLine)
        this.process!.once('close', onClose)
      })

      // Bridge is now fully initialized — switch to running state
      this.addLog('Bridge ready')
      this.state = 'running'
      this.emitState()

      // Install the permanent request-response line handler
      this.rl.on('line', (line: string) => {
        try {
          const resp: BridgeResponse = JSON.parse(line)
          const normalized = normalizeBridgeMessage(resp)
          const pending = normalized.requestId ? this.pending.get(normalized.requestId) : undefined

          if (pending) {
            if (resp.type) {
              pending.onEvent?.(resp.type, resp.data)
            } else if (resp.error) {
              pending.reject(new Error(resp.error))
            } else {
              pending.resolve(resp.result)
            }
          } else if (resp.type && resp.data) {
            // Orphan event (e.g. subagent_result after main agent finished)
            // Forward to all renderer windows so late events are not dropped.
            const eventKey = `CHAT_${resp.type.toUpperCase()}`
            const channel = IPC_EVENTS[eventKey as keyof typeof IPC_EVENTS]
            if (channel) {
              const allWindows = BrowserWindow.getAllWindows()
              for (const win of allWindows) {
                if (!win.isDestroyed()) {
                  win.webContents.send(channel, resp.data)
                }
              }
            }
          }
        } catch {
          // Non-JSON line from bridge (shouldn't happen — logs go to stderr)
        }
      })

      // Handle unexpected exit after ready
      this.process.on('close', (code) => {
        this.addLog(`Bridge process exited with code ${code}`)
        this.state = code === 0 ? 'stopped' : 'error'
        this.process = null
        this.rl = null
        this.initialized = false
        this.clientId = 'miqi-desktop'
        this.emitState()
        // Reject all pending requests
        for (const [id, pending] of this.pending) {
          pending.reject(new Error('Bridge process exited'))
          this.pending.delete(id)
        }
      })

      this.process.on('error', (err) => {
        this.addLog(`Bridge process error: ${err.message}`)
        this.state = 'error'
        this.process = null
        this.initialized = false
        this.clientId = 'miqi-desktop'
        this.emitState()
      })

      // Wait briefly and check if process is still alive
      await new Promise<void>((resolve, reject) => {
        setTimeout(() => {
          if (
            this.process?.exitCode !== null &&
            this.process?.exitCode !== undefined
          ) {
            reject(
              new Error(
                `Bridge process exited immediately with code ${this.process.exitCode}`,
              ),
            )
          } else {
            resolve()
          }
        }, 250)
      })

      await this.initializeConnection()
      this.state = 'running'
      this.emitState()
    } catch (err) {
      this.state = 'error'
      this.addLog(`Failed to start bridge: ${err}`)
      this.emitState()

      // Cleanup on initialization failure
      this.stopFileWatcher()
      if (this.rl) {
        this.rl.close()
        this.rl = null
      }
      if (this.process) {
        this.process.stdin?.end()
        this.process.kill('SIGTERM')
        this.process = null
      }
      this.initialized = false
      this.clientId = 'miqi-desktop'
      // Reject all pending requests
      for (const [id, pending] of this.pending) {
        pending.reject(new Error('Bridge initialization failed'))
        this.pending.delete(id)
      }
      throw err
    }
  }

  async stop(): Promise<void> {
    if (!this.process) return

    this.state = 'stopping'
    this.emitState()

    // Stop file watcher
    this.stopFileWatcher()

    this.initialized = false
    this.clientId = 'miqi-desktop'

    this.process.stdin?.end()
    this.process.kill('SIGTERM')

    // Force kill after 5s
    setTimeout(() => {
      if (this.process) {
        this.process.kill('SIGKILL')
      }
    }, 5000)

    this.addLog('Bridge stopping')
  }

  private startFileWatcher(): void {
    if (!this.hotReloadEnabled || this.fileWatcher) return

    const miqiDir = join(this.projectRoot, 'miqi')
    if (!existsSync(miqiDir)) {
      this.addLog(
        `[Hot Reload] Skipping watcher - miqi directory not found: ${miqiDir}`,
      )
      return
    }

    this.addLog('[Hot Reload] File watcher enabled for Python backend')

    this.fileWatcher = watch(
      miqiDir,
      { recursive: true },
      (_fileEventType, filename) => {
        if (!filename) return

        // Only watch Python files
        const ext = extname(filename)
        if (ext !== '.py') return

        // Skip pycache and __pycache__ directories
        if (filename.includes('__pycache__') || filename.endsWith('.pyc'))
          return

        this.handleFileChange(filename)
      },
    )
  }

  private stopFileWatcher(): void {
    if (this.fileWatcher) {
      this.fileWatcher.close()
      this.fileWatcher = null
      this.addLog('[Hot Reload] File watcher stopped')
    }
  }

  private handleFileChange(filename: string): void {
    const now = Date.now()
    if (now - this.lastReloadTime < this.reloadCooldown) {
      return
    }

    this.lastReloadTime = now
    this.addLog(`[Hot Reload] Detected change in: ${filename}`)

    // Schedule restart after a short delay to allow multiple files to change
    setTimeout(async () => {
      await this.restart()
    }, 500)
  }

  private async restart(): Promise<void> {
    if (this.state !== 'running') return

    this.addLog('[Hot Reload] Restarting bridge due to code changes...')

    this.pending.clear()

    // Stop current process
    if (this.process) {
      this.process.stdin?.end()
      this.process.kill('SIGTERM')
    }

    // Wait briefly for process to exit
    await new Promise((resolve) => setTimeout(resolve, 500))

    // Restart
    try {
      await this.start()
      this.addLog('[Hot Reload] Bridge restarted successfully')
    } catch (err) {
      this.addLog(`[Hot Reload] Failed to restart bridge: ${err}`)
    }
  }

  isRunning(): boolean {
    return this.process !== null && this.state === 'running'
  }

  async sendSafe(
    method: string,
    params?: Record<string, unknown>,
    onEvent?: (type: string, data: unknown) => void,
  ): Promise<unknown> {
    if (!this.isRunning()) return null
    try {
      return await this.send(method, params, onEvent)
    } catch (e: any) {
      this.addLog(`[Bridge] sendSafe ${method} swallowed: ${e?.message ?? String(e)}`)
      return null
    }
  }

  /** Like sendSafe but returns structured error info so the UI can display it.
   *  Use for pages that need to show failure reasons, not just blank states. */
  async sendSafeWithError(
    method: string,
    params?: Record<string, unknown>,
  ): Promise<{ ok: true; value: unknown } | { ok: false; error: string; code?: string }> {
    if (!this.isRunning()) return { ok: false, error: 'Bridge not running' }
    try {
      const value = await this.send(method, params)
      return { ok: true, value }
    } catch (e: any) {
      const msg = e?.message ?? String(e ?? 'Unknown bridge error')
      this.addLog(`[Bridge] sendSafeWithError ${method} failed: ${msg}`)
      return { ok: false, error: msg, code: e?.code }
    }
  }

  app(): TypedAppClient {
    return createTypedAppClient((method, params, onEvent) =>
      this.send(method, params, onEvent),
    )
  }

  async send(
    method: string,
    params?: Record<string, unknown>,
    onEvent?: (type: string, data: unknown) => void,
  ): Promise<unknown> {
    return this.sendRequest(method, params, onEvent)
  }

  private async sendRequest(
    method: string,
    params?: Record<string, unknown>,
    onEvent?: (type: string, data: unknown) => void,
    options: SendOptions = {},
  ): Promise<unknown> {
    const canSend =
      this.isRunning() ||
      (options.allowStarting === true && this.process !== null && this.state === 'starting')

    if (!canSend) {
      throw new Error('Bridge not running')
    }

    const id = randomUUID()
    const request: BridgeRequest = { id, method, params }
    const timeoutMs =
      options.timeoutMs ??
      (method === 'chat.send' ? 300_000 : 30_000)

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id)
        reject(new Error(`Request ${method} timed out`))
      }, timeoutMs)

      this.pending.set(id, {
        resolve: (value: unknown) => {
          clearTimeout(timeout)
          this.pending.delete(id)
          resolve(value)
        },
        reject: (err: Error) => {
          clearTimeout(timeout)
          this.pending.delete(id)
          reject(err)
        },
        onEvent,
      })

      const stdin = this.process!.stdin!
      if (!stdin.writable || stdin.destroyed) {
        this.pending.delete(id)
        reject(new Error('Bridge not running'))
        return
      }
      try {
        stdin.write(JSON.stringify(request) + '\n', (err) => {
          if (err) {
            this.pending.delete(id)
            reject(err)
          }
        })
      } catch (err) {
        this.pending.delete(id)
        reject(err instanceof Error ? err : new Error(String(err)))
      }
    })
  }

  private writeNotification(method: string, params: Record<string, unknown> = {}): void {
    if (!this.process?.stdin) return
    this.process.stdin.write(JSON.stringify({ method, params }) + '\n')
  }

  private async initializeConnection(): Promise<void> {
    const version = '0.1.0'
    const result = await this.sendRequest(
      'initialize',
      buildInitializeParams(version) as unknown as Record<string, unknown>,
      undefined,
      { allowStarting: true, timeoutMs: 15_000 },
    )

    const init = result as { clientId?: string; serverInfo?: { version?: string } } | null
    this.clientId = init?.clientId ?? 'miqi-desktop'
    this.initialized = true
    this.addLog(
      `Bridge initialized as ${this.clientId}` +
        (init?.serverInfo?.version ? ` against server ${init.serverInfo.version}` : ''),
    )
    this.writeNotification('initialized')
  }

  private addLog(message: string): void {
    this.logs.push(`[${new Date().toISOString()}] ${message}`)
    if (this.logs.length > this.maxLogs) {
      this.logs = this.logs.slice(-this.maxLogs)
    }
    this.emit('log', message)
  }

  private emitState(): void {
    this.emit('state', this.getStatus())
  }
}
