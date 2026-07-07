/**
 * Shared Electron main-process file logger.
 *
 * Both `index.ts` (writeElectronLog) and `bridge.ts` (recordMainLog) delegate
 * to this module so that desktop and bridge logs are colocated under
 * `workspace/logs/` with the same retention and pruning behavior.
 *
 * Key design decisions (from CodeRabbit review):
 * - Single shared implementation — no duplicated logic between bridge/index.
 * - Safe I/O: all file operations are wrapped in try/catch so logging
 *   failures never crash unrelated code paths.
 * - Cached log directory: `mkdirSync` is called once, not on every write.
 * - Throttled cleanup: old-log deletion runs every 100 writes, not every write.
 * - Static `fs` imports only — no dynamic `require('fs')`.
 * - Basic redaction for secrets that may appear in console output.
 */
import {
  appendFileSync,
  mkdirSync,
  readdirSync,
  statSync,
  unlinkSync,
} from 'fs';
import { join } from 'path';

const RETAIN_DAYS = 7;
const CLEANUP_INTERVAL = 100;
const CUTOFF_MS = RETAIN_DAYS * 86_400_000;

// Basic redaction patterns for secrets that may leak via console output
const REDACT_RE = [
  // Colon-separated: Authorization: Bearer sk-xxx (multi-word value)
  /("?\w*(?:api[_-]?key|token|secret|authorization|password)\w*"?)\s*:\s*"?([^"}\s,;]+(?:\s+[^"}\s,;]+)*)"?/gi,
  // Equals-separated: api_key=sk-xxx (single-word value only)
  /("?\w*(?:api[_-]?key|token|secret|authorization|password)\w*"?)\s*=\s*"?([^"}\s,;]+)"?/gi,
];

function redactMessage(message: string): string {
  let result = message;
  for (const re of REDACT_RE) {
    result = result.replace(re, '$1=[REDACTED]');
  }
  return result;
}

let _logDir: string | null = null;
let _writeCounter = 0;

/**
 * Resolve and cache the workspace/logs directory.
 * Falls back to `process.cwd()/workspace/logs` if no explicit root is given.
 * Ensures the directory exists on first call.
 */
function resolveLogDir(projectRoot?: string): string {
  if (_logDir) return _logDir;
  const root = projectRoot ?? process.cwd();
  const dir = join(root, 'workspace', 'logs');
  try {
    mkdirSync(dir, { recursive: true });
  } catch {
    // If mkdir fails, still return the path — writes will be caught by try/catch
  }
  _logDir = dir;
  return dir;
}

function cleanupOldLogs(logDir: string): void {
  const cutoff = Date.now() - CUTOFF_MS;
  try {
    for (const name of readdirSync(logDir)) {
      if (!name.endsWith('.log')) continue;
      const fp = join(logDir, name);
      try {
        if (statSync(fp).mtimeMs < cutoff) unlinkSync(fp);
      } catch {
        /* skip per-file errors */
      }
    }
  } catch {
    /* ignore if log dir doesn't exist */
  }
}

/**
 * Append a single log line to `electron-main-{date}.log`.
 *
 * @param level   Log level string (INFO, WARN, ERROR)
 * @param message Log message (will be redacted for secrets)
 * @param projectRoot  Optional project root for resolving the log directory.
 *                     Only used on the very first call; cached afterwards.
 */
export function writeMainProcessLog(
  level: string,
  message: string,
  projectRoot?: string,
): void {
  try {
    const logDir = resolveLogDir(projectRoot);
    const dateStr = new Date().toISOString().slice(0, 10);
    const logPath = join(logDir, `electron-main-${dateStr}.log`);
    const timestamp = new Date().toISOString();
    appendFileSync(
      logPath,
      `[${timestamp}] [${level}] ${redactMessage(message)}\n`,
      'utf8',
    );
    // Throttled cleanup — run every N writes
    _writeCounter += 1;
    if (_writeCounter % CLEANUP_INTERVAL === 0) {
      cleanupOldLogs(logDir);
    }
  } catch {
    // ignore file logging failures — never crash the caller
  }
}
