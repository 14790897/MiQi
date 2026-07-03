import { electron } from '../../shared/electron';
import { spawnSync } from 'child_process';
import { existsSync } from 'fs';
import { homedir } from 'os';
import { join } from 'path';
import type { BridgeManager } from '../bridge';
import {
  IPC,
  ChatSendInput,
  ChatAbortInput,
  SessionGetInput,
  SessionDeleteInput,
  SessionClaimLegacyInput,
  ConfigUpdateInput,
  ProviderTestInput,
  ProviderUpdateInput,
  ChannelsUpdateInput,
  CronCreateInput,
  CronUpdateInput,
  CronToggleInput,
  CronDeleteInput,
  CronRunInput,
  CronRunsInput,
  MemoryGetInput,
  MemoryUpdateInput,
  MemoryLessonUnlearnInput,
  SkillsGetInput,
  FilesReadInput,
  FilesWriteInput,
  McpUpsertInput,
  McpDeleteInput,
  AgentSpawnInput,
  PermissionsUpdateInput,
  ThreadStartInput,
  ThreadReadInput,
  ThreadNameSetInput,
  TurnStartInput,
  TurnInterruptInput,
} from '../../shared/ipc';
import type { WslCheckResult, WslStatsResult } from '../../shared/ipc';

const { ipcMain, dialog } = electron;

