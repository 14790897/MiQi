/**
 * grok-bridge.ts — GrokBridgeManager
 *
 * Spawns `grok agent stdio` and drives it via the Agent Client Protocol
 * (ACP — JSON-RPC 2.0 over stdin/stdout).  Mirrors BridgeManager's pattern
 * so the IPC layer can treat both bridges uniformly.
 */

import { ChildProcess, spawn, execSync } from 'child_process';
import { EventEmitter } from 'events';
import { createInterface, Interface } from 'readline';
import { existsSync, readFileSync } from 'fs';
import { join } from 'path';
import { homedir } from 'os';
import { randomUUID } from 'crypto';
import type { RuntimeState, RuntimeStatus } from '../../shared/ipc';
import { IPC_EVENTS } from '../../shared/ipc';
import { writeMainProcessLog } from '../electron-log';
import { resolveGrokModelConfig, generateGrokConfigToml, writeGrokConfigToml } from './grok-config';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Methods that are long-lived (streaming) — get extended timeouts. */
const STREAMING_METHODS = new Set(['session/prompt']);

/** Default request timeout in ms for non-streaming methods. */
const DEFAULT_TIMEOUT_MS = 30_000;

/** Streaming inactivity timeout — matches the Python bridge's chat timeout. */
const STREAMING_TIMEOUT_MS = 720_000; // 12 min

// ---------------------------------------------------------------------------
// Process discovery
// ---------------------------------------------------------------------------

function findGrokExecutable(projectRoot: string): { command: string; args: string[] } {
  const isWindows = process.platform === 'win32';
  const exeSuffix = isWindows ? '.exe' : '';

  // 1. Explicit env var
  const envPath = process.env['GROK_BUILD_PATH'];
  if (envPath) {
    return { command: envPath, args: ['agent', 'stdio'] };
  }

  // 2. Installed in ~/.grok/bin/ (official distribution)
  const homeGrok = join(homedir(), '.grok', 'bin', `grok${exeSuffix}`);
  if (existsSync(homeGrok)) {
    return { command: homeGrok, args: ['agent', 'stdio'] };
  }

  // 3. grok-build in project (development mode)
  const grokBuildDir = join(projectRoot, 'grok-build');
  const releaseExe = join(grokBuildDir, 'target', 'release', `xai-grok-pager${exeSuffix}`);
  if (existsSync(releaseExe)) {
    return { command: releaseExe, args: ['agent', 'stdio'] };
  }

  const debugExe = join(grokBuildDir, 'target', 'debug', `xai-grok-pager${exeSuffix}`);
  if (existsSync(debugExe)) {
    return { command: debugExe, args: ['agent', 'stdio'] };
  }

  // 4. Bundled in resources (packaged app)
  const bundledExe = process.resourcesPath
    ? join(process.resourcesPath, `xai-grok-pager${exeSuffix}`)
    : null;
  if (bundledExe && existsSync(bundledExe)) {
    return { command: bundledExe, args: ['agent', 'stdio'] };
  }

  // 5. PATH fallback
  return { command: 'grok', args: ['agent', 'stdio'] };
}

