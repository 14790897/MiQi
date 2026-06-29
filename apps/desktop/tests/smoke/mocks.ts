/**
 * Mock bridge for Playwright smoke QA tests.
 * Supports both static (read-only) and interactive modes.
 *
 * Interactive mode: the test calls window.__miqiMock.trigger*(...) to
 * simulate backend events (progress, final, error, abort).
 */

export interface MockBridgeOptions {
  runtimeStatus?: 'stopped' | 'running' | 'starting';
  sessions?: Array<{ key: string; title: string; updated_at: number; message_count: number }>;
  preloadOk?: boolean;
}

export function buildMockBridgeScript(opts: MockBridgeOptions = {}): string {
  const runtimeStatus = opts.runtimeStatus || 'running';
  const preloadOk = opts.preloadOk !== false;
  const initialSessions = opts.sessions || [
    { key: 'sess-001', title: 'Test conversation 1', updated_at: Date.now(), message_count: 5 },
    { key: 'sess-002', title: 'Test conversation 2', updated_at: Date.now() - 3600000, message_count: 3 },
  ];
  const sessionsJson = JSON.stringify(initialSessions);

  return `
(function() {
  if (typeof window === 'undefined') return;
  if (!${preloadOk}) return;

  var noop = function() { return function() {}; };

  // ── Interactive helpers ──────────────────────────────────────────
  var _callbacks = { progress: [], final: [], error: [], aborted: [] };

  function _on(type, cb) {
    _callbacks[type].push(cb);
    return function() {
      _callbacks[type] = _callbacks[type].filter(function(f) { return f !== cb; });
    };
  }

  function _fire(type, data) {
    _callbacks[type].forEach(function(f) { try { f(data); } catch(e) {} });
  }

  // ── window.miqi ──────────────────────────────────────────────────

  window.miqi = {
    runtime: {
      start: function() { return Promise.resolve({ state: 'running', pid: 12345 }); },
      stop: function() { return Promise.resolve({ state: 'stopped', pid: 0 }); },
      status: function() { return Promise.resolve({ state: '${runtimeStatus}', pid: ${runtimeStatus === 'running' ? 12345 : 0} }); },
      logs: function() { return Promise.resolve(['[miqi-bridge] Bridge started', '[miqi-bridge] Agent ready']); },
      onStateChange: noop,
      onLog: noop,
    },

    chat: {
      send: function() { return Promise.resolve({ accepted: true, req_id: 'req-test-001' }); },
      abort: function() {
        _fire('aborted', {});
        return Promise.resolve({ aborted: true });
      },
      onProgress: function(cb) { return _on('progress', cb); },
      onFinal: function(cb) { return _on('final', cb); },
      onError: function(cb) { return _on('error', cb); },
      onAborted: function(cb) { return _on('aborted', cb); },
      onSubagentResult: noop,
    },

    threads: {
      start: function(opts) {
        var id = 'thread-' + Date.now();
        return Promise.resolve({ thread: { id: id, title: opts && opts.title || 'Chat' } });
      },
    },

    sessions: {
      list: function() { return Promise.resolve({ sessions: ${sessionsJson} }); },
    },

    approvals: {
      list: function() { return Promise.resolve({ pending: [], permanent_rules: [], timeouts: null }); },
      resolve: function() { return Promise.resolve({ resolved: true }); },
      clearPermanent: function() { return Promise.resolve({ cleared: true }); },
      addPermanent: function() { return Promise.resolve({ added: { pattern: 'echo', decision: 'always' } }); },
      history: function() { return Promise.resolve({ items: [] }); },
      onRequest: noop,
      onCleared: noop,
    },

    files: {
      tree: function() { return Promise.resolve({ tree: { name: '/', type: 'directory', children: [] } }); },
      read: function() { return Promise.resolve({ path: '/test.txt', content: 'test' }); },
      write: function() { return Promise.resolve({ path: '/test.txt', written: true }); },
      delete: function() { return Promise.resolve({ deleted: true, path: '/test.txt' }); },
      diff: function() { return Promise.resolve({ path: '/test.txt', diff: 'no changes' }); },
      revert: function() { return Promise.resolve({ path: '/test.txt', reverted: true }); },
      accept: function() { return Promise.resolve({ accepted: true, path: '/test.txt' }); },
    },

    config: {
      get: function() { return Promise.resolve({}); },
      update: function() { return Promise.resolve({}); },
    },

    providers: {
      list: function() { return Promise.resolve([]); },
      test: function() { return Promise.resolve({ ok: true }); },
      update: function() { return Promise.resolve({ ok: true }); },
    },

    channels: {
      get: function() { return Promise.resolve({}); },
      update: function() { return Promise.resolve({ ok: true }); },
    },

    cron: {
      list: function() { return Promise.resolve([]); },
      create: function() { return Promise.resolve({ ok: true }); },
      update: function() { return Promise.resolve({ ok: true }); },
      testRun: function() { return Promise.resolve({ ok: true }); },
      runs: function() { return Promise.resolve([]); },
    },

    memory: {
      list: function() { return Promise.resolve([]); },
      get: function() { return Promise.resolve(null); },
      save: function() { return Promise.resolve({ ok: true }); },
      delete: function() { return Promise.resolve({ ok: true }); },
      lessons: function() { return Promise.resolve([]); },
      unlearn: function() { return Promise.resolve({ ok: true }); },
    },

    experience: {
      list: function() { return Promise.resolve({ entries: [
        { id: '1', type: 'rule', title: 'Python type hints', content: 'Always use type hints in function signatures', confidence: 0.9, enabled: true, scope: 'all', source: 'agent', session_key: 'sess-001' },
        { id: '2', type: 'rule', title: 'Error handling pattern', content: 'Use try-catch with specific error types', confidence: 0.8, enabled: true, scope: 'all', source: 'agent', session_key: 'sess-001' },
        { id: '3', type: 'trace', title: 'React best practices', content: 'Use functional components and hooks', confidence: 0.7, enabled: true, scope: 'all', source: 'agent', session_key: 'sess-002' },
        { id: '4', type: 'trace', title: 'Database migration', content: 'Always test migrations before applying', confidence: 0.85, enabled: true, scope: 'all', source: 'agent', session_key: 'sess-002' },
      ] }); },
      delete: function() { return Promise.resolve({ deleted: true }); },
      toggle: function() { return Promise.resolve({ ok: true }); },
      search: function() { return Promise.resolve({ entries: [] }); },
    },

    skills: {
      list: function() { return Promise.resolve({ skills: [
        { key: 'code-reviewer', name: 'code-reviewer', description: 'Review code for bugs and style issues', source: 'workspace' },
        { key: 'pdf-generator', name: 'pdf-generator', description: 'Generate PDF documents from markdown', source: 'workspace' },
        { key: 'data-analyzer', name: 'data-analyzer', description: 'Analyze CSV and JSON data files', source: 'builtin' },
        { key: 'web-scraper', name: 'web-scraper', description: 'Scrape web pages for data extraction', source: 'builtin' },
      ] }); },
      get: function() { return Promise.resolve(null); },
      create: function() { return Promise.resolve({ ok: true }); },
      upload: function() { return Promise.resolve({ ok: true }); },
      delete: function() { return Promise.resolve({ ok: true }); },
      openFolder: function() { return Promise.resolve({ ok: true }); },
    },

    mcps: {
      list: function() { return Promise.resolve([]); },
      upsert: function() { return Promise.resolve({ ok: true }); },
      delete: function() { return Promise.resolve({ ok: true }); },
    },

    python: {
      check: function() { return Promise.resolve({ ok: true, path: 'python.exe', version: '3.12.0', config_exists: true }); },
    },

    wsl: {
      check: function() { return Promise.resolve({ installed: true }); },
      install: function() { return Promise.resolve({ ok: true }); },
      exportDistro: function() { return Promise.resolve({ file: '/tmp/export.tar.gz', size: 0 }); },
      importDistro: function() { return Promise.resolve({ ok: true }); },
      getStats: function() { return Promise.resolve({ distro_count: 1, total_disk_mb: 1024 }); },
    },

    setup: {
      writeInitialConfig: function() { return Promise.resolve({ ok: true }); },
    },

    dialog: {
      openFile: function() { return Promise.resolve({ canceled: true }); },
    },
  };

  // ── Trigger API (for tests) ──────────────────────────────────────

  window.__miqiMock = {
    /** Simulate a progress event (tool-hint or status text) */
    progress: function(data) { _fire('progress', data || { text: '' }); },

    /** Simulate the final assistant response and trigger typewriter animation */
    final: function(content) {
      _fire('progress', { text: 'Generating response…' });
      // Small delay so ChatConsole has time to process the progress event first
      setTimeout(function() {
        _fire('final', { content: content || 'This is a test response from the mock bridge.' });
      }, 50);
    },

    /** Simulate a backend error */
    error: function(message) {
      _fire('error', { message: message || 'Mock backend error' });
    },

    /** Simulate an abort confirmation */
    abort: function() {
      _fire('aborted', {});
    },

    /** Fire a tool execution progress hint */
    toolProgress: function(text, callId) {
      _fire('progress', {
        text: text || 'exec: echo hello',
        tool_hint: true,
        tool_call_id: callId || 'call_mock_001',
      });
    },

    /** Clear all registered callbacks */
    reset: function() {
      _callbacks = { progress: [], final: [], error: [], aborted: [] };
    },
  };

  window.dispatchEvent(new Event('DOMContentLoaded'));
})();
`.trim();
}
