import { describe, expect, it, vi, afterEach } from 'vitest';
import { Writable } from 'stream';
import {
  guardStdStreams,
  handleStdStreamError,
  isBrokenPipeError,
  safeWrite,
} from './console-guard';

function makeErrno(code: string, message = `write ${code}`): NodeJS.ErrnoException {
  const err = new Error(message) as NodeJS.ErrnoException;
  err.code = code;
  return err;
}

describe('isBrokenPipeError', () => {
  it('recognizes EPIPE and ECONNRESET', () => {
    expect(isBrokenPipeError(makeErrno('EPIPE'))).toBe(true);
    expect(isBrokenPipeError(makeErrno('ECONNRESET'))).toBe(true);
  });

  it('rejects other errors and non-errors', () => {
    expect(isBrokenPipeError(makeErrno('EACCES'))).toBe(false);
    expect(isBrokenPipeError(new Error('no code'))).toBe(false);
    expect(isBrokenPipeError('not an error')).toBe(false);
    expect(isBrokenPipeError(null)).toBe(false);
  });
});

describe('safeWrite', () => {
  it('preserves the return value of the wrapped function', () => {
    const stream = new Writable({
      write(_c, _e, cb) {
        cb();
      },
    });
    expect(safeWrite(stream, () => 42, [])).toBe(42);
  });

  it('swallows a synchronous EPIPE and destroys the stream', () => {
    const stream = new Writable({
      write(_c, _e, cb) {
        cb();
      },
    });
    const fn = vi.fn((_s?: unknown) => {
      throw makeErrno('EPIPE');
    });

    // First write throws EPIPE — swallowed.
    expect(() => safeWrite(stream, fn, ['hello'])).not.toThrow();
    expect(fn).toHaveBeenCalledTimes(1);

    // Stream is now destroyed — subsequent writes are skipped.
    expect(safeWrite(stream, fn, ['again'])).toBeUndefined();
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('rethrows non-broken-pipe errors', () => {
    const stream = new Writable({
      write(_c, _e, cb) {
        cb();
      },
    });
    const boom = new Error('boom');
    const fn = () => {
      throw boom;
    };
    expect(() => safeWrite(stream, fn, [])).toThrow('boom');
  });

  it('returns undefined when the stream is already destroyed', () => {
    const stream = new Writable({
      write(_c, _e, cb) {
        cb();
      },
    });
    const fn = vi.fn((_s?: unknown) => 'value');
    stream.destroy();
    expect(safeWrite(stream, fn, [])).toBeUndefined();
    expect(fn).not.toHaveBeenCalled();
  });
});

describe('handleStdStreamError', () => {
  it('swallows EPIPE error events and destroys the stream', () => {
    const stream = new Writable({
      write(_c, _e, cb) {
        cb();
      },
    });
    handleStdStreamError(stream);

    const destroySpy = vi.spyOn(stream, 'destroy');
    stream.emit('error', makeErrno('EPIPE'));

    expect(destroySpy).toHaveBeenCalled();
    expect(stream.destroyed).toBe(true);
  });

  it('rethrows non-broken-pipe error events', () => {
    const stream = new Writable({
      write(_c, _e, cb) {
        cb();
      },
    });
    handleStdStreamError(stream);
    expect(() => stream.emit('error', new Error('real failure'))).toThrow('real failure');
  });
});

describe('guardStdStreams', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('installs error handlers on process.stdout and process.stderr', () => {
    const stdoutSpy = vi.spyOn(process.stdout, 'on');
    const stderrSpy = vi.spyOn(process.stderr, 'on');
    guardStdStreams();

    expect(stdoutSpy).toHaveBeenCalledWith('error', expect.any(Function));
    expect(stderrSpy).toHaveBeenCalledWith('error', expect.any(Function));
  });
});