/** Check whether any grok binary exists anywhere. */
export function isGrokBinaryAvailable(projectRoot: string): boolean {
  try {
    const { command, args } = findGrokExecutable(projectRoot);
    // If command is an absolute path, check existence
    if (command.includes('/') || command.includes('\\')) {
      return existsSync(command);
    }
    // On PATH — try `where` / `which`
    const whichCmd = process.platform === 'win32' ? 'where' : 'which';
    execSync(`${whichCmd} ${command}`, { stdio: 'ignore', windowsHide: true });
    return true;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// ACP wire types
// ---------------------------------------------------------------------------

interface AcpRequest {
  jsonrpc: '2.0';
  id: number;
  method: string;
  params?: unknown;
}

interface AcpResponse {
  jsonrpc: '2.0';
  id: number;
  result?: unknown;
  error?: {
    code: number;
    message: string;
    data?: unknown;
  };
}

interface AcpNotification {
  jsonrpc: '2.0';
  method: string;
  params?: unknown;
}

type AcpMessage = AcpRequest | AcpResponse | AcpNotification;

// ---------------------------------------------------------------------------
// GrokBridgeManager
// ---------------------------------------------------------------------------

export class GrokBridgeManager extends EventEmitter {
  private process: ChildProcess | null = null;
  private rl: Interface | null = null;

  private state: RuntimeState = 'stopped';
  private lastError: string = '';
  private logs: string[] = [];
  private maxLogs: number = 500;
  private projectRoot: string;

  // JSON-RPC state
  private nextId: number = 1;
  private pendingPromptContent: string = '';
  private pending: Map<
    number,
    {
      resolve: (value: unknown) => void;
      reject: (reason: Error) => void;
      onEvent?: (type: string, data: unknown) => void;
      refreshTimeout?: () => void;
    }
  > = new Map();

  // ACP session cache: miqiSessionKey → grokSessionId
  private sessionCache: Map<string, string> = new Map();
  // Current active grok session
  private currentSessionId: string | null = null;
  // MiQi session key that maps to currentSessionId
  private currentSessionKey: string = 'desktop:default';
  // Pending grok model config
  private modelConfig: ReturnType<typeof resolveGrokModelConfig> = null;

  // Permission callbacks — waiting for user response
  private pendingPermissions: Map<
    string,
    { resolve: (v: unknown) => void; reject: (e: Error) => void }
  > = new Map();

  constructor(projectRoot?: string) {
    super();
    this.projectRoot = projectRoot || join(__dirname, '..', '..', '..', '..');
  }

  // -----------------------------------------------------------------------
  // Public API (mirrors BridgeManager)
  // -----------------------------------------------------------------------

  getStatus(): RuntimeStatus {
    return {
      state: this.state,
      configured: this.state === 'running',
      sandbox_available: false,
      error:
        this.state === 'error'
          ? this.lastError || 'Grok bridge process exited unexpectedly'
          : undefined,
    };
  }

  getProjectRoot(): string {
    return this.projectRoot;
  }

  isRunning(): boolean {
    return this.process !== null && this.state === 'running';
  }

  getLogs(): string[] {
    return [...this.logs];
  }

  async ensureRunning(): Promise<boolean> {
    if (this.isRunning()) return true;
    await this.start();
    // Wait for actual ready state (handle fire-and-forget race)
    let waited = 0;
    while (this.state === 'starting' && waited < 30_000) {
      await new Promise((r) => setTimeout(r, 200));
      waited += 200;
    }
    if (this.state !== 'running') {
      throw new Error(`Grok backend not ready after ${waited}ms: state=${this.state}`);
    }
    return true;
  }

  // -----------------------------------------------------------------------
  // Lifecycle
  // -----------------------------------------------------------------------

  async start(): Promise<void> {
    console.log('[grok:start] ENTER');
    if (this.state === 'running' || this.state === 'starting') return;

    console.log('[grok] start() called, re-reading MiQi config...');

    this.sessionCache.clear();
    this.clearPending(new Error('Grok bridge restarting'));

    this.state = 'starting';
    this.emitState();

    // Resolve model config from MiQi config
    const config = readMiQiConfig();
    this.modelConfig = resolveGrokModelConfig(config);
    if (!this.modelConfig) {
      this.lastError = 'No configured provider found';
      this.addLog('No configured provider found — grok backend staying in stopped state');
      this.recordMainLog(
        'WARN',
        'No configured provider with API key found. Set up at least one provider in Settings.'
      );
      this.state = 'error';
      this.emitState();
      return; // don't throw — let ensureRunning retry after user configures providers
    }

    // Set API key env var and generate config.toml
    process.env[this.modelConfig.apiKeyEnvVar] = this.modelConfig.apiKey;
    writeGrokConfigToml(generateGrokConfigToml(this.modelConfig));

    const { command, args } = findGrokExecutable(this.projectRoot);
    this.addLog(`Starting grok bridge: ${command} ${args.join(' ')}`);
    this.addLog(`Model: ${this.modelConfig.modelId} via ${this.modelConfig.apiBase || 'default'}`);
    this.recordMainLog('INFO', `Starting grok bridge: ${command} ${args.join(' ')}`);

    let startedProcess: ChildProcess | null = null;
    let startedReader: Interface | null = null;

    try {
      const grokProcess = spawn(command, args, {
        cwd: this.projectRoot,
        stdio: ['pipe', 'pipe', 'pipe'],
        env: {
          ...process.env,
          [this.modelConfig.apiKeyEnvVar]: this.modelConfig.apiKey ?? '',
          NO_COLOR: '1',
        },
        windowsHide: true,
      });
      this.process = grokProcess;
      startedProcess = grokProcess;

      const lineReader = createInterface({
        input: grokProcess.stdout!,
        crlfDelay: Infinity,
      });
      this.rl = lineReader;
      startedReader = lineReader;

      lineReader.on('line', (line: string) => {
        if (this.process !== grokProcess) return;
        try {
          const msg: AcpMessage = JSON.parse(line);
          this.handleAcpMessage(msg);
        } catch {
          // Non-JSON line from grok (e.g. startup log) — forward as log
          if (line.trim()) {
            this.addLog(`[grok stdout] ${line}`);
          }
        }
      });

      grokProcess.stderr!.on('data', (data: Buffer) => {
        const text = data.toString().trim();
        if (text) {
          this.addLog(text);
          this.recordMainLog('WARN', `[grok stderr] ${text}`);
        }
      });

      grokProcess.on('error', (err) => {
        if (this.process !== grokProcess) return;
        this.addLog(`Grok process error: ${err.message}`);
        this.state = 'error';
        this.process = null;
        this.rl = null;
        this.clearPending(new Error(`Grok process error: ${err.message}`));
        this.emitState();
      });

      // ── ACP lifecycle handshake ──────────────────────────────────────
      // 1. Wait for grok process to be alive (it won't produce stdout
      //    until we send the first JSON-RPC request — protocol deadlock).
      {
        const graceMs = 10_000;
        const pollMs = 250;
        let waited = 0;
        while (waited < graceMs && !grokProcess.killed && grokProcess.exitCode === null) {
          await new Promise((r) => setTimeout(r, pollMs));
          waited += pollMs;
        }
        if (grokProcess.killed || grokProcess.exitCode !== null) {
          throw new Error(
            `Grok process exited with code ${grokProcess.exitCode} during startup ` +
              `(waited ${waited}ms)`
          );
        }
      }

      // 2. initialize
      this.addLog('grok alive — sending ACP initialize');
      const initResp = await this.acpRequest('initialize', {
        protocolVersion: 1,
        clientCapabilities: {
          fs: { readTextFile: false, writeTextFile: false },
          terminal: false,
        },
        _meta: {
          clientType: 'miqi-desktop',
          clientVersion: '0.1.0',
          startupHints: {
            nonInteractive: true,
            skipGitStatus: true,
            skipProjectLayout: true,
          },
        },
      });
      this.addLog(`grok initialized: ${JSON.stringify(initResp)}`);

      // 3. authenticate (grok reads MIQI_API_KEY from env)
      try {
        await this.acpRequest('authenticate', {
          methodId: 'xai.api_key',
          _meta: { headless: true },
        });
        this.addLog('grok authenticated');
      } catch {
        // If xai.api_key method is not advertised, try without auth
        this.addLog('grok auth skipped (may already be authenticated)');
      }

      // 4. Initial session
      try {
        await this.ensureCurrentSession();
        this.addLog(`grok session created: ${this.currentSessionId}`);
      } catch (err) {
        this.addLog(`grok session/new failed: ${err}`);
        // Non-fatal — sessions can be created lazily
      }

      this.state = 'running';
      this.emitState();

      // Handle unexpected exit
      grokProcess.on('close', (code) => {
        if (this.process !== grokProcess) return;
        if (this.state === 'stopping') return;
        this.addLog(`Grok process exited with code ${code}`);
        this.state = code === 0 ? 'stopped' : 'error';
        this.process = null;
        this.rl = null;
        this.sessionCache.clear();
        this.currentSessionId = null;
        this.clearPending(new Error('Grok process exited'));
        this.emitState();
      });

      this.addLog('grok bridge fully started');
    } catch (err) {
      this.addLog(`Failed to start grok bridge: ${err}`);

      if (this.process === startedProcess) {
        this.state = 'error';
        this.emitState();
      }

      if (startedReader) startedReader.close();
      if (this.rl === startedReader) this.rl = null;
      if (startedProcess && this.process === startedProcess) {
        try {
          startedProcess.stdin?.end();
        } catch {
          /* ignore */
        }
        startedProcess.kill('SIGTERM');
        this.process = null;
      }

      if (this.process === startedProcess || !this.process) {
        this.clearPending(new Error('Grok bridge initialization failed'));
      }
      throw err;
    }
  }

  async stop(): Promise<void> {
    if (!this.process) return;

    this.state = 'stopping';
    this.emitState();

    this.addLog('Grok bridge stopping');

    const proc = this.process;
    await new Promise<void>((resolve) => {
      let settled = false;
      const done = () => {
        if (settled) return;
        settled = true;
        clearTimeout(forceKillTimer);
        proc.removeListener('close', done);
        proc.removeListener('exit', done);
        if (this.process === proc) {
          this.process = null;
          this.rl = null;
          this.state = 'stopped';
          this.sessionCache.clear();
          this.currentSessionId = null;
          this.clearPending(new Error('Grok bridge stopped'));
          this.emitState();
        }
        resolve();
      };

      const forceKillTimer = setTimeout(() => {
        if (this.process === proc) proc.kill('SIGKILL');
      }, 5000);

      proc.once('close', done);
      proc.once('exit', done);

      try {
        proc.stdin?.end();
      } catch {
        /* ignore */
      }
      proc.kill('SIGTERM');
    });

    this.addLog('Grok bridge stopped');
  }

  // -----------------------------------------------------------------------
  // Send (mirrors BridgeManager.send with onEvent streaming callback)
  // -----------------------------------------------------------------------

  async send(
    method: string,
    params?: Record<string, unknown>,
    onEvent?: (type: string, data: unknown) => void
  ): Promise<unknown> {
    if (!this.isRunning()) {
      throw new Error('Grok bridge not running');
    }

    switch (method) {
      case 'chat.send':
        return this.handleChatSend(params ?? {}, onEvent);
      case 'chat.abort':
        return this.handleChatAbort(params ?? {});
      default:
        throw new Error(`Unknown grok method: ${method}`);
    }
  }

  // -----------------------------------------------------------------------
  // Permissions
  // -----------------------------------------------------------------------

  async resolvePermission(approvalId: string, outcome: string): Promise<void> {
    const entry = this.pendingPermissions.get(approvalId);
    if (!entry) {
      this.addLog(`[grok] No pending permission for ${approvalId}`);
      return;
    }
    this.pendingPermissions.delete(approvalId);

    const outcomeObj =
      outcome === 'allow_once'
        ? { optionId: 'allow_once' }
        : outcome === 'allow_always'
          ? { optionId: 'allow_always' }
          : outcome === 'reject_once'
            ? { optionId: 'deny_once' }
            : { cancelled: true };

    try {
      entry.resolve({ outcome: outcomeObj });
    } catch (err) {
      this.addLog(`[grok] resolvePermission error: ${err}`);
    }
  }

  // -----------------------------------------------------------------------
  // Private: ACP protocol helpers
  // -----------------------------------------------------------------------

  private async acpRequest(method: string, params?: unknown): Promise<unknown> {
    const id = this.nextId++;
    const request: AcpRequest = { jsonrpc: '2.0', id, method, params };
    const isStreaming = STREAMING_METHODS.has(method);
    const isLongRunning =
      method === 'session/new' || method === 'initialize' || method === 'authenticate';
    const timeoutMs = isStreaming
      ? STREAMING_TIMEOUT_MS
      : isLongRunning
        ? 60_000
        : DEFAULT_TIMEOUT_MS;
    const startMs = Date.now();

    const promise = new Promise<unknown>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        const duration = Date.now() - startMs;
        reject(new Error(`ACP request ${method} timed out after ${duration}ms`));
      }, timeoutMs);

      this.pending.set(id, {
        resolve: (value) => {
          clearTimeout(timer);
          this.pending.delete(id);
          resolve(value);
        },
        reject: (err) => {
          clearTimeout(timer);
          this.pending.delete(id);
          reject(err);
        },
      });
    });

    const stdin = this.process!.stdin!;
    if (!stdin.writable || stdin.destroyed) {
      throw new Error('Grok bridge not running');
    }

    stdin.write(JSON.stringify(request) + '\n', (err) => {
      if (err) {
        const entry = this.pending.get(id);
        if (entry) entry.reject(err);
      }
    });

    return promise;
  }

  private acpNotify(method: string, params?: unknown): void {
    if (!this.process?.stdin) return;
    const notification: AcpNotification = { jsonrpc: '2.0', method, params };
    this.process.stdin.write(JSON.stringify(notification) + '\n');
  }

  // -----------------------------------------------------------------------
  // Private: ACP message dispatch
  // -----------------------------------------------------------------------

  private handleAcpMessage(msg: AcpMessage): void {
    // Notifications (no id, has method)
    if (!('id' in msg) && 'method' in msg) {
      this.handleAcpNotification(msg as AcpNotification);
      return;
    }

    // Requests from grok → client (has id + method)
    if ('id' in msg && 'method' in msg) {
      this.handleAcpRequest(msg as AcpRequest);
      return;
    }

    // Responses (has id, no method)
    if ('id' in msg && !('method' in msg)) {
      this.handleAcpResponse(msg as AcpResponse);
      return;
    }
  }

  private handleAcpNotification(msg: AcpNotification): void {
    const params = msg.params as Record<string, unknown> | undefined;
    if (!params) return;

    switch (msg.method) {
      case 'session/update': {
        const update = params['update'] as Record<string, unknown> | undefined;
        const sessionUpdate = update?.['sessionUpdate'] as string | undefined;

        switch (sessionUpdate) {
          case 'agent_message_chunk': {
            const content = update?.['content'] as Record<string, unknown> | undefined;
            if (content?.['text']) {
              this.pendingPromptContent += content['text'] as string;
              this.emitBridgeEvent('chat:progress', {
                delta: content['text'],
                tool_hint: false,
                session_key: this.currentSessionKey,
              });
            }
            break;
          }
          case 'agent_thought_chunk': {
            const content = update?.['content'] as Record<string, unknown> | undefined;
            if (content?.['text']) {
              this.emitBridgeEvent('chat:progress', {
                delta: content['text'],
                tool_hint: false,
                stream: 'stderr',
                session_key: this.currentSessionKey,
              });
            }
            break;
          }
          case 'tool_call': {
            const title = (update?.['title'] as string) || 'Tool call';
            const toolCallId = update?.['toolCallId'] as string | undefined;
            this.emitBridgeEvent('chat:progress', {
              text: title,
              tool_hint: true,
              tool_call_id: toolCallId,
              session_key: this.currentSessionKey,
            });
            break;
          }
          case 'tool_call_update': {
            const contentArr = (update?.['content'] as unknown[]) ?? [];
            for (const block of contentArr) {
              const b = block as Record<string, unknown>;
              if (b['type'] === 'content') {
                const c = b['content'] as Record<string, unknown>;
                if (c['text']) {
                  this.emitBridgeEvent('chat:progress', {
                    delta: c['text'],
                    tool_hint: true,
                    tool_call_id: update?.['toolCallId'],
                    session_key: this.currentSessionKey,
                  });
                }
              }
            }
            break;
          }
          case 'plan':
          case 'task':
          case 'turn_completed': {
            // Resolve the pending session/prompt acpRequest so handleChatSend
            // can emit the 'final' event and re-enable the textarea.
            for (const [_id, entry] of this.pending) {
              entry.resolve({ stopReason: 'completed' });
              break; // only the first pending (session/prompt)
            }
            if (this.onEvent) {
              this.onEvent('final', {
                content: this.pendingPromptContent,
                aborted: false,
                session_key: this.currentSessionKey,
              });
            }
            break;
          }
          default:
            this.addLog(`[grok] Unhandled sessionUpdate: ${sessionUpdate}`);
            break;
        }
        break;
      }
      default:
        // Unknown notification — ignore
        break;
    }
  }

  private handleAcpRequest(msg: AcpRequest): void {
    switch (msg.method) {
      case 'session/request_permission': {
        const params = msg.params as Record<string, unknown>;
        const toolCall = params?.['toolCall'] as Record<string, unknown> | undefined;
        const optionsArr = (params?.['options'] as Array<Record<string, unknown>>) || [];

        const command =
          ((toolCall?.['rawInput'] as Record<string, unknown>)?.['command'] as string) || '';
        const title = (toolCall?.['title'] as string) || 'Tool call';
        const kind = (toolCall?.['kind'] as string) || 'unknown';

        const category =
          kind === 'execute' ? 'exec' : kind === 'write' ? 'file_write' : 'unknown_tool';

        const hasAllowAlways = optionsArr.some((o) => o['kind'] === 'allow_always');

        const approvalId = `grok:${msg.id}`;

        this.pendingPermissions.set(approvalId, {
          resolve: (v) => {
            // Send the JSON-RPC response back to grok
            const id = msg.id;
            delete (v as Record<string, unknown>).approval_id;
            this.process?.stdin?.write(JSON.stringify({ jsonrpc: '2.0', id, result: v }) + '\n');
          },
          reject: (_e) => {
            this.process?.stdin?.write(
              JSON.stringify({
                jsonrpc: '2.0',
                id: msg.id,
                result: { outcome: { cancelled: true } },
              }) + '\n'
            );
          },
        });

        this.emitBridgeEvent('approval:request', {
          approval_id: approvalId,
          command,
          description: title,
          category,
          allow_permanent: hasAllowAlways,
          details: toolCall,
        });
        break;
      }
      default:
        // Respond with method_not_found so grok doesn't hang
        this.process?.stdin?.write(
          JSON.stringify({
            jsonrpc: '2.0',
            id: msg.id,
            error: { code: -32601, message: `Method not found: ${msg.method}` },
          }) + '\n'
        );
        break;
    }
  }

  private handleAcpResponse(msg: AcpResponse): void {
    const id = msg.id;
    const entry = this.pending.get(id);

    if (!entry) {
      // May be a stale response — ignore
      return;
    }

    if (msg.error) {
      entry.reject(
        Object.assign(new Error(msg.error.message), {
          code: String(msg.error.code),
          data: msg.error.data,
        })
      );
    } else {
      entry.resolve(msg.result);
    }
  }

  // -----------------------------------------------------------------------
  // Private: chat handlers
  // -----------------------------------------------------------------------

  private async handleChatSend(
    params: Record<string, unknown>,
    onEvent?: (type: string, data: unknown) => void
  ): Promise<unknown> {
    const sessionKey = (params['session_key'] as string) || 'desktop:default';
    const content = (params['content'] as string) || '';
    const sessionId = await this.ensureCurrentSession(sessionKey);
    this.addLog('[grok] handleChatSend sessionKey=' + sessionKey + ' sessionId=' + sessionId);
    const projectCwd = (params['cwd'] as string) || this.projectRoot;
    this.currentSessionKey = sessionKey;
    // Reset accumulated content for this turn
    this.pendingPromptContent = '';

    // Set up the event bridge so ACP streaming events flow to the IPC handler
    this.onEvent = onEvent || null;

    try {
      const result = await this.acpRequest('session/prompt', {
        sessionId,
        prompt: [{ type: 'text', text: content }],
        _meta: { modelId: this.modelConfig?.modelId },
      });

      this.onEvent = null;

      // Emit final event
      if (onEvent) {
        const resp = result as Record<string, unknown> | undefined;
        const stopReason = resp?.['stopReason'] as string | undefined;
        onEvent('final', {
          content: this.pendingPromptContent,
          aborted: stopReason === 'cancelled',
          stop_reason: stopReason,
          session_key: sessionKey,
        });
      }

      return result;
    } catch (err: unknown) {
      this.onEvent = null;
      const msg = err instanceof Error ? err.message : String(err);
      if (onEvent) {
        onEvent('error', { message: msg, session_key: sessionKey });
      }
      throw err;
    }
  }

  private async handleChatAbort(params: Record<string, unknown>): Promise<unknown> {
    const sessionKey = (params['session_key'] as string) || 'desktop:default';
    const sessionId = this.sessionCache.get(sessionKey) || this.currentSessionId;

    if (!sessionId) {
      return { aborted: false, error: 'No active session' };
    }

    this.acpNotify('session/cancel', { sessionId });
    return { aborted: true, session_key: sessionId };
  }

  // -----------------------------------------------------------------------
  // Private: session management
  // -----------------------------------------------------------------------

  private async ensureCurrentSession(sessionKey?: string): Promise<string> {
    const key = sessionKey || 'desktop:default';
    const cached = this.sessionCache.get(key);
    if (cached) return cached;

    const result = (await this.acpRequest('session/new', {
      cwd: this.projectRoot,
      mcpServers: [],
    })) as Record<string, unknown>;

    const sessionId = (result?.['sessionId'] as string) || '';
    this.sessionCache.set(key, sessionId);
    this.currentSessionId = sessionId;
    return sessionId;
  }

  // -----------------------------------------------------------------------
  // Private: event bridge for chat.send streaming
  // -----------------------------------------------------------------------

  private onEvent: ((type: string, data: unknown) => void) | null = null;

  private emitBridgeEvent(type: string, data: unknown): void {
    // Route to the active chat.send onEvent callback (for streaming)
    if (this.onEvent) {
      if (type === 'chat:progress') {
        this.onEvent('progress', data);
      } else if (type === 'approval:request') {
        this.onEvent('approval_request', data);
      }
    }
  }

  // -----------------------------------------------------------------------
  // Private: helpers
  // -----------------------------------------------------------------------

  private clearPending(error: Error): void {
    for (const [_id, entry] of this.pending) {
      entry.reject(error);
    }
    this.pending.clear();
  }

  private addLog(message: string): void {
    this.logs.push(`[${new Date().toISOString()}] ${message}`);
    if (this.logs.length > this.maxLogs) {
      this.logs = this.logs.slice(-this.maxLogs);
    }
    this.emit('log', message);
  }

  private recordMainLog(level: string, message: string): void {
    writeMainProcessLog(level, message, this.projectRoot, 'grok-bridge');
  }

  private emitState(): void {
    this.emit('state', this.getStatus());
  }
}

// ---------------------------------------------------------------------------
// MiQi config reader (mirrors ipc/index.ts readLocalConfig)
// ---------------------------------------------------------------------------

function getMiQiConfigPath(): string {
  const miqiHome = process.env['MIQI_HOME']?.trim();
  // Mirror getConfigDir() in ipc/index.ts: MIQI_HOME → MIQI_HOME/config.json, unset → ~/.miqi/config.json
  return miqiHome ? join(miqiHome, 'config.json') : join(homedir(), '.miqi', 'config.json');
}

function readMiQiConfig(): Record<string, unknown> {
  const configPath = getMiQiConfigPath();
  try {
    if (!existsSync(configPath)) return {};
    const raw = readFileSync(configPath, 'utf8');
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return {};
  }
}
