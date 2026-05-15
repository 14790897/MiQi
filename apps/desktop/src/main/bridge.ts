import { ChildProcess, spawn, execSync } from 'child_process'
import { EventEmitter } from 'events'
import { createInterface, Interface } from 'readline'
import { existsSync, watch } from 'fs'
import { join, extname } from 'path'
import { randomUUID } from 'crypto'
import type { RuntimeState, RuntimeStatus } from '../shared/ipc'

export interface BridgeRequest {
  id: string
  method: string
  params?: Record<string, unknown>
}

interface BridgeResponse {
  id: string
  result?: unknown
  error?: string
  type?: string
  data?: unknown
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
  const bundledBridge =
    join(process.resourcesPath, 'miqi-bridge.exe')
  if (existsSync(bundledBridge)) {
    return { command: bundledBridge, args: [] }
  }

  // If project has uv.lock, use uv run python
  if (
    existsSync(join(projectRoot, 'uv.lock')) ||
    existsSync(join(projectRoot, 'pyproject.toml'))
  ) {
    try {
      execSync('uv --version', { stdio: 'ignore' })
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

  constructor(projectRoot?: string) {
    super()
    // In dev: __dirname = apps/desktop/out/main → projectRoot is 4 levels up
    this.projectRoot = projectRoot || join(__dirname, '..', '..', '..', '..')
    // Enable hot reload in development mode
    this.hotReloadEnabled =
      process.env['NODE_ENV'] === 'development' ||
      process.env['ELECTRON_RENDERER_URL'] !== undefined
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
      })

      this.rl = createInterface({
        input: this.process.stdout!,
        crlfDelay: Infinity,
      })

      this.rl.on('line', (line: string) => {
        try {
          const resp: BridgeResponse = JSON.parse(line)
          const pending = this.pending.get(resp.id)
          if (!pending) return

          if (resp.type) {
            pending.onEvent?.(resp.type, resp.data)
          } else if (resp.error) {
            pending.reject(new Error(resp.error))
          } else {
            pending.resolve(resp.result)
          }
        } catch {
          // Non-JSON line from bridge (shouldn't happen — logs go to stderr)
        }
      })

      this.process.stderr!.on('data', (data: Buffer) => {
        const text = data.toString().trim()
        if (text) {
          console.log(`[MIQI BRIDGE STDERR] ${text}`)
          this.addLog(text)
        }
      })

      this.process.on('close', (code) => {
        this.addLog(`Bridge process exited with code ${code}`)
        this.state = code === 0 ? 'stopped' : 'error'
        this.process = null
        this.rl = null
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
            this.state = 'running'
            this.emitState()
            resolve()
          }
        }, 1500)
      })
    } catch (err) {
      this.state = 'error'
      this.addLog(`Failed to start bridge: ${err}`)
      this.emitState()
      throw err
    }
  }

  async stop(): Promise<void> {
    if (!this.process) return

    this.state = 'stopping'
    this.emitState()

    // Stop file watcher
    this.stopFileWatcher()

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
      (eventType, filename) => {
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

    // Store pending requests to retry after restart
    const pendingRequests = [...this.pending.entries()]
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
    } catch {
      return null
    }
  }

  async send(
    method: string,
    params?: Record<string, unknown>,
    onEvent?: (type: string, data: unknown) => void,
  ): Promise<unknown> {
    if (!this.isRunning()) {
      throw new Error('Bridge not running')
    }

    const id = randomUUID()
    const request: BridgeRequest = { id, method, params }

    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject, onEvent })

      const timeout = setTimeout(
        () => {
          this.pending.delete(id)
          reject(new Error(`Request ${method} timed out`))
        },
        method === 'chat.send' ? 300_000 : 30_000,
      ) // 5 min for chat, 30s for others

      const origResolve = resolve
      const origReject = reject

      this.pending.set(id, {
        resolve: (value: unknown) => {
          clearTimeout(timeout)
          origResolve(value)
        },
        reject: (err: Error) => {
          clearTimeout(timeout)
          origReject(err)
        },
        onEvent,
      })

      this.process!.stdin!.write(JSON.stringify(request) + '\n')
    })
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
