/**
 * grok-bridge.test.ts — Unit tests for GrokBridgeManager + grok-config.
 *
 * Follows the same patterns as bridge.test.ts:
 * - hoisted mocks for child_process spawn
 * - real PassThrough streams for stdout/stderr
 * - vi.mock for fs with a mutable config variable
 * - feedLine() helper to drive the JSON-RPC line reader
 */

import { PassThrough } from 'stream';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { GrokBridgeManager, isGrokBinaryAvailable } from './grok-bridge';
import {
  resolveGrokModelConfig,
  generateGrokConfigToml,
  grokHome,
} from './grok-config';

// ---------------------------------------------------------------------------
// Mutable state for mocks (set by beforeEach, read by mock factories)
// ---------------------------------------------------------------------------

let mockMiQiConfig: string = '{}';
let mockFsExists: (p: string) => boolean = () => false;

// ---------------------------------------------------------------------------
// Hoisted mocks
// ---------------------------------------------------------------------------

const { spawn: mockSpawn, execSync: mockExecSync } = vi.hoisted(() => ({
  spawn: vi.fn(),
  execSync: vi.fn(() => Buffer.from('')),
}));

vi.mock('child_process', async (importOriginal) => {
  const actual = await importOriginal<typeof import('child_process')>();
  return { ...actual, spawn: mockSpawn, execSync: mockExecSync };
});

vi.mock('fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('fs')>();
  return {
    ...actual,
    existsSync: vi.fn((p: import('fs').PathLike) => mockFsExists(p.toString())),
    watch: vi.fn(() => ({ close: vi.fn() })),
    mkdirSync: vi.fn(),
    writeFileSync: vi.fn(),
    readFileSync: vi.fn(() => mockMiQiConfig),
  };
});

vi.mock('readline', async () => {
  const actual = await vi.importActual<typeof import('readline')>('readline');
  return {
    ...actual,
    createInterface: vi.fn((opts: any) => actual.createInterface(opts)),
  };
});

vi.mock('electron', () => ({}));

vi.mock('../electron-log', () => ({
  writeMainProcessLog: vi.fn(),
}));

vi.mock('../../shared/electron', () => ({
  electron: {
    app: { isPackaged: false, whenReady: vi.fn(), on: vi.fn(), quit: vi.fn() },
    BrowserWindow: { prototype: {}, getAllWindows: vi.fn(() => []), fromWebContents: vi.fn() },
    ipcMain: { handle: vi.fn(), on: vi.fn() },
    dialog: { showOpenDialog: vi.fn() },
    shell: { openPath: vi.fn(), showItemInFolder: vi.fn(), openExternal: vi.fn() },
    Menu: { buildFromTemplate: vi.fn(() => ({ popup: vi.fn() })) },
    Notification: { isSupported: vi.fn(() => false) },
  },
}));

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function createMockProcess() {
  const stdout = new PassThrough();
  const stderr = new PassThrough();
  const proc: any = {
    stdin: {
      write: vi.fn((_data: string, cb?: (err?: Error) => void) => { cb?.(); }),
      end: vi.fn(),
      writable: true,
      destroyed: false,
    },
    stdout,
    stderr,
    on: vi.fn(),
    once: vi.fn(),
    removeListener: vi.fn(),
    kill: vi.fn(),
    exitCode: null as number | null,
  };
  mockSpawn.mockReturnValue(proc);
  return proc;
}

function feedLine(proc: any, obj: Record<string, unknown>): void {
  proc.stdout.write(JSON.stringify(obj) + '\n');
}

function findRequest(proc: any, method: string): { id: number; params: unknown } | null {
  const writes = proc.stdin.write?.mock?.calls || [];
  for (const call of writes) {
    try {
      const r = JSON.parse(call[0]);
      if (r.method === method) return { id: r.id, params: r.params };
    } catch { /* skip */ }
  }
  return null;
}

