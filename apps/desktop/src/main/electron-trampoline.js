/**
 * Electron main-process trampoline.
 *
 * electron-vite's bundler wraps ESM imports from 'electron' through an
 * _interopNamespaceDefault helper that uses for...in to enumerate properties.
 * Since electron's main-process exports (app, BrowserWindow, ipcMain, etc.)
 * are non-enumerable getters, the namespace object ends up empty — every
 * destructured binding is undefined at runtime.
 *
 * This unbundled CommonJS file resolves electron natively, injects it on
 * globalThis, and then hands control to the bundled application.  All
 * TypeScript code in main/ and shared/ reads electron from globalThis so
 * the bundler never touches the real electron module.
 */

const electron = require('electron')

// electron-vite may load this file during build analysis under plain Node.js,
// where require('electron') returns the path string to the binary — not the
// Electron module namespace.  Detect that case and bail silently.
const isRealElectron =
  typeof electron === 'object' && electron !== null && electron.app

if (!isRealElectron) {
  // Build-time scan or non-Electron runtime — exit without crashing so the
  // bundler can finish analysis.  The guard only fires inside real Electron.
  if (typeof electron === 'string' || process.env['ELECTRON_RUN_AS_NODE']) {
    // Not running inside Electron's main process
  } else {
    const path = require('path')
    require('fs').writeFileSync(
      path.join(__dirname, 'trampoline-crash.log'),
      'FATAL: electron.app unavailable — Electron binary may be corrupt\n',
    )
    process.exit(1)
  }
} else {
  // Running inside real Electron — inject and hand off
  globalThis.__ELECTRON__ = electron
  require('./index.js').main()
}