export function registerIpcHandlers(bridge: BridgeManager): void {
  // -----------------------------------------------------------------------
  // Runtime
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.RUNTIME_START, async () => {
    await bridge.start();
    return bridge.getStatus();
  });

  ipcMain.handle(IPC.RUNTIME_STOP, async () => {
    await bridge.stop();
    return bridge.getStatus();
  });

  ipcMain.handle(IPC.RUNTIME_STATUS, () => {
    return bridge.getStatus();
  });

  ipcMain.handle(IPC.RUNTIME_LOGS, () => {
    return bridge.getLogs();
  });

  // -----------------------------------------------------------------------
  // Chat
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.CHAT_SEND, async (_event, payload: unknown) => {
    const input = ChatSendInput.parse(payload);

    const sender = _event.sender;
    const safeSend = (channel: string, data: unknown) => {
      if (!sender.isDestroyed()) {
        sender.send(channel, data);
      }
    };
    const result = await bridge.send(
      'chat.send',
      {
        content: input.content,
        session_key: input.session_key ?? 'desktop:default',
        thread_id: (input as any).thread_id ?? undefined,
      },
      (type: string, data: unknown) => {
        if (type === 'progress') {
          safeSend('chat:progress', data);
        } else if (type === 'final') {
          safeSend('chat:final', data);
        } else if (type === 'error') {
          safeSend('chat:error', data);
        } else if (type === 'aborted') {
          safeSend('chat:aborted', data);
        } else if (type === 'approval_request') {
          safeSend('approval:request', data);
        } else if (type === 'approval_cleared') {
          safeSend('approval:cleared', data);
        } else if (type === 'subagent_result') {
          safeSend('chat:subagent_result', data);
        } else if (type === 'chat:delta' || type === 'delta') {
          safeSend('chat:progress', data);
        }
      }
    );

    return result;
  });

  ipcMain.handle(IPC.CHAT_ABORT, async (_event, payload: unknown) => {
    const input = ChatAbortInput.parse(payload);
    return bridge.send('chat.abort', { session_key: input.session_key });
  });

  // -----------------------------------------------------------------------
  // Sessions
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.SESSIONS_LIST, async () => {
    const result = await bridge.sendSafe('sessions.list');
    if (result == null) return { sessions: [] };
    return result;
  });

  ipcMain.handle(IPC.SESSIONS_GET, async (_event, payload: unknown) => {
    const input = SessionGetInput.parse(payload);
    return bridge.sendSafe('sessions.get', { session_key: input.session_key });
  });

  ipcMain.handle(IPC.SESSIONS_DELETE, async (_event, payload: unknown) => {
    const input = SessionDeleteInput.parse(payload);
    return bridge.send('sessions.delete', { session_key: input.session_key });
  });

  ipcMain.handle(IPC.SESSIONS_ARCHIVE, async (_event, payload: unknown) => {
    const input = SessionGetInput.parse(payload);
    return bridge.sendSafe('sessions.archive', { session_key: input.session_key });
  });

  ipcMain.handle(IPC.SESSIONS_UNARCHIVE, async (_event, payload: unknown) => {
    const input = SessionGetInput.parse(payload);
    return bridge.sendSafe('sessions.unarchive', { session_key: input.session_key });
  });

  ipcMain.handle(IPC.SESSIONS_LIST_ARCHIVED, async () => {
    return bridge.sendSafe('sessions.list_archived');
  });

  ipcMain.handle(IPC.SESSIONS_GET_TRACKED_FILES, async (_event, payload: unknown) => {
    const input = SessionGetInput.parse(payload);
    return bridge.sendSafe('sessions.get_tracked_files', { session_key: input.session_key });
  });

  ipcMain.handle(IPC.SESSIONS_CLEAR_TRACKED_FILES, async (_event, payload: unknown) => {
    const input = SessionGetInput.parse(payload);
    return bridge.send('sessions.clear_tracked_files', { session_key: input.session_key });
  });

  ipcMain.handle(IPC.SESSIONS_CLAIM_LEGACY, async (_event, payload: unknown) => {
    const input = SessionClaimLegacyInput.parse(payload);
    return bridge.send('sessions.claim_legacy', { session_key: input.session_key });
  });

  // -----------------------------------------------------------------------
  // Config
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.CONFIG_GET, async () => {
    return bridge.sendSafe('config.get');
  });

  ipcMain.handle(IPC.CONFIG_UPDATE, async (_event, payload: unknown) => {
    const input = ConfigUpdateInput.parse(payload);
    return bridge.send('config.update', { config: input.config });
  });

  // -----------------------------------------------------------------------
  // Providers
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.PROVIDERS_LIST, async () => {
    return bridge.sendSafe('providers.list');
  });

  ipcMain.handle(IPC.PROVIDERS_TEST, async (_event, payload: unknown) => {
    const input = ProviderTestInput.parse(payload);
    return bridge.send('providers.test', input as Record<string, unknown>);
  });

  ipcMain.handle(IPC.PROVIDERS_UPDATE, async (_event, payload: unknown) => {
    const input = ProviderUpdateInput.parse(payload);
    return bridge.send('providers.update', input as Record<string, unknown>);
  });

  // -----------------------------------------------------------------------
  // Channels
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.CHANNELS_LIST, async () => {
    return bridge.sendSafe('channels.list');
  });

  ipcMain.handle(IPC.CHANNELS_UPDATE, async (_event, payload: unknown) => {
    const input = ChannelsUpdateInput.parse(payload);
    return bridge.send('channels.update', input as Record<string, unknown>);
  });

  // -----------------------------------------------------------------------
  // Python check — runs directly in main process, no bridge needed.
  // This must work BEFORE the bridge starts (e.g. during Setup Wizard).
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.PYTHON_CHECK, () => {
    const projectRoot = bridge.getProjectRoot();
    const issues: string[] = [];
    let pythonVersion = 'unknown';

    // Check for bundled miqi-bridge.exe first (packaged / production environment).
    // The bundled exe is a self-contained PyInstaller build that includes
    // Python 3.11+ and all dependencies (pydantic, httpx, loguru, …).
    // No system Python needed — if the exe exists, the environment is ready.
    const bundledBridge = join(process.resourcesPath, 'miqi-bridge.exe');
    if (existsSync(bundledBridge)) {
      // The bundled exe supports --check for optional validation.
      // PyInstaller onefile exe has a decompression delay on first run,
      // so we keep this lightweight and don't block the UI on it.
      // Primary signal: file exists → environment is considered OK.
      pythonVersion = 'bundled';
      // Try a quick --check to get the actual Python version (best-effort, non-blocking)
      try {
        const checkResult = spawnSync(bundledBridge, ['--check'], {
          timeout: 15000,
          encoding: 'utf8',
          windowsHide: true,
        });
        if (checkResult.status === 0 && checkResult.stdout) {
          try {
            const info = JSON.parse((checkResult.stdout as string).trim());
            if (info.python_version) pythonVersion = info.python_version;
            if (Array.isArray(info.issues) && info.issues.length > 0) {
              issues.push(...info.issues);
            }
          } catch {
            // JSON parse failed — not critical, bundled exe exists
          }
        }
        // If --check failed or not supported (old exe), still OK — file exists
      } catch {
        // --check timeout or error — not critical, bundled exe exists
      }
    } else {
      // Development environment: check system Python
      const candidates: string[][] = [];
      if (process.env['MIQI_PYTHON_PATH']) {
        candidates.push([process.env['MIQI_PYTHON_PATH']!]);
      }
      // uv
      const hasUvLock =
        existsSync(join(projectRoot, 'uv.lock')) || existsSync(join(projectRoot, 'pyproject.toml'));
      if (hasUvLock) {
        candidates.push(['uv', 'run', 'python']);
      }
      // .venv on Windows
      const venvWin = join(projectRoot, '.venv', 'Scripts', 'python.exe');
      if (existsSync(venvWin)) candidates.push([venvWin]);
      // .venv on Unix
      const venvUnix = join(projectRoot, '.venv', 'bin', 'python');
      if (existsSync(venvUnix)) candidates.push([venvUnix]);
      // system fallbacks
      candidates.push(['python3'], ['python']);

      let pythonCmd: string[] | null = null;
      for (const candidate of candidates) {
        try {
          const r = spawnSync(candidate[0], [...candidate.slice(1), '--version'], {
            timeout: 5000,
            encoding: 'utf8',
            windowsHide: true,
          });
          if (r.status === 0) {
            pythonCmd = candidate;
            const ver = (r.stdout || r.stderr || '').trim().replace(/^Python\s+/i, '');
            pythonVersion = ver;
            // Validate version >= 3.11
            const parts = ver.split('.').map(Number);
            if (parts[0] < 3 || (parts[0] === 3 && (parts[1] ?? 0) < 11)) {
              issues.push(`Python ${ver} is too old (need >= 3.11)`);
            }
            break;
          }
        } catch {
          // try next
        }
      }

      if (!pythonCmd) {
        issues.push('Python not found. Install Python >= 3.11 or set MIQI_PYTHON_PATH.');
        pythonVersion = 'not found';
      } else {
        // Check key MiQi dependencies
        const checkScript = `
import importlib, sys
for m in ("pydantic", "httpx", "loguru"):
    try:
        importlib.import_module(m)
    except ImportError:
        print("MISSING:" + m)
`;
        try {
          const r = spawnSync(pythonCmd[0], [...pythonCmd.slice(1), '-c', checkScript], {
            timeout: 8000,
            encoding: 'utf8',
            windowsHide: true,
          });
          const out = (r.stdout || '').trim();
          for (const line of out.split('\n')) {
            if (line.startsWith('MISSING:')) {
              issues.push(`Missing dependency: ${line.slice(8)}`);
            }
          }
        } catch {
          issues.push('Could not check MiQi dependencies');
        }
      }
    }

    const configExists = existsSync(join(homedir(), '.miqi', 'config.json'));

    return {
      ok: issues.length === 0,
      python_version: pythonVersion,
      issues,
      config_exists: configExists,
    };
  });

  // -----------------------------------------------------------------------
  // WSL2 check & install — Windows only, runs in main process.
  // Must work BEFORE the bridge starts (during Setup Wizard).
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.WSL_CHECK, () => {
    const isWindows = process.platform === 'win32';

    if (!isWindows) {
      return {
        isWindows: false,
        installed: true, // not relevant on non-Windows
        version: null,
        distros: [],
        defaultDistro: null,
        running: false,
      } satisfies WslCheckResult;
    }

    let installed = false;
    let version: string | null = null;
    let distros: string[] = [];
    let defaultDistro: string | null = null;
    let running = false;

    // Check if WSL is installed at all
    try {
      const statusResult = spawnSync('wsl', ['--status'], {
        timeout: 8000,
        encoding: 'buffer',
        windowsHide: true,
      });
      if (statusResult.status === 0) {
        installed = true;
        // WSL --status outputs UTF-16LE on Windows; decode accordingly
        let output = '';
        const buf = statusResult.stdout as Buffer | null;
        if (buf && buf.length > 1) {
          // Detect BOM or try UTF-16LE if there are many null bytes
          const hasBOM = buf[0] === 0xff && buf[1] === 0xfe;
          const nullRatio =
            buf.reduce((acc, b, i) => (i % 2 === 1 && b === 0 ? acc + 1 : acc), 0) /
            Math.floor(buf.length / 2);
          if (hasBOM || nullRatio > 0.3) {
            output = buf.toString('utf16le');
          } else {
            output = buf.toString('utf8');
          }
          // Strip BOM and trailing nulls
          output = output.replace(/^\uFEFF/, '').replace(/\0/g, '');
        }
        // Parse default distro line, e.g. "默认分发版: Ubuntu-22.04" or "Default Distribution: Ubuntu"
        const defaultMatch = output.match(/(?:默认分发|Default Distr?ibution)\s*[:：]\s*(.+)/i);
        if (defaultMatch) defaultDistro = defaultMatch[1].trim();
        // Parse default version, e.g. "默认版本: 2" or "Default Version: 2"
        const verMatch = output.match(/(?:默认版本|Default Version)\s*[:：]\s*(\d+)/i);
        if (verMatch) version = verMatch[1];
      }
    } catch {
      // WSL not installed
    }

    // List installed distros
    if (installed) {
      try {
        const listResult = spawnSync('wsl', ['--list', '--quiet'], {
          timeout: 8000,
          encoding: 'buffer',
          windowsHide: true,
        });
        if (listResult.status === 0) {
          const buf = listResult.stdout as Buffer | null;
          let raw = '';
          if (buf && buf.length > 1) {
            const hasBOM = buf[0] === 0xff && buf[1] === 0xfe;
            const nullRatio =
              buf.reduce((acc, b, i) => (i % 2 === 1 && b === 0 ? acc + 1 : acc), 0) /
              Math.floor(buf.length / 2);
            raw =
              hasBOM || nullRatio > 0.3
                ? buf
                    .toString('utf16le')
                    .replace(/^\uFEFF/, '')
                    .replace(/\0/g, '')
                : buf.toString('utf8').replace(/\0/g, '');
          }
          const lines = raw
            .split(/\r?\n/)
            .map((l) => l.trim())
            .filter(Boolean);
          distros = lines;
          // If no default found from --status, use first listed distro
          if (!defaultDistro && distros.length > 0) {
            defaultDistro = distros[0];
          }
        }
      } catch {
        // ignore
      }

      // Check if WSL is currently running (any WSL process active)
      try {
        const psResult = spawnSync('wsl', ['--list', '--running'], {
          timeout: 8000,
          encoding: 'buffer',
          windowsHide: true,
        });
        if (psResult.status === 0) {
          const buf = psResult.stdout as Buffer | null;
          let raw = '';
          if (buf && buf.length > 1) {
            const hasBOM = buf[0] === 0xff && buf[1] === 0xfe;
            const nullRatio =
              buf.reduce((acc, b, i) => (i % 2 === 1 && b === 0 ? acc + 1 : acc), 0) /
              Math.floor(buf.length / 2);
            raw =
              hasBOM || nullRatio > 0.3
                ? buf
                    .toString('utf16le')
                    .replace(/^\uFEFF/, '')
                    .replace(/\0/g, '')
                : buf.toString('utf8').replace(/\0/g, '');
          }
          const runningLines = raw
            .split(/\r?\n/)
            .map((l) => l.trim())
            .filter(Boolean);
          // Header line + at least one distro means something is running
          running = runningLines.length > 1;
        }
      } catch {
        // ignore
      }
    }

    return {
      isWindows: true,
      installed,
      version,
      distros,
      defaultDistro,
      running,
    } satisfies WslCheckResult;
  });

  ipcMain.handle(IPC.WSL_INSTALL, () => {
    if (process.platform !== 'win32') {
      return { launched: false, error: 'Not on Windows' };
    }
    try {
      // wsl --install requires admin; spawning with shell: true so it can
      // request elevation via UAC.  We detach since the installer may reboot.
      const child = spawnSync(
        'powershell.exe',
        ['-Command', 'Start-Process wsl -ArgumentList "--install" -Verb RunAs'],
        { timeout: 15000, encoding: 'utf8', shell: false }
      );
      if (child.error) {
        return { launched: false, error: child.error.message };
      }
      return { launched: true };
    } catch (e: any) {
      return { launched: false, error: e?.message ?? String(e) };
    }
  });

  // -----------------------------------------------------------------------
  // WSL stats — memory / CPU / disk usage (Windows only)
  // Optimized: fast stats in one WSL call; CPU via two-sample /proc/stat
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.WSL_GET_STATS, (_event, distroName?: string) => {
    if (process.platform !== 'win32') {
      return {
        ok: false,
        error: 'Not on Windows',
        distro: '',
        memory: { total_mb: 0, used_mb: 0, free_mb: 0, used_pct: 0 },
        cpu: { usage_pct: 0, cores: 0 },
        disk: { total_gb: 0, used_gb: 0, free_gb: 0, used_pct: 0 },
        uptime_sec: 0,
      };
    }

    // Determine target distro
    let targetDistro = distroName ?? '';
    if (!targetDistro) {
      try {
        const st = spawnSync('wsl', ['--status'], {
          timeout: 5000,
          encoding: 'buffer',
          windowsHide: true,
        });
        if (st.status === 0) {
          const buf = st.stdout as Buffer | null;
          let out = '';
          if (buf && buf.length > 1) {
            const hasBOM = buf[0] === 0xff && buf[1] === 0xfe;
            out =
              hasBOM ||
              buf.reduce(
                (a: number, b: number, i: number) => (i % 2 === 1 && b === 0 ? a + 1 : a),
                0
              ) /
                Math.floor(buf.length / 2) >
                0.3
                ? buf
                    .toString('utf16le')
                    .replace(/^\uFEFF/, '')
                    .replace(/\0/g, '')
                : buf.toString('utf8').replace(/\0/g, '');
          }
          const m = out.match(/(?:默认分发|Default Distr?ibution)\s*[:：]\s*(.+)/i);
          if (m) targetDistro = m[1].trim();
        }
      } catch {
        /* ignore */
      }

      if (!targetDistro) {
        try {
          const lr = spawnSync('wsl', ['--list', '--running', '--quiet'], {
            timeout: 5000,
            encoding: 'buffer',
            windowsHide: true,
          });
          if (lr.status === 0) {
            const buf = lr.stdout as Buffer | null;
            let out = '';
            if (buf && buf.length > 1) {
              const hasBOM = buf[0] === 0xff && buf[1] === 0xfe;
              out =
                hasBOM ||
                buf.reduce(
                  (a: number, b: number, i: number) => (i % 2 === 1 && b === 0 ? a + 1 : a),
                  0
                ) /
                  Math.floor(buf.length / 2) >
                  0.3
                  ? buf
                      .toString('utf16le')
                      .replace(/^\uFEFF/, '')
                      .replace(/\0/g, '')
                  : buf.toString('utf8').replace(/\0/g, '');
            }
            const lines = out
              .split(/\r?\n/)
              .map((l: string) => l.trim())
              .filter(Boolean);
            if (lines.length > 1) targetDistro = lines[1];
          }
        } catch {
          /* ignore */
        }
      }

      if (!targetDistro) {
        return {
          ok: false,
          error: 'No WSL distro found. Install a distro first.',
          distro: '',
          memory: { total_mb: 0, used_mb: 0, free_mb: 0, used_pct: 0 },
          cpu: { usage_pct: 0, cores: 0 },
          disk: { total_gb: 0, used_gb: 0, free_gb: 0, used_pct: 0 },
          uptime_sec: 0,
        };
      }
    }

    // Helper: run command in WSL (15s timeout, auto-detect UTF-8 vs UTF-16LE)
    const runInWsl = (cmd: string): { stdout: string; stderr: string; status: number | null } => {
      const r = spawnSync('wsl.exe', ['-d', targetDistro, '--', 'bash', '-c', cmd], {
        timeout: 15000,
        encoding: 'buffer', // read as buffer to auto-detect encoding
        windowsHide: true,
      });
      const decodeBuf = (buf: Buffer | string | null): string => {
        if (!buf || buf.length === 0) return '';
        if (typeof buf === 'string') return buf.trim();
        // Auto-detect: UTF-16LE BOM or high ratio of null bytes in odd positions → UTF-16LE
        if (buf.length >= 2 && buf[0] === 0xff && buf[1] === 0xfe) {
          return buf
            .toString('utf16le')
            .replace(/^\uFEFF/, '')
            .replace(/\0/g, '')
            .trim();
        }
        const nullRatio =
          buf.reduce((a, b, i) => (i % 2 === 1 && b === 0 ? a + 1 : a), 0) /
          Math.floor(buf.length / 2);
        if (nullRatio > 0.3) {
          return buf.toString('utf16le').replace(/\0/g, '').trim();
        }
        return buf.toString('utf8').replace(/\0/g, '').trim();
      };
      return {
        stdout: decodeBuf(r.stdout as Buffer | null),
        stderr: decodeBuf(r.stderr as Buffer | null),
        status: r.status,
      };
    };

    // --- Fast stats: memory + disk + cores + uptime in ONE WSL call ---
    // Each command outputs a prefixed line; awk ensures precise field extraction.
    const fastScript = [
      'free -m 2>/dev/null | awk \'/^Mem:/ {print "MEM:" $2 ":" $3 ":" $4 ":" $7}\'',
      'nproc 2>/dev/null | awk \'{print "CORES:" $1}\'',
      // Use --output for reliable column order: size, used, avail (in MB)
      'df --output=size,used,avail --block-size=1M / 2>/dev/null | awk \'NR==2 {printf "DISK:%d:%d:%d\\n", $1, $2, $3}\'',
      'awk \'{print "UPTIME:" $1}\' /proc/uptime 2>/dev/null',
    ].join('; ');
    const fastResult = runInWsl(fastScript);
    console.log(
      '[wsl:stats] fastScript status:',
      fastResult.status,
      'stdout:',
      JSON.stringify(fastResult.stdout)
    );

    // Parse results (each metric independent)
    let memory = { total_mb: 0, used_mb: 0, free_mb: 0, used_pct: 0 };
    let cores = 0;
    let disk = { total_gb: 0, used_gb: 0, free_gb: 0, used_pct: 0 };
    let uptimeSec = 0;

    if (fastResult.stdout) {
      const lines = fastResult.stdout.split('\n');

      // Memory: MEM:total:used:free:available
      const memLine = lines.find((l) => l.startsWith('MEM:'));
      if (memLine) {
        const parts = memLine.substring(4).split(':');
        const total = parseInt(parts[0], 10);
        const used = parseInt(parts[1], 10);
        if (!Number.isNaN(total) && total > 0) {
          memory = {
            total_mb: total,
            used_mb: Number.isNaN(parseInt(parts[1], 10)) ? 0 : parseInt(parts[1], 10),
            free_mb: Number.isNaN(parseInt(parts[2], 10)) ? 0 : parseInt(parts[2], 10),
            used_pct: Math.round((used / total) * 100),
          };
        }
      }

      // Cores
      const coresLine = lines.find((l) => l.startsWith('CORES:'));
      if (coresLine) {
        cores = parseInt(coresLine.substring(7), 10) || 0;
      }

      // Disk: DISK:total_MB:used_MB:free_MB (from --output --block-size=1M)
      const diskLine = lines.find((l) => l.startsWith('DISK:'));
      if (diskLine) {
        const parts = diskLine.substring(5).split(':');
        const totalMb = parseInt(parts[0] || '0', 10);
        const usedMb = parseInt(parts[1] || '0', 10);
        const freeMb = parseInt(parts[2] || '0', 10);
        if (!Number.isNaN(totalMb) && totalMb > 0 && usedMb <= totalMb) {
          disk = {
            total_gb: Math.round((totalMb / 1024) * 10) / 10,
            used_gb: Math.round((usedMb / 1024) * 10) / 10,
            free_gb: Math.round((freeMb / 1024) * 10) / 10,
            used_pct: Math.round((usedMb / totalMb) * 100),
          };
        }
      }

      // Uptime
      const uptimeLine = lines.find((l) => l.startsWith('UPTIME:'));
      if (uptimeLine) {
        uptimeSec = parseFloat(uptimeLine.substring(8)) || 0;
      }
    }

    // --- Fallback: if combined script failed, try individual commands ---
    if (memory.total_mb === 0) {
      console.log('[wsl:stats] memory from fastScript empty, trying fallback');
      const memRaw = runInWsl('cat /proc/meminfo');
      if (memRaw.stdout) {
        const mt = memRaw.stdout.match(/MemTotal:\s*(\d+)/);
        const mu = memRaw.stdout.match(/MemAvailable:\s*(\d+)/);
        if (mt?.[1]) {
          const totalKb = parseInt(mt[1], 10);
          const availKb = mu?.[1] ? parseInt(mu[1], 10) : totalKb;
          memory = {
            total_mb: Math.round(totalKb / 1024),
            used_mb: Math.round((totalKb - availKb) / 1024),
            free_mb: Math.round(availKb / 1024),
            used_pct: Math.round(((totalKb - availKb) / totalKb) * 100),
          };
        }
      }
    }

    if (cores === 0) {
      const cpuInfo = runInWsl('grep -c ^processor /proc/cpuinfo 2>/dev/null');
      if (cpuInfo.stdout) cores = parseInt(cpuInfo.stdout, 10) || 0;
    }

    if (disk.total_gb === 0) {
      // Fallback: use df --output for reliable column order (in MB)
      const dfRaw = runInWsl('df --output=size,used,avail --block-size=1M / 2>/dev/null');
      console.log('[wsl:stats] disk fallback raw:', JSON.stringify(dfRaw.stdout));
      if (dfRaw.stdout) {
        const lines2 = dfRaw.stdout.split('\n').filter(Boolean);
        if (lines2.length >= 2) {
          const vals = lines2[1].trim().split(/\s+/).map(Number);
          const t = vals[0],
            u = vals[1],
            f = vals[2];
          if (!Number.isNaN(t) && t > 0 && !Number.isNaN(u) && u <= t) {
            disk = {
              total_gb: Math.round((t / 1024) * 10) / 10,
              used_gb: Math.round((u / 1024) * 10) / 10,
              free_gb: Math.round(((f || 0) / 1024) * 10) / 10,
              used_pct: Math.round((u / t) * 100),
            };
          }
        }
      }
    }

    if (uptimeSec === 0) {
      const upRaw = runInWsl('cat /proc/uptime');
      if (upRaw.stdout) uptimeSec = parseFloat(upRaw.stdout.trim().split(/\s+/)[0]) || 0;
    }

    // --- CPU usage: two /proc/stat samples with 0.5s delay ---
    // Uses bash built-ins + awk; no external dependencies beyond bash.
    let cpuUsagePct = 0;
    const cpuScript = [
      "S1=$(awk 'NR==1 {print $2, $3, $4, $5, $6, $7, $8}' /proc/stat)",
      'sleep 0.5',
      "S2=$(awk 'NR==1 {print $2, $3, $4, $5, $6, $7, $8}' /proc/stat)",
      '# Compute total and idle diff',
      'set -- $S1; T1=$(( $2 + $3 + $4 + $5 + $6 + $7 + $8 )); I1=$5',
      'set -- $S2; T2=$(( $2 + $3 + $4 + $5 + $6 + $7 + $8 )); I2=$5',
      'TD=$(( T2 - T1 )); ID=$(( I2 - I1 ))',
      'if [ $TD -gt 0 ]; then echo $(( 100 * (TD - ID) / TD )); else echo "0"; fi',
    ].join('; ');
    const cpuResult = runInWsl(cpuScript);
    if (cpuResult.status === 0 && cpuResult.stdout) {
      const pct = parseInt(cpuResult.stdout.trim(), 10);
      if (!Number.isNaN(pct)) {
        cpuUsagePct = Math.min(Math.max(pct, 0), 100);
      }
    }

    return {
      ok: true,
      distro: targetDistro,
      memory,
      cpu: { usage_pct: cpuUsagePct, cores: Math.max(cores, 0) },
      disk,
      uptime_sec: Math.round(uptimeSec),
    } satisfies WslStatsResult;
  });

  // Export default WSL distro to a tar file for sandbox use.
  // This creates a dedicated sandbox distro that avoids requiring sudo
  // because the sandbox uses --unshare-user-try (user namespace).
  ipcMain.handle(IPC.WSL_EXPORT_DISTRO, async (_, distroName: string) => {
    if (process.platform !== 'win32') {
      return { exported: false, distro: null, tarPath: null, error: 'Not on Windows' };
    }
    if (!distroName) {
      return { exported: false, distro: null, tarPath: null, error: 'No distro to export' };
    }
    try {
      // Export the specified distro to a tar file
      const exportDir = process.env['LOCALAPPDATA'] || process.env['APPDATA'] || '';
      if (!exportDir) {
        return { exported: false, distro: null, tarPath: null, error: 'LOCALAPPDATA not found' };
      }
      const tarPath = join(exportDir, `${distroName}.tar`);
      const child = spawnSync(
        'wsl.exe',
        ['-d', distroName, '--export', distroName, '-t', tarPath],
        { timeout: 120000, encoding: 'utf8', windowsHide: true }
      );
      if (child.status !== 0) {
        return {
          exported: false,
          distro: null,
          tarPath: null,
          error: child.stderr || 'Export failed',
        };
      }
      return { exported: true, distro: distroName, tarPath, error: null };
    } catch (e: any) {
      return { exported: false, distro: null, tarPath: null, error: e?.message ?? String(e) };
    }
  });

  // Import a dedicated sandbox distro from a tar file.
  // The imported distro is used exclusively by the sandbox,
  // avoiding sudo requirement because sandbox uses --unshare-user-try.
  ipcMain.handle(
    IPC.WSL_IMPORT_DISTRO,
    async (_, options: { tarPath: string; distroName: string }) => {
      if (process.platform !== 'win32') {
        return { imported: false, distro: null, installLocation: null, error: 'Not on Windows' };
      }
      const { tarPath, distroName } = options;
      if (!tarPath) {
        return {
          imported: false,
          distro: null,
          installLocation: null,
          error: 'No tar file path provided',
        };
      }
      if (!distroName) {
        return {
          imported: false,
          distro: null,
          installLocation: null,
          error: 'No distro name provided',
        };
      }
      try {
        // Import the tar file as a new dedicated sandbox distro
        // Use LOCALAPPDATA as install location to avoid requiring admin
        const installLocation = join(
          process.env['LOCALAPPDATA'] || process.env['APPDATA'] || '',
          'MiQi Sandbox'
        );
        const child = spawnSync(
          'wsl.exe',
          [
            '--import',
            distroName,
            installLocation,
            tarPath,
            '--version',
            '2', // Always WSL2 for sandbox
          ],
          { timeout: 120000, encoding: 'utf8', windowsHide: true }
        );
        if (child.status !== 0) {
          return {
            imported: false,
            distro: null,
            installLocation: null,
            error: child.stderr || 'Import failed',
          };
        }
        return { imported: true, distroName, installLocation, error: null };
      } catch (e: any) {
        return {
          imported: false,
          distro: null,
          installLocation: null,
          error: e?.message ?? String(e),
        };
      }
    }
  );

  // -----------------------------------------------------------------------
  // Dialog (file open for workspace)
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.DIALOG_OPEN_FILE, async () => {
    const result = await dialog.showOpenDialog({
      properties: ['openFile', 'openDirectory'],
    });
    return result.canceled ? null : (result.filePaths[0] ?? null);
  });

  // -----------------------------------------------------------------------
  // Approvals
  // -----------------------------------------------------------------------
  ipcMain.handle('approvals:list', async () => {
    return bridge.sendSafe('approvals.list');
  });

  ipcMain.handle('approvals:resolve', async (_event, payload: unknown) => {
    const p = payload as { approval_id: string; decision: string };
    return bridge.send('approvals.resolve', p as Record<string, unknown>);
  });

  ipcMain.handle('approvals:clear_permanent', async (_event, payload: unknown) => {
    const p = (payload ?? {}) as { pattern?: string };
    return bridge.send('approvals.clear_permanent', p as Record<string, unknown>);
  });

  ipcMain.handle('approvals:add_permanent', async (_event, payload: unknown) => {
    const p = payload as { pattern: string };
    return bridge.send('approvals.add_permanent', p as Record<string, unknown>);
  });

  ipcMain.handle('approvals:history', async (_event, payload: unknown) => {
    const p = (payload ?? {}) as { limit?: number };
    return bridge.sendSafe('approvals.history', p as Record<string, unknown>);
  });

  // -----------------------------------------------------------------------
  // Cron
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.CRON_LIST, async () => {
    return bridge.sendSafe('cron.list');
  });

  ipcMain.handle(IPC.CRON_CREATE, async (_event, payload: unknown) => {
    const input = CronCreateInput.parse(payload);
    return bridge.send('cron.create', input as Record<string, unknown>);
  });

  ipcMain.handle(IPC.CRON_UPDATE, async (_event, payload: unknown) => {
    const input = CronUpdateInput.parse(payload);
    return bridge.send('cron.update', input as Record<string, unknown>);
  });

  ipcMain.handle(IPC.CRON_DELETE, async (_event, payload: unknown) => {
    const input = CronDeleteInput.parse(payload);
    return bridge.send('cron.delete', input as Record<string, unknown>);
  });

  ipcMain.handle(IPC.CRON_TOGGLE, async (_event, payload: unknown) => {
    const input = CronToggleInput.parse(payload);
    return bridge.send('cron.toggle', input as Record<string, unknown>);
  });

  ipcMain.handle(IPC.CRON_RUN, async (_event, payload: unknown) => {
    const input = CronRunInput.parse(payload);
    return bridge.send('cron.run', input as Record<string, unknown>);
  });

  ipcMain.handle(IPC.CRON_RUNS, async (_event, payload: unknown) => {
    const input = CronRunsInput.parse(payload ?? {});
    return bridge.sendSafe('cron.runs', input as Record<string, unknown>);
  });

  // -----------------------------------------------------------------------
  // Memory
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.MEMORY_LIST, async () => {
    return bridge.sendSafe('memory.list');
  });

  ipcMain.handle(IPC.MEMORY_GET, async (_event, payload: unknown) => {
    const input = MemoryGetInput.parse(payload);
    return bridge.sendSafe('memory.get', input as Record<string, unknown>);
  });

  ipcMain.handle(IPC.MEMORY_UPDATE, async (_event, payload: unknown) => {
    const input = MemoryUpdateInput.parse(payload);
    return bridge.send('memory.update', input as Record<string, unknown>);
  });

  ipcMain.handle(IPC.MEMORY_LESSONS, async () => {
    return bridge.sendSafe('memory.lessons');
  });

  ipcMain.handle(IPC.MEMORY_LESSON_UNLEARN, async (_event, payload: unknown) => {
    const input = MemoryLessonUnlearnInput.parse(payload);
    return bridge.send('memory.lesson.unlearn', input as Record<string, unknown>);
  });

  ipcMain.handle(IPC.MEMORY_DELETE, async (_event, payload: unknown) => {
    const p = payload as { path: string };
    return bridge.send('memory.delete', p as Record<string, unknown>);
  });

  // -----------------------------------------------------------------------
  // Experience
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.EXPERIENCE_LIST, async (_event, payload: unknown) => {
    return bridge.sendSafe('experience:list', payload as Record<string, unknown>);
  });

  ipcMain.handle(IPC.EXPERIENCE_DELETE, async (_event, payload: unknown) => {
    return bridge.send('experience:delete', payload as Record<string, unknown>);
  });

  ipcMain.handle(IPC.EXPERIENCE_TOGGLE, async (_event, payload: unknown) => {
    return bridge.send('experience:toggle', payload as Record<string, unknown>);
  });

  ipcMain.handle(IPC.EXPERIENCE_SEARCH, async (_event, payload: unknown) => {
    return bridge.sendSafe('experience:search', payload as Record<string, unknown>);
  });

  // -----------------------------------------------------------------------
  // Skills
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.SKILLS_LIST, async () => {
    return bridge.sendSafe('skills.list');
  });

  ipcMain.handle(IPC.SKILLS_GET, async (_event, payload: unknown) => {
    const input = SkillsGetInput.parse(payload);
    return bridge.sendSafe('skills.get', input as Record<string, unknown>);
  });

  ipcMain.handle(IPC.SKILLS_OPEN_FOLDER, async (_event, payload: unknown) => {
    const p = payload as { name: string };
    return bridge.send('skills.open_folder', p as Record<string, unknown>);
  });

  ipcMain.handle(IPC.SKILLS_CREATE, async (_event, payload: unknown) => {
    const p = payload as { name: string; description?: string };
    return bridge.send('skills.create', p as Record<string, unknown>);
  });

  ipcMain.handle(IPC.SKILLS_UPLOAD, async (_event, payload: unknown) => {
    const p = payload as { name: string; content: string };
    return bridge.send('skills.upload', p as Record<string, unknown>);
  });

  ipcMain.handle(IPC.SKILLS_DELETE, async (_event, payload: unknown) => {
    const p = payload as { name: string };
    return bridge.send('skills.delete', p as Record<string, unknown>);
  });

  // -----------------------------------------------------------------------
  // Files (Workspace Editor)
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.FILES_TREE, async () => {
    return bridge.sendSafe('files.tree');
  });

  ipcMain.handle(IPC.FILES_READ, async (_event, payload: unknown) => {
    const input = FilesReadInput.parse(payload);
    return bridge.sendSafe('files.read', input as Record<string, unknown>);
  });

  ipcMain.handle(IPC.FILES_WRITE, async (_event, payload: unknown) => {
    const input = FilesWriteInput.parse(payload);
    return bridge.send('files.write', input as Record<string, unknown>);
  });

  ipcMain.handle(IPC.FILES_DELETE, async (_event, payload: unknown) => {
    const p = payload as { path: string };
    return bridge.send('files.delete', p as Record<string, unknown>);
  });

  ipcMain.handle(IPC.FILES_DIFF, async (_event, payload: unknown) => {
    const p = payload as { path: string; session_key?: string };
    return bridge.sendSafe('files.diff', p as Record<string, unknown>);
  });

  ipcMain.handle(IPC.FILES_REVERT, async (_event, payload: unknown) => {
    const p = payload as { path: string; session_key?: string };
    return bridge.send('files.revert', p as Record<string, unknown>);
  });

  ipcMain.handle(IPC.FILES_ACCEPT, async (_event, payload: unknown) => {
    const p = payload as { path: string; session_key?: string };
    return bridge.send('files.accept', p as Record<string, unknown>);
  });

  // -----------------------------------------------------------------------
  // MCP
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.MCP_LIST, async () => {
    return bridge.sendSafe('mcp.list');
  });

  ipcMain.handle(IPC.MCP_UPSERT, async (_event, payload: unknown) => {
    const input = McpUpsertInput.parse(payload);
    return bridge.send('mcp.upsert', input as Record<string, unknown>);
  });

  ipcMain.handle(IPC.MCP_DELETE, async (_event, payload: unknown) => {
    const input = McpDeleteInput.parse(payload);
    return bridge.send('mcp.delete', input as Record<string, unknown>);
  });

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
      provider_name: string;
      api_key?: string | null;
      api_base?: string | null;
      model?: string | null;
      agent_name?: string | null;
      workspace?: string | null;
      soul_preset?: string | null;
      brave_api_key?: string | null;
      search_provider?: string | null;
      search_ollama_api_base?: string | null;
      search_ollama_api_key?: string | null;
      fetch_provider?: string | null;
      fetch_ollama_api_base?: string | null;
      fetch_ollama_api_key?: string | null;
      papers_provider?: string | null;
      semantic_scholar_api_key?: string | null;
    };
    const configDir = join(homedir(), '.miqi');
    const configPath = join(configDir, 'config.json');

    // Load existing config if it exists, so we don't clobber other keys
    let existing: Record<string, unknown> = {};
    try {
      const { readFileSync } = require('fs') as typeof import('fs');
      if (existsSync(configPath)) {
        existing = JSON.parse(readFileSync(configPath, 'utf8'));
      }
    } catch {
      // Start fresh
    }

    // Deep-merge provider key
    const providers = (existing['providers'] as Record<string, unknown> | undefined) ?? {};
    providers[provider_name] = {
      ...((providers[provider_name] as Record<string, unknown> | undefined) ?? {}),
      ...(api_key ? { apiKey: api_key } : {}),
      ...(api_base ? { apiBase: api_base } : {}),
    };
    existing['providers'] = providers;

    // Set agent defaults (model, name, workspace, soulPreset)
    const agents = (existing['agents'] as Record<string, unknown> | undefined) ?? {};
    const defaults = (agents['defaults'] as Record<string, unknown> | undefined) ?? {};
    if (model) defaults['model'] = model;
    if (agent_name) defaults['name'] = agent_name;
    if (workspace) defaults['workspace'] = workspace;
    if (soul_preset) defaults['soulPreset'] = soul_preset;
    agents['defaults'] = defaults;
    existing['agents'] = agents;

    // Web tools
    const tools = (existing['tools'] as Record<string, unknown> | undefined) ?? {};
    const web = (tools['web'] as Record<string, unknown> | undefined) ?? {};

    // Web Search
    const search = (web['search'] as Record<string, unknown> | undefined) ?? {};
    if (search_provider) search['provider'] = search_provider;
    if (brave_api_key) search['apiKey'] = brave_api_key;
    if (search_ollama_api_base) search['ollamaApiBase'] = search_ollama_api_base;
    if (search_ollama_api_key) search['ollamaApiKey'] = search_ollama_api_key;
    web['search'] = search;

    // Web Fetch
    const fetch = (web['fetch'] as Record<string, unknown> | undefined) ?? {};
    if (fetch_provider) fetch['provider'] = fetch_provider;
    if (fetch_ollama_api_base) fetch['ollamaApiBase'] = fetch_ollama_api_base;
    if (fetch_ollama_api_key) fetch['ollamaApiKey'] = fetch_ollama_api_key;
    web['fetch'] = fetch;

    tools['web'] = web;

    // Papers
    const papers = (tools['papers'] as Record<string, unknown> | undefined) ?? {};
    if (papers_provider) papers['provider'] = papers_provider;
    if (semantic_scholar_api_key) papers['semanticScholarApiKey'] = semantic_scholar_api_key;
    tools['papers'] = papers;

    existing['tools'] = tools;

    // Ensure directory exists
    const { mkdirSync, writeFileSync } = require('fs') as typeof import('fs');
    mkdirSync(configDir, { recursive: true });
    writeFileSync(configPath, JSON.stringify(existing, null, 2), 'utf8');

    return { saved: true, path: configPath };
  });

  // ---------------------------------------------------------------------------
  // Agents (Phase 2)
  // ---------------------------------------------------------------------------
  ipcMain.handle(IPC.AGENT_LIST, async (_event, payload: unknown) => {
    const p = (payload ?? {}) as { session_key?: string };
    return bridge.sendSafe('agent.list', { session_key: p.session_key ?? 'desktop:default' });
  });

  ipcMain.handle(IPC.AGENT_SPAWN, async (_event, payload: unknown) => {
    const input = AgentSpawnInput.parse(payload);
    return bridge.sendSafe('agent.spawn', {
      agent_type: input.agent_type,
      task: input.task,
      label: input.label,
    });
  });

  ipcMain.handle(IPC.AGENT_KILL, async (_event, payload: unknown) => {
    const { agent_id } = payload as { agent_id: string };
    return bridge.sendSafe('agent.kill', { agent_id });
  });

  // ---------------------------------------------------------------------------
  // Plan (Phase 2)
  // ---------------------------------------------------------------------------
  ipcMain.handle(IPC.PLAN_GET, async (_event, payload: unknown) => {
    const { thread_id } = payload as { thread_id: string };
    return bridge.sendSafe('plan.get', { thread_id });
  });

  // ---------------------------------------------------------------------------
  // Permissions (Phase 3)
  // ---------------------------------------------------------------------------
  ipcMain.handle(IPC.PERMISSIONS_GET, async () => {
    return bridge.sendSafe('permissions.get');
  });

  ipcMain.handle(IPC.PERMISSIONS_UPDATE, async (_event, payload: unknown) => {
    const input = PermissionsUpdateInput.parse(payload);
    return bridge.sendSafe('permissions.update', { config: input });
  });

  ipcMain.handle(IPC.PERMISSIONS_PERMANENT_ADD, async (_event, payload: unknown) => {
    const { pattern } = payload as { pattern: string };
    return bridge.sendSafe('permissions.permanent.add', { pattern });
  });

  ipcMain.handle(IPC.PERMISSIONS_PERMANENT_REMOVE, async (_event, payload: unknown) => {
    const { pattern } = payload as { pattern: string };
    return bridge.sendSafe('permissions.permanent.remove', { pattern });
  });

  // ---------------------------------------------------------------------------
  // Plugins (Phase 4)
  // ---------------------------------------------------------------------------
  ipcMain.handle(IPC.PLUGINS_LIST, async () => {
    return bridge.sendSafe('plugins.list');
  });

  ipcMain.handle(IPC.PLUGINS_INSTALL, async (_event, payload: unknown) => {
    const { name } = payload as { name: string };
    return bridge.sendSafe('plugins.install', { name });
  });

  ipcMain.handle(IPC.PLUGINS_UNINSTALL, async (_event, payload: unknown) => {
    const { name } = payload as { name: string };
    return bridge.sendSafe('plugins.uninstall', { name });
  });

  ipcMain.handle(IPC.PLUGINS_TOGGLE, async (_event, payload: unknown) => {
    const { name, enabled } = payload as { name: string; enabled: boolean };
    return bridge.sendSafe('plugins.toggle', { name, enabled });
  });

  // -- Threads (Phase 36+) --------------------------------------------------
  ipcMain.handle(IPC.THREAD_START, async (_event, payload: unknown) => {
    const input = ThreadStartInput.parse(payload);
    const sender = _event.sender;
    const safeSend = (channel: string, data: unknown) => {
      if (!sender.isDestroyed()) sender.send(channel, data);
    };
    return bridge.send(
      'thread/start',
      {
        title: input.title,
        sessionKey: input.session_key,
        threadId: input.thread_id,
      },
      (type: string, data: unknown) => {
        if (type === 'thread/started') {
          safeSend('thread:started', data);
        }
      }
    );
  });

  ipcMain.handle(IPC.THREAD_LIST, async (_event, payload: unknown) => {
    const p = (payload ?? {}) as { session_key?: string };
    return bridge.sendSafe('thread/list', { sessionId: p.session_key });
  });

  ipcMain.handle(IPC.THREAD_READ, async (_event, payload: unknown) => {
    const input = ThreadReadInput.parse(payload);
    return bridge.sendSafe('thread/read', {
      threadId: input.thread_id,
      sessionId: input.session_key,
    });
  });

  ipcMain.handle(IPC.THREAD_NAME_SET, async (_event, payload: unknown) => {
    const input = ThreadNameSetInput.parse(payload);
    return bridge.send('thread/name/set', {
      threadId: input.thread_id,
      name: input.name,
      sessionId: input.session_key,
    });
  });

  // -- Turns (Phase 37+) ----------------------------------------------------
  ipcMain.handle(IPC.TURN_START, async (_event, payload: unknown) => {
    const input = TurnStartInput.parse(payload);
    const sender = _event.sender;
    const safeSend = (channel: string, data: unknown) => {
      if (!sender.isDestroyed()) sender.send(channel, data);
    };
    return bridge.send(
      'turn/start',
      {
        threadId: input.thread_id,
        input: [{ type: 'message', content: input.content }],
        model: input.model,
        effort: input.effort,
      },
      (type: string, data: unknown) => {
        if (type === 'error') {
          safeSend('chat:error', data);
        } else if (
          type === 'turn/completed' ||
          type === 'turn/started' ||
          type === 'item/started' ||
          type === 'item/completed'
        ) {
          safeSend(`turn:event`, data);
        } else if (type === 'approval_request') {
          safeSend('approval:request', data);
        } else if (type === 'approval_cleared') {
          safeSend('approval:cleared', data);
        } else {
          safeSend('chat:progress', data);
        }
      }
    );
  });

  ipcMain.handle(IPC.TURN_INTERRUPT, async (_event, payload: unknown) => {
    const input = TurnInterruptInput.parse(payload);
    return bridge.send('turn/interrupt', {
      threadId: input.thread_id,
      turnId: input.turn_id,
    });
  });
}