async function startGrokBridge(
  proc: any,
  bridge: GrokBridgeManager,
  initResult: Record<string, unknown> = { protocolVersion: 1 },
  authResult: Record<string, unknown> = {},
  sessionResult: Record<string, unknown> = { sessionId: 'sess-test-001' },
): Promise<void> {
  // Set up fs mock to tell GrokBridgeManager the grok binary exists
  mockFsExists = (p: string) => {
    if (p.includes('target/release/xai-grok-pager')) return true;
    if (p.includes('config.json')) return true;
    if (p.includes('.miqi')) return true;
    return false;
  };

  const startPromise = bridge.start();
  // Wait for spawn + readline + handlers
  await new Promise((r) => setTimeout(r, 300));
  // First line: signal grok is alive (catches the line reader setup)
  feedLine(proc, { jsonrpc: '2.0', id: 0, result: { status: 'ready' } });
  await new Promise((r) => setTimeout(r, 300));

  // initialize request
  const initReq = findRequest(proc, 'initialize');
  expect(initReq).not.toBeNull();
  feedLine(proc, { jsonrpc: '2.0', id: initReq!.id, result: initResult });

  await new Promise((r) => setTimeout(r, 150));

  // authenticate (may be skipped if method not advertised)
  const authReq = findRequest(proc, 'authenticate');
  if (authReq) {
    feedLine(proc, { jsonrpc: '2.0', id: authReq.id, result: authResult });
    await new Promise((r) => setTimeout(r, 100));
  }

  // session/new
  const sessReq = findRequest(proc, 'session/new');
  if (sessReq) {
    feedLine(proc, { jsonrpc: '2.0', id: sessReq.id, result: sessionResult });
    await new Promise((r) => setTimeout(r, 100));
  }

  await startPromise;
}

function setProviderCfg(providers: Record<string, unknown>, model = 'openai/gpt-4.1') {
  mockMiQiConfig = JSON.stringify({
    agents: { defaults: { model } },
    providers,
  });
}

// ---------------------------------------------------------------------------
// Tests: grok-config.ts (pure functions — no process mocks needed)
// ---------------------------------------------------------------------------

describe('grokHome', () => {
  it('returns a path under the home directory', () => {
    const home = grokHome();
    expect(home).toContain('.grok');
    expect(home.length).toBeGreaterThan(5);
  });
});

describe('resolveGrokModelConfig', () => {
  it('returns null for empty config', () => {
    expect(resolveGrokModelConfig({})).toBeNull();
  });

  it('returns null when no provider has an apiKey', () => {
    expect(resolveGrokModelConfig({
      agents: { defaults: { model: 'openai/gpt-4.1' } },
      providers: { openai: { apiBase: 'https://api.openai.com/v1' } },
    })).toBeNull();
  });

  it('resolves a provider with apiKey via the model prefix', () => {
    const r = resolveGrokModelConfig({
      agents: { defaults: { model: 'openai/gpt-4.1' } },
      providers: { openai: { apiKey: 'sk-test-123', apiBase: 'https://api.openai.com/v1' } },
    });
    expect(r).not.toBeNull();
    expect(r!.modelId).toBe('gpt-4.1');
    expect(r!.apiKey).toBe('sk-test-123');
    expect(r!.apiBase).toBe('https://api.openai.com/v1');
    expect(r!.apiKeyEnvVar).toBe('MIQI_API_KEY');
    expect(r!.modelSlug).toBe('grok-model');
  });

  it('strips provider prefix from model string', () => {
    const r = resolveGrokModelConfig({
      agents: { defaults: { model: 'anthropic/claude-opus-4-5' } },
      providers: { anthropic: { apiKey: 'sk-ant-test' } },
    });
    expect(r).not.toBeNull();
    expect(r!.modelId).toBe('claude-opus-4-5');
  });

  it('falls back to first provider with apiKey when model prefix has no match', () => {
    const r = resolveGrokModelConfig({
      agents: { defaults: { model: 'grok' } },
      providers: {
        grok: {},
        openai: { apiKey: 'sk-fallback', model: 'gpt-4o' },
      },
    });
    expect(r).not.toBeNull();
    expect(r!.apiKey).toBe('sk-fallback');
    expect(r!.modelId).toBe('gpt-4o');
  });

  it('falls back to env var if no provider has apiKey', () => {
    process.env['XAI_API_KEY'] = 'xai-env-key';
    try {
      const r = resolveGrokModelConfig({
        agents: { defaults: { model: 'gpt-4.1' } },
        providers: {},
      });
      expect(r).not.toBeNull();
      expect(r!.apiKey).toBe('xai-env-key');
    } finally {
      delete process.env['XAI_API_KEY'];
    }
  });
});

