import { describe, expect, it, vi, beforeEach } from 'vitest'
import { PassThrough } from 'stream'
import {
  buildInitializeParams,
  normalizeBridgeMessage,
} from './bridge'

// ============================================================
// Pure-function tests (unchanged)
// ============================================================

describe('normalizeBridgeMessage', () => {
  it('normalizes AppServer response request_id', () => {
    const msg = normalizeBridgeMessage({
      request_id: 'req-1',
      result: { ok: true },
    })

    expect(msg.requestId).toBe('req-1')
    expect(msg.result).toEqual({ ok: true })
    expect(msg.error).toBeUndefined()
  })

  it('normalizes transport response id', () => {
    const msg = normalizeBridgeMessage({
      id: 'req-2',
      result: { ok: true },
    })

    expect(msg.requestId).toBe('req-2')
  })

  it('normalizes AppServer error code', () => {
    const msg = normalizeBridgeMessage({
      request_id: 'req-3',
      error: 'Not initialized',
      code: 'NOT_INITIALIZED',
      recoverable: false,
    })

    expect(msg.requestId).toBe('req-3')
    expect(msg.error).toBe('Not initialized')
    expect(msg.code).toBe('NOT_INITIALIZED')
    expect(msg.recoverable).toBe(false)
  })

  it('normalizes legacy type events', () => {
    const msg = normalizeBridgeMessage({
      id: 'req-4',
      type: 'progress',
      data: { text: 'running' },
    })

    expect(msg.requestId).toBe('req-4')
    expect(msg.eventType).toBe('progress')
    expect(msg.data).toEqual({ text: 'running' })
  })

  it('normalizes AppServer event envelopes', () => {
    const msg = normalizeBridgeMessage({
      request_id: 'req-5',
      event: 'fs/changed',
      data: { watchId: 'watch-1' },
    })

    expect(msg.requestId).toBe('req-5')
    expect(msg.eventType).toBe('fs/changed')
    expect(msg.data).toEqual({ watchId: 'watch-1' })
  })
})

describe('buildInitializeParams', () => {
  it('builds the Desktop initialize payload', () => {
    const params = buildInitializeParams('0.1.0')

    expect(params.clientId).toBe('miqi-desktop')
    expect(params.clientInfo).toEqual({
      name: 'miqi_desktop',
      title: 'MiQi Desktop',
      version: '0.1.0',
    })
    expect(params.capabilities).toEqual({
      experimentalApi: true,
      optOutNotificationMethods: [],
    })
  })
})

// ============================================================
// Lifecycle tests — mock spawn, use real readline + PassThrough
// ============================================================

const { spawn: mockSpawn, execSync: mockExecSync } = vi.hoisted(() => ({
  spawn: vi.fn(),
  execSync: vi.fn(() => Buffer.from('')),
}))

vi.mock('child_process', () => ({
  spawn: mockSpawn,
  execSync: mockExecSync,
}))

// fs mocks: only return true for uv/pyproject to force the uv code path
vi.mock('fs', () => ({
  existsSync: vi.fn((p: string) => {
    if (typeof p === 'string') {
      if (p.includes('uv.lock') || p.includes('pyproject.toml')) return true
    }
    return false
  }),
  watch: vi.fn(() => ({ close: vi.fn() })),
}))

async function importBridgeManager() {
  const mod = await import('./bridge')
  return mod.BridgeManager
}

function createMockProcess() {
  const stdout = new PassThrough()
  const stderr = new PassThrough()
  const proc = {
    stdin: { write: vi.fn(), end: vi.fn() },
    stdout,
    stderr,
    on: vi.fn(),
    kill: vi.fn(),
    exitCode: null as number | null,
  }
  mockSpawn.mockReturnValue(proc)
  return proc
}

/** Feed a JSON line into the bridge process stdout. */
function feedLine(proc: ReturnType<typeof createMockProcess>, obj: Record<string, unknown>) {
  proc.stdout.write(JSON.stringify(obj) + '\n')
}

