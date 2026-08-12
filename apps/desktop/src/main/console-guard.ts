/**
 * Console write guard for the Electron main process.
 *
 * When the main process is spawned by another process (a script, a launcher,
 * a terminal emulator) and that parent exits, the stdout/stderr pipe closes
 * underneath us. Any subsequent write throws `EPIPE: broken pipe`:
 *  - synchronously, from inside `console.log`/`process.stdout.write` — or
 *  - asynchronously, as an `'error'` event on the stream, which Node's
 *    default handler turns into an uncaught exception ("A JavaScript error
 *    occurred in the main process" crash dialog).
 *
 * The log file (`writeMainProcessLog`) is the durable record; the console is
 * best-effort. This module makes console writes safe, keeps the original
 * routing (log → stdout, warn/error → stderr), and is unit-testable without
 * needing Electron.
 */

// Error codes that mean "the reader of our stdout/stderr is gone".
// EPIPE is the classic broken pipe; ECONNRESET is what some platforms
// surface when the pipe's reader closes the connection.
const READER_GONE_CODES = new Set(['EPIPE', 'ECONNRESET']);

/**
 * The minimal writable-stream surface this guard needs. Both `process.stdout`
 * and `stream.Writable` instances satisfy it structurally, so the helpers stay
 * unit-testable without importing tty-specific `WriteStream` types.
 */
export interface GuardedWritable {
  readonly destroyed: boolean;
  destroy(): void;
  on(event: 'error', listener: (err: Error) => void): unknown;
}

/**
 * True when the error means our pipe reader went away — a condition to
 * swallow — as opposed to a real failure that should keep Node's default
 * (crash) behavior.
 */
export function isBrokenPipeError(err: unknown): boolean {
  return err instanceof Error && READER_GONE_CODES.has((err as NodeJS.ErrnoException).code ?? '');
}

/**
 * `'error'` event handler for a std stream: swallow reader-gone errors and
 * destroy the stream (writes to it become no-ops), rethrow anything else so
 * real failures keep Node's default behavior.
 */
export function handleStdStreamError(stream: GuardedWritable): void {
  stream.on('error', (err: Error) => {
    if (isBrokenPipeError(err)) {
      // stdout/stderr pipe is broken — drop subsequent writes silently.
      stream.destroy();
    } else {
      // Not a broken pipe — keep Node's default behavior (crash the process).
      throw err;
    }
  });
}

/**
 * Invoke `fn(...args)` guarding against a broken pipe:
 *   - if the stream is already destroyed, skip the call entirely;
 *   - otherwise swallow a synchronous reader-gone throw (and destroy the
 *     stream so later writes are skipped too) instead of letting it become
 *     an uncaught exception.
 *
 * The return value of `fn(...args)` is preserved; once the stream is broken
 * the call degrades to `undefined`.
 */
export function safeWrite<T extends (...args: any[]) => unknown>(
  stream: GuardedWritable,
  fn: T,
  args: Parameters<T>
): ReturnType<T> | undefined {
  if (stream.destroyed) {
    return undefined;
  }
  try {
    return fn(...args) as ReturnType<T>;
  } catch (err) {
    if (!isBrokenPipeError(err)) {
      throw err;
    }
    stream.destroy();
    return undefined;
  }
}

/**
 * Install the stream-level `'error'` handlers on `process.stdout` and
 * `process.stderr` so that an async EPIPE (emitted as an `'error'` event)
 * does not crash the main process. Call once at startup, before any logging.
 */
export function guardStdStreams(): void {
  handleStdStreamError(process.stdout);
  handleStdStreamError(process.stderr);
}