describe('generateGrokConfigToml', () => {
  it('generates a valid TOML with model section', () => {
    const toml = generateGrokConfigToml({
      modelSlug: 'grok-model', modelId: 'gpt-4.1',
      modelName: 'openai/gpt-4.1', apiBase: 'https://api.openai.com/v1',
      apiKey: 'sk-test', apiKeyEnvVar: 'MIQI_API_KEY',
    });
    expect(toml).toContain('[models]');
    expect(toml).toContain('default = "grok-model"');
    expect(toml).toContain('[model.grok-model]');
    expect(toml).toContain('model = "gpt-4.1"');
    expect(toml).toContain('base_url = "https://api.openai.com/v1"');
    expect(toml).toContain('env_key = "MIQI_API_KEY"');
  });

  it('omits base_url when not provided', () => {
    const toml = generateGrokConfigToml({
      modelSlug: 'grok-model', modelId: 'claude-opus-4-5',
      modelName: 'anthropic/claude-opus-4-5', apiKey: 'sk-ant-test', apiKeyEnvVar: 'MIQI_API_KEY',
    });
    expect(toml).not.toContain('base_url');
  });

  it('escapes special characters in values', () => {
    const toml = generateGrokConfigToml({
      modelSlug: 'grok-model', modelId: 'model-with-"quotes"',
      modelName: 'Test "Model"', apiKey: 'sk-test', apiKeyEnvVar: 'MIQI_API_KEY',
    });
    expect(toml).toContain('model = "model-with-\\"quotes\\""');
  });
});

// ---------------------------------------------------------------------------
// Tests: GrokBridgeManager lifecycle
// ---------------------------------------------------------------------------

describe('GrokBridgeManager lifecycle', () => {
  let bridge: GrokBridgeManager;

  beforeEach(() => {
    vi.clearAllMocks();
    setProviderCfg({ openai: { apiKey: 'sk-test-bridge', apiBase: 'https://api.openai.com/v1' } });
  });

  afterEach(() => {
    delete process.env['MIQI_API_KEY'];
  });

  it('starts in stopped state', () => {
    bridge = new GrokBridgeManager('/fake/project');
    expect(bridge.isRunning()).toBe(false);
    expect(bridge.getStatus().state).toBe('stopped');
  });

  it('goes through start → running lifecycle', async () => {
    bridge = new GrokBridgeManager('/fake/project');
    const proc = createMockProcess();
    await startGrokBridge(proc, bridge);
    expect(bridge.isRunning()).toBe(true);
    expect(bridge.getStatus().state).toBe('running');
    expect(mockSpawn).toHaveBeenCalled();
  }, 10_000);

  it('sets MIQI_API_KEY env var on start', async () => {
    setProviderCfg({ openai: { apiKey: 'sk-test-bridge', apiBase: 'https://api.openai.com/v1' } }, 'openai/gpt-4.1');
    delete process.env['MIQI_API_KEY'];
    bridge = new GrokBridgeManager('/fake/project');
    const proc = createMockProcess();
    await startGrokBridge(proc, bridge);
    expect(process.env['MIQI_API_KEY']).toBe('sk-test-bridge');
  }, 10_000);

  it('writes config.toml on start', async () => {
    const fs = await import('fs');
    bridge = new GrokBridgeManager('/fake/project');
    const proc = createMockProcess();
    await startGrokBridge(proc, bridge);
    expect(fs.writeFileSync).toHaveBeenCalled();
    const writeCall = (fs.writeFileSync as any).mock.calls.find((c: any[]) => c[0].includes('config.toml'));
    expect(writeCall).toBeDefined();
    expect(writeCall[1]).toContain('[model.grok-model]');
    expect(writeCall[1]).toContain('model = "gpt-4.1"');
  }, 10_000);

  it('throws when no configured provider exists', async () => {
    mockMiQiConfig = '{}';
    bridge = new GrokBridgeManager('/fake/project');
    createMockProcess();
    await expect(bridge.start()).rejects.toThrow(/No configured provider found/);
    expect(bridge.getStatus().state).toBe('error');
  }, 10_000);

  it('stops gracefully', async () => {
    bridge = new GrokBridgeManager('/fake/project');
    const proc = createMockProcess();
    await startGrokBridge(proc, bridge);
    expect(bridge.isRunning()).toBe(true);

    // Simulate process close on kill
    proc.kill.mockImplementation(() => {
      proc.exitCode = 0;
      // Find and call the 'close' handler registered during start
      const closeHandlers = (proc.once as any).mock.calls
        .filter((c: any[]) => c[0] === 'close');
      for (const [_event, handler] of closeHandlers) {
        setTimeout(() => handler(0), 10);
      }
      return true;
    });

    await bridge.stop();
    expect(bridge.isRunning()).toBe(false);
    expect(bridge.getStatus().state).toBe('stopped');
  }, 10_000);

  it('emit state events on lifecycle transitions', async () => {
    bridge = new GrokBridgeManager('/fake/project');
    const proc = createMockProcess();
    const stateEvents: string[] = [];
    bridge.on('state', (status: any) => stateEvents.push(status.state));
    await startGrokBridge(proc, bridge);
    expect(stateEvents).toContain('starting');
    expect(stateEvents).toContain('running');
  }, 10_000);

  it('rejects send when bridge is not running', async () => {
    bridge = new GrokBridgeManager('/fake/project');
    await expect(bridge.send('chat.send', { content: 'hi' })).rejects.toThrow('not running');
  });
});

