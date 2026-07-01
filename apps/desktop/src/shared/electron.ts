/**
 * Electron runtime accessor — all main-process code MUST import electron from
 * here instead of from 'electron' directly.  The trampoline (electron-trampoline.js)
 * sets __ELECTRON__ on globalThis before loading the bundled application, so
 * require('electron') is resolved by the true Electron runtime without any
 * bundler interop wrapper that would drop non-enumerable exports.
 */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const g = globalThis as any;

if (!g.__ELECTRON__) {
  throw new Error('electron runtime not injected — electron-trampoline.js must be the entry point');
}

export const electron: typeof import('electron') = g.__ELECTRON__;