/** Get the request ID from the last stdin write matching a method. */
function findRequestId(proc: ReturnType<typeof createMockProcess>, method: string): string | null {
  const write = proc.stdin.write as ReturnType<typeof vi.fn>
  for (const call of write.mock.calls) {
    try {
      const r = JSON.parse(call[0] as string)
      if (r.method === method) return r.id
    } catch { /* skip */ }
  }
  return null
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('BridgeManager lifecycle', () => {
  it('completes initialize handshake and sends initialized notification', async () => {
    const BridgeManager = await importBridgeManager()
    const proc = createMockProcess()
    const bridge = new BridgeManager('/fake/root')

    const startPromise = bridge.start()

    // Wait for the 250ms alive-check + a tick for initializeConnection
    await new Promise((r) => setTimeout(r, 300))
    expect(mockSpawn).toHaveBeenCalled()

    // Feed the initialize response
    const initId = findRequestId(proc, 'initialize')
    expect(initId).toBeTruthy()
    feedLine(proc, {
      id: initId,
      result: { clientId: 'alpha-1', serverInfo: { version: '0.2.0' } },
    })

    await startPromise

    expect(bridge.isInitialized()).toBe(true)
    expect(bridge.isRunning()).toBe(true)
    expect(bridge.getStatus().state).toBe('running')

    // Should have sent the initialized notification
    const writes = proc.stdin.write as ReturnType<typeof vi.fn>
    const initNotification = writes.mock.calls
      .map((c: any[]) => c[0])
      .find((s: string) => s.includes('"method":"initialized"'))
    expect(initNotification).toBeTruthy()
  }, 10_000)

  it('rejects initialize when process exits immediately', async () => {
    const BridgeManager = await importBridgeManager()
    const proc = createMockProcess()
    proc.exitCode = 1

    const bridge = new BridgeManager('/fake/root')
    await expect(bridge.start()).rejects.toThrow(/exited immediately/)
    expect(bridge.getStatus().state).toBe('error')
  })

  it('cleans up all resources on initialize failure', async () => {
    const BridgeManager = await importBridgeManager()
    const proc = createMockProcess()
    const bridge = new BridgeManager('/fake/root')

    const startPromise = bridge.start()
    await new Promise((r) => setTimeout(r, 300))

    const initId = findRequestId(proc, 'initialize')
    feedLine(proc, {
      id: initId,
      error: 'Internal error',
      code: 'INTERNAL',
    })

    await expect(startPromise).rejects.toThrow(/Internal error/)

    // 1. readline close → rl set to null after cleanup
    expect((bridge as any).rl).toBeNull()
    // 2. watcher close → fileWatcher set to null
    expect((bridge as any).fileWatcher).toBeNull()
    // 3. stdin.end called
    expect(proc.stdin.end).toHaveBeenCalled()
    // 4. process.kill called with SIGTERM
    expect(proc.kill).toHaveBeenCalledWith('SIGTERM')
    // 5. pending cleared (size 0 after cleanup)
    expect((bridge as any).pending.size).toBe(0)
  }, 10_000)

  it('routes streaming accepted→progress→final without early resolve', async () => {
    const BridgeManager = await importBridgeManager()
    const proc = createMockProcess()
    const bridge = new BridgeManager('/fake/root')

    // Complete initialize
    const startPromise = bridge.start()
    await new Promise((r) => setTimeout(r, 300))
    feedLine(proc, {
      id: findRequestId(proc, 'initialize'),
      result: { clientId: 'ac', serverInfo: { version: '1' } },
    })
    await startPromise

    // Send a streaming request
    const events: { type: string; data: unknown }[] = []
    let resolved = false
    let rejected = false
    const sendPromise = bridge
      .send('chat.send', { message: 'hello' }, (type, data) => {
        events.push({ type, data })
      })
      .then((v) => { resolved = true; return v })
      .catch(() => { rejected = true })

    await new Promise((r) => setTimeout(r, 10))
    const reqId = findRequestId(proc, 'chat.send')

    // 1) accepted response → onEvent('response', ...), promise NOT resolved
    feedLine(proc, { id: reqId, result: { status: 'accepted', taskId: 'task-1' } })
    await new Promise((r) => setTimeout(r, 10))

    expect(events.length).toBe(1)
    expect(events[0].type).toBe('response')
    expect((events[0].data as any).status).toBe('accepted')
    expect(resolved).toBe(false)
    expect(rejected).toBe(false)

    // 2) progress event
    feedLine(proc, { id: reqId, type: 'progress', data: { text: 'thinking...' } })
    await new Promise((r) => setTimeout(r, 10))
    expect(events.length).toBe(2)
    expect(events[1].type).toBe('progress')
    expect(resolved).toBe(false)

    // 3) final event → promise resolves
    feedLine(proc, { id: reqId, type: 'final', data: { text: 'done!' } })
    const result = await sendPromise
    expect(resolved).toBe(true)
    expect(result).toEqual({ text: 'done!' })
    expect(events.length).toBe(3)
    expect(events[2].type).toBe('final')
  }, 10_000)

  it('rejects streaming promise on error event with data.message envelope', async () => {
    const BridgeManager = await importBridgeManager()
    const proc = createMockProcess()
    const bridge = new BridgeManager('/fake/root')

    const startPromise = bridge.start()
    await new Promise((r) => setTimeout(r, 300))
    feedLine(proc, {
      id: findRequestId(proc, 'initialize'),
      result: { clientId: 'err-test', serverInfo: { version: '1' } },
    })
    await startPromise

    const events: string[] = []
    const sendPromise = bridge.send('chat.send', { message: 'hi' }, (type) => {
      events.push(type)
    })

    await new Promise((r) => setTimeout(r, 10))
    const reqId = findRequestId(proc, 'chat.send')

    // accepted
    feedLine(proc, { id: reqId, result: { status: 'accepted' } })
    await new Promise((r) => setTimeout(r, 10))
    expect(events).toContain('response')

    // error event with data.message envelope (real bridge format)
    feedLine(proc, { id: reqId, type: 'error', data: { message: 'Something broke' } })
    await expect(sendPromise).rejects.toThrow('Something broke')
  }, 10_000)

  it('does not emit bridge-event for terminal error (single channel)', async () => {
    const BridgeManager = await importBridgeManager()
    const proc = createMockProcess()
    const bridge = new BridgeManager('/fake/root')

    const startPromise = bridge.start()
    await new Promise((r) => setTimeout(r, 300))
    feedLine(proc, {
      id: findRequestId(proc, 'initialize'),
      result: { clientId: 'ch-test', serverInfo: { version: '1' } },
    })
    await startPromise

    // Track bridge-event emissions
    const bridgeEvents: unknown[] = []
    bridge.on('bridge-event', (e: unknown) => bridgeEvents.push(e))

    // Send a streaming request
    const sendPromise = bridge.send('chat.send', { message: 'test' }, () => {})

    await new Promise((r) => setTimeout(r, 10))
    const reqId = findRequestId(proc, 'chat.send')

    // progress event → should emit bridge-event
    feedLine(proc, { id: reqId, type: 'progress', data: { text: 'thinking...' } })
    await new Promise((r) => setTimeout(r, 10))
    expect(bridgeEvents.length).toBeGreaterThanOrEqual(1)

    // terminal error event → must NOT emit bridge-event (single channel)
    const beforeCount = bridgeEvents.length
    feedLine(proc, { id: reqId, type: 'error', data: { message: 'Boom' } })

    await expect(sendPromise).rejects.toThrow('Boom')
    // No new bridge-event emitted for terminal error
    expect(bridgeEvents.length).toBe(beforeCount)
  }, 10_000)

  it('rejects all pending on process exit', async () => {
    const BridgeManager = await importBridgeManager()
    const proc = createMockProcess()
    const bridge = new BridgeManager('/fake/root')

    const startPromise = bridge.start()
    await new Promise((r) => setTimeout(r, 300))
    feedLine(proc, {
      id: findRequestId(proc, 'initialize'),
      result: { clientId: 'exit-test', serverInfo: { version: '1' } },
    })
    await startPromise

    // Start a streaming request
    const events: string[] = []
    const sendPromise = bridge.send('chat.send', { message: 'test' }, (type) => {
      events.push(type)
    })

    await new Promise((r) => setTimeout(r, 10))
    const reqId = findRequestId(proc, 'chat.send')

    // accepted
    feedLine(proc, { id: reqId, result: { status: 'accepted' } })
    await new Promise((r) => setTimeout(r, 10))
    expect(events).toContain('response')

    // Simulate process exit → should reject pending
    const closeHandler = proc.on.mock.calls.find(
      (c: any[]) => c[0] === 'close',
    )?.[1] as (code: number) => void
    expect(closeHandler).toBeTruthy()
    closeHandler(1)

    await expect(sendPromise).rejects.toThrow('Bridge process exited')
  }, 10_000)

  it('handles aborted terminal event', async () => {
    const BridgeManager = await importBridgeManager()
    const proc = createMockProcess()
    const bridge = new BridgeManager('/fake/root')

    const startPromise = bridge.start()
    await new Promise((r) => setTimeout(r, 300))
    feedLine(proc, {
      id: findRequestId(proc, 'initialize'),
      result: { clientId: 'abort-test', serverInfo: { version: '1' } },
    })
    await startPromise

    const events: string[] = []
    const sendPromise = bridge.send('chat.send', { message: 'abort-me' }, (type) => {
      events.push(type)
    })

    await new Promise((r) => setTimeout(r, 10))
    const reqId = findRequestId(proc, 'chat.send')

    // accepted
    feedLine(proc, { id: reqId, result: { status: 'accepted' } })
    await new Promise((r) => setTimeout(r, 10))

    // aborted event → promise resolves
    feedLine(proc, { id: reqId, type: 'aborted', data: { reason: 'user cancelled' } })
    const result = await sendPromise
    expect(result).toEqual({ reason: 'user cancelled' })
  }, 10_000)

  it('times out streaming request with no terminal event', async () => {
    const BridgeManager = await importBridgeManager()
    const proc = createMockProcess()
    const bridge = new BridgeManager('/fake/root')

    const startPromise = bridge.start()
    await new Promise((r) => setTimeout(r, 300))
    feedLine(proc, {
      id: findRequestId(proc, 'initialize'),
      result: { clientId: 'timeout-test', serverInfo: { version: '1' } },
    })
    await startPromise

    // Use a custom timeout
    const origSendRequest = (bridge as any).sendRequest.bind(bridge)
    const sendPromise = origSendRequest(
      'chat.send',
      { message: 'test' },
      (() => {}) as any,
      { timeoutMs: 100 },
    )

    await new Promise((r) => setTimeout(r, 10))
    const reqId = findRequestId(proc, 'chat.send')

    // accepted — keeps pending alive
    feedLine(proc, { id: reqId, result: { status: 'accepted' } })
    await new Promise((r) => setTimeout(r, 10))

    // Wait for timeout
    await expect(sendPromise).rejects.toThrow(/timed out/)
  }, 10_000)
})