// ---------------------------------------------------------------------------
// Tests: chat.send streaming
// ---------------------------------------------------------------------------

describe('GrokBridgeManager chat.send', () => {
  let bridge: GrokBridgeManager;
  let proc: any;

  beforeEach(() => {
    vi.clearAllMocks();
    setProviderCfg({ openai: { apiKey: 'sk-chat-test', apiBase: 'https://api.openai.com/v1' } });
  });

  afterEach(() => {
    delete process.env['MIQI_API_KEY'];
  });

  async function setup() {
    bridge = new GrokBridgeManager('/fake/project');
    proc = createMockProcess();
    await startGrokBridge(proc, bridge);
  }

  it('sends session/prompt and receives streaming text chunks', async () => {
    await setup();
    const events: Array<{ type: string; data: unknown }> = [];
    const onEvent = (type: string, data: unknown) => events.push({ type, data });

    const sendPromise = bridge.send('chat.send', {
      content: 'Hello grok', session_key: 'desktop:default',
    }, onEvent);

    await new Promise((r) => setTimeout(r, 150));
    const promptReq = findRequest(proc, 'session/prompt');
    expect(promptReq).not.toBeNull();

    feedLine(proc, {
      jsonrpc: '2.0', method: 'session/update',
      params: {
        sessionId: 'sess-test-001',
        update: { sessionUpdate: 'agent_message_chunk', content: { type: 'text', text: 'Hello' } },
      },
    });
    feedLine(proc, {
      jsonrpc: '2.0', method: 'session/update',
      params: {
        sessionId: 'sess-test-001',
        update: { sessionUpdate: 'agent_message_chunk', content: { type: 'text', text: ' from grok!' } },
      },
    });
    feedLine(proc, { jsonrpc: '2.0', id: promptReq!.id, result: { stopReason: 'end_turn' } });

    await sendPromise;
    const progressEvents = events.filter((e) => e.type === 'progress');
    const finalEvents = events.filter((e) => e.type === 'final');
    expect(progressEvents.length).toBe(2);
    expect((progressEvents[0].data as any).delta).toBe('Hello');
    expect((progressEvents[1].data as any).delta).toBe(' from grok!');
    expect(finalEvents.length).toBe(1);
    expect((finalEvents[0].data as any).stop_reason).toBe('end_turn');
  }, 10_000);

  it('receives thought chunks as progress', async () => {
    await setup();
    const events: Array<{ type: string; data: unknown }> = [];
    const onEvent = (type: string, data: unknown) => events.push({ type, data });

    const sendPromise = bridge.send('chat.send', { content: 'Think' }, onEvent);
    await new Promise((r) => setTimeout(r, 150));
    const promptReq = findRequest(proc, 'session/prompt');

    feedLine(proc, {
      jsonrpc: '2.0', method: 'session/update',
      params: {
        sessionId: 'sess-test-001',
        update: { sessionUpdate: 'agent_thought_chunk', content: { type: 'text', text: 'Analyzing...' } },
      },
    });
    feedLine(proc, { jsonrpc: '2.0', id: promptReq!.id, result: { stopReason: 'end_turn' } });
    await sendPromise;

    const thoughtEvents = events.filter(
      (e) => e.type === 'progress' && (e.data as any).stream === 'stderr'
    );
    expect(thoughtEvents.length).toBe(1);
    expect((thoughtEvents[0].data as any).delta).toBe('Analyzing...');
  }, 10_000);

  it('receives tool call events', async () => {
    await setup();
    const events: Array<{ type: string; data: unknown }> = [];
    const onEvent = (type: string, data: unknown) => events.push({ type, data });

    const sendPromise = bridge.send('chat.send', { content: 'List files' }, onEvent);
    await new Promise((r) => setTimeout(r, 150));
    const promptReq = findRequest(proc, 'session/prompt');

    feedLine(proc, {
      jsonrpc: '2.0', method: 'session/update',
      params: {
        sessionId: 'sess-test-001',
        update: { sessionUpdate: 'tool_call', title: 'List directory', toolCallId: 'tc-001', kind: 'list', locations: [{ path: '/home' }] },
      },
    });
    feedLine(proc, {
      jsonrpc: '2.0', method: 'session/update',
      params: {
        sessionId: 'sess-test-001',
        update: { sessionUpdate: 'tool_call_update', toolCallId: 'tc-001', content: [{ type: 'content', content: { type: 'text', text: 'file1.txt' } }] },
      },
    });
    feedLine(proc, { jsonrpc: '2.0', id: promptReq!.id, result: { stopReason: 'end_turn' } });
    await sendPromise;

    const toolEvents = events.filter((e) => e.type === 'progress' && (e.data as any).tool_hint);
    expect(toolEvents.length).toBeGreaterThanOrEqual(1);
    expect((toolEvents[0].data as any).text).toBe('List directory');
  }, 10_000);

  it('handles errors from session/prompt', async () => {
    await setup();
    const events: Array<{ type: string; data: unknown }> = [];
    const onEvent = (type: string, data: unknown) => events.push({ type, data });

    const sendPromise = bridge.send('chat.send', { content: 'This will error' }, onEvent);
    await new Promise((r) => setTimeout(r, 150));
    const promptReq = findRequest(proc, 'session/prompt');

    feedLine(proc, { jsonrpc: '2.0', id: promptReq!.id, error: { code: -32000, message: 'Model not found: gpt-4.1' } });
    await expect(sendPromise).rejects.toThrow('Model not found');

    const errorEvents = events.filter((e) => e.type === 'error');
    expect(errorEvents.length).toBe(1);
  }, 10_000);

  it('creates sessions lazily', async () => {
    setProviderCfg({ openai: { apiKey: 'sk-test', apiBase: 'https://api.openai.com/v1' } }, 'openai/gpt-4.1');
    bridge = new GrokBridgeManager('/fake/project');
    proc = createMockProcess();
    await startGrokBridge(proc, bridge);

    const sendPromise = bridge.send('chat.send', { content: 'hi' }, () => {});
    await new Promise((r) => setTimeout(r, 150));
    const promptReq = findRequest(proc, 'session/prompt');
    expect(promptReq).not.toBeNull();
    expect((promptReq!.params as any).sessionId).toBe('sess-test-001');

    feedLine(proc, { jsonrpc: '2.0', id: promptReq!.id, result: { stopReason: 'end_turn' } });
    await sendPromise;
  }, 10_000);
});

