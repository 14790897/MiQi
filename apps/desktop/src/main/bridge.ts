import { ChildProcess, spawn, execSync } from 'child_process'
import { EventEmitter } from 'events'
import { createInterface, Interface } from 'readline'
import { existsSync } from 'fs'
import { join } from 'path'
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

function findPython(projectRoot: string): { command: string; args: string[] } {
  // If user set MIQI_PYTHON_PATH, use it directly
  const envPath = process.env['MIQI_PYTHON_PATH']
  if (envPath) return { command: envPath, args: [] }

  // If project has uv.lock, use uv run python
  if (existsSync(join(projectRoot, 'uv.lock')) || existsSync(join(projectRoot, 'pyproject.toml'))) {
    try {
      execSync('uv --version', { stdio: 'ignore' })
      return { command: 'uv', args: ['run', 'python'] }
    } catch {
      // uv not available, fall through
    }
  }

  // Try .venv
  const venvPython = join(projectRoot, '.venv', 'Scripts', 'python.exe')
  if (existsSync(venvPython)) return { command: venvPython, args: [] }

  // Fallback
  return { command: 'python3', args: [] }
}

export class BridgeManager extends EventEmitter {
  private process: ChildProcess | null = null
  private rl: Interface | null = null
  private pending: Map<string, {
    resolve: (value: unknown) => void
    reject: (reason: Error) => void
    onEvent?: (type: string, data: unknown) => void
  }> = new Map()

  private state: RuntimeState = 'stopped'
  private logs: string[] = []
  private maxLogs: number = 500
  private projectRoot: string

  constructor(projectRoot?: string) {
    super()
    // In dev: __dirname = apps/desktop/out/main → projectRoot is 4 levels up
    this.projectRoot = projectRoot || join(__dirname, '..', '..', '..', '..')
  }

  getStatus(): RuntimeStatus {
    return {
      state: this.state,
      configured: this.state === 'running',
      error: this.state === 'error' ? 'Bridge process exited unexpectedly' : undefined,
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

    const bridgeScript = join(this.projectRoot, 'miqi', 'bridge', 'server.py')
    const { command, args } = findPython(this.projectRoot)

    this.addLog(`Starting MiQi bridge: ${command} ${args.join(' ')} "${bridgeScript}"`)
    this.addLog(`Working directory: ${this.projectRoot}`)

    try {
      const spawnArgs = [...args, bridgeScript]
      this.process = spawn(command, spawnArgs, {
        cwd: this.projectRoot,
        stdio: ['pipe', 'pipe', 'pipe'],
        env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONUTF8: '1' },
      })

      this.rl = createInterface({ input: this.process.stdout!, crlfDelay: Infinity })

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
          if (this.process?.exitCode !== null && this.process?.exitCode !== undefined) {
            reject(new Error(`Bridge process exited immediately with code ${this.process.exitCode}`))
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

  async send(method: string, params?: Record<string, unknown>, onEvent?: (type: string, data: unknown) => void): Promise<unknown> {
    if (!this.process || this.state !== 'running') {
      throw new Error('Bridge not running')
    }

    const id = randomUUID()
    const request: BridgeRequest = { id, method, params }

    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject, onEvent })

      const timeout = setTimeout(() => {
        this.pending.delete(id)
        reject(new Error(`Request ${method} timed out`))
      }, method === 'chat.send' ? 300_000 : 30_000) // 5 min for chat, 30s for others

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