// ---------------------------------------------------------------------------
// Tests: chat.abort
// ---------------------------------------------------------------------------

describe('GrokBridgeManager chat.abort', () => {
  let bridge: GrokBridgeManager;
  let proc: any;

  beforeEach(async () => {
    vi.clearAllMocks();
    setProviderCfg({ openai: { apiKey: 'sk-test', apiBase: 'https://api.openai.com/v1' } });
    bridge = new GrokBridgeManager('/fake/project');
    proc = createMockProcess();
    await startGrokBridge(proc, bridge);
  });

  afterEach(() => {
    delete process.env['MIQI_API_KEY'];
  });

  it('sends session/cancel notification', async () => {
    const result = await bridge.send('chat.abort', { session_key: 'desktop:default' });
    expect(result).toEqual({ aborted: true, session_key: 'sess-test-001' });

    const writes = proc.stdin.write?.mock?.calls || [];
    const cancelCall = writes.find((c: any[]) => {
      try { const r = JSON.parse(c[0]); return r.method === 'session/cancel'; } catch { return false; }
    });
    expect(cancelCall).toBeDefined();
  }, 10_000);
});

// ---------------------------------------------------------------------------
// Tests: Permissions
// ---------------------------------------------------------------------------

describe('GrokBridgeManager permissions', () => {
  let bridge: GrokBridgeManager;
  let proc: any;

  beforeEach(async () => {
    vi.clearAllMocks();
    setProviderCfg({ openai: { apiKey: 'sk-test', apiBase: 'https://api.openai.com/v1' } });
    bridge = new GrokBridgeManager('/fake/project');
    proc = createMockProcess();
    await startGrokBridge(proc, bridge);
  });

  afterEach(() => {
    delete process.env['MIQI_API_KEY'];
  });

  it('emits approval:request when grok requests permission', async () => {
    const approvalEvents: unknown[] = [];
    const onEvent = (type: string, data: unknown) => {
      if (type === 'approval_request') approvalEvents.push(data);
    };

    const sendPromise = bridge.send('chat.send', { content: 'Run a command' }, onEvent);
    await new Promise((r) => setTimeout(r, 150));
    const promptReq = findRequest(proc, 'session/prompt');

    feedLine(proc, {
      jsonrpc: '2.0', id: 50, method: 'session/request_permission',
      params: {
        sessionId: 'sess-test-001',
        toolCall: { title: 'Run shell command', kind: 'execute', rawInput: { command: 'npm install' } },
        options: [
          { optionId: 'allow_once', name: 'Allow once', kind: 'allow_once' },
          { optionId: 'allow_always', name: 'Always allow', kind: 'allow_always' },
          { optionId: 'deny_once', name: 'Deny', kind: 'deny_once' },
        ],
      },
    });
    await new Promise((r) => setTimeout(r, 50));

    expect(approvalEvents.length).toBe(1);
    const evt = approvalEvents[0] as any;
    expect(evt.approval_id).toBe('grok:50');
    expect(evt.command).toBe('npm install');
    expect(evt.description).toBe('Run shell command');
    expect(evt.allow_permanent).toBe(true);
    expect(evt.category).toBe('exec');

    // Resolve permission — sends JSON-RPC response
    await bridge.resolvePermission('grok:50', 'allow_once');

    const writes = proc.stdin.write?.mock?.calls || [];
    const responseCall = writes.find((c: any[]) => {
      try {
        const r = JSON.parse(c[0]);
        return r.id === 50 && r.result?.outcome?.optionId === 'allow_once';
      } catch { return false; }
    });
    expect(responseCall).toBeDefined();

    feedLine(proc, { jsonrpc: '2.0', id: promptReq!.id, result: { stopReason: 'end_turn' } });
    await sendPromise;
  }, 10_000);

  it('handles reject permission', async () => {
    const sendPromise = bridge.send('chat.send', { content: 'test' }, () => {});
    await new Promise((r) => setTimeout(r, 150));
    const promptReq = findRequest(proc, 'session/prompt');

    feedLine(proc, {
      jsonrpc: '2.0', id: 51, method: 'session/request_permission',
      params: {
        sessionId: 'sess-test-001',
        toolCall: { title: 'Delete file', kind: 'write', rawInput: { path: '/important.txt' } },
        options: [{ optionId: 'allow_once', name: 'Allow once', kind: 'allow_once' }, { optionId: 'deny_once', name: 'Deny', kind: 'deny_once' }],
      },
    });
    await new Promise((r) => setTimeout(r, 50));
    await bridge.resolvePermission('grok:51', 'reject_once');

    feedLine(proc, { jsonrpc: '2.0', id: promptReq!.id, result: { stopReason: 'end_turn' } });
    await sendPromise;
  }, 10_000);

  it('silently ignores unknown permission id', async () => {
    await bridge.resolvePermission('grok:unknown-id', 'allow_once');
  });
});

// ---------------------------------------------------------------------------
// Tests: isGrokBinaryAvailable
// ---------------------------------------------------------------------------

describe('isGrokBinaryAvailable', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns true when binary exists at release path', () => {
    mockFsExists = (p: string) => {
      if (p.includes('target/release/xai-grok-pager')) return true;
      return false;
    };
    expect(isGrokBinaryAvailable('/fake/project')).toBe(true);
  });

  it('returns false when all paths miss', () => {
    mockFsExists = () => false;
    mockExecSync.mockImplementation(() => { throw new Error('not found'); });
    expect(isGrokBinaryAvailable('/fake/project')).toBe(false);
  });
});
