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
  sessionMessages?: Record<string, unknown[]>;
  preloadOk?: boolean;
}

export function buildMockBridgeScript(opts: MockBridgeOptions = {}): string {
  const runtimeStatus = opts.runtimeStatus || 'running';
  const preloadOk = opts.preloadOk !== false;
  const initialSessions = opts.sessions || [
    { key: 'sess-001', title: 'Test conversation 1', updated_at: Date.now(), message_count: 5 },
    {
      key: 'sess-002',
      title: 'Test conversation 2',
      updated_at: Date.now() - 3600000,
      message_count: 3,
    },
  ];
  const sessionsJson = JSON.stringify(initialSessions);
  const sessionMessagesJson = JSON.stringify(opts.sessionMessages || {});

  return `
(function() {
  if (typeof window === 'undefined') return;
  if (!${preloadOk}) return;

  var noop = function() { return function() {}; };
  var now = Date.now();
  var _skills = [
    { name: 'code-reviewer', description: 'Review code for bugs and style issues', source: 'workspace', path: '/mock/skills/code-reviewer/SKILL.md', available: true, missingRequirements: null, content: '# code-reviewer\\n\\nReview code for bugs and style issues.', metadata: { owner: 'qa' } },
    { name: 'pdf-generator', description: 'Generate PDF documents from markdown', source: 'workspace', path: '/mock/skills/pdf-generator/SKILL.md', available: true, missingRequirements: null, content: '# pdf-generator\\n\\nGenerate PDF documents from markdown.', metadata: null },
    { name: 'data-analyzer', description: 'Analyze CSV and JSON data files', source: 'builtin', path: '/mock/builtin/data-analyzer/SKILL.md', available: true, missingRequirements: null, content: '# data-analyzer\\n\\nAnalyze CSV and JSON data files.', metadata: null },
    { name: 'web-scraper', description: 'Scrape web pages for data extraction', source: 'builtin', path: '/mock/builtin/web-scraper/SKILL.md', available: true, missingRequirements: null, content: '# web-scraper\\n\\nScrape web pages for data extraction.', metadata: null }
  ];
  var _mcps = [
    { name: 'filesystem-demo', command: 'npx', args: ['-y', '@modelcontextprotocol/server-filesystem'], description: 'Local filesystem tools', tool_timeout: 30, lazy: false }
  ];
  var _memoryFiles = [
    { path: 'README.md', scope: 'workspace', size: 34, updatedAtMs: now - 120000, content: '# Workspace notes\\nRemember smoke QA.' },
    { path: 'agent-profile.md', scope: 'agent', size: 36, updatedAtMs: now - 60000, content: '# Agent memory\\nPrefer focused tests.' }
  ];
  var _lessons = [
    { id: 'lesson-1', trigger: 'When adding Playwright tests', badAction: 'Only check screenshots', betterAction: 'Assert bridge calls and visible UI state', scope: 'workspace', sessionKey: 'sess-001', confidence: 2, effectiveConfidence: 3, hits: 4, state: 'active', enabled: true, source: 'mock', createdAt: new Date(now - 300000).toISOString(), updatedAt: new Date(now - 100000).toISOString() }
  ];
  function _makeCronJob(input) {
    var scheduleKind = input.scheduleKind || 'every';
    var everyMs = scheduleKind === 'every' ? (input.everyMs || 60000) : null;
    var atMs = scheduleKind === 'at' ? input.atMs : null;
    var expr = scheduleKind === 'cron' ? (input.expr || '* * * * *') : null;
    return {
      id: input.jobId || ('cron-' + Date.now() + '-' + Math.floor(Math.random() * 1000)),
      name: input.name || 'Mock job',
      enabled: input.enabled !== false,
      schedule: { kind: scheduleKind, atMs: atMs || null, everyMs: everyMs || null, expr: expr || null, tz: input.tz || null },
      payload: { kind: 'agent_turn', message: input.message || '', deliver: input.deliver !== false, channel: input.channel || null, to: input.to || null },
      state: { nextRunAtMs: Date.now() + (everyMs || 60000), lastRunAtMs: null, lastStatus: null, lastError: null },
      createdAtMs: Date.now(),
      updatedAtMs: Date.now(),
      deleteAfterRun: false
    };
  }
  var _cronJobs = [
    _makeCronJob({ jobId: 'cron-daily', name: 'Daily digest', scheduleKind: 'every', everyMs: 60000, message: 'Summarize outstanding tasks' })
  ];
  var _cronRuns = [
    { jobId: 'cron-daily', jobName: 'Daily digest', startedAtMs: now - 30000, status: 'ok', error: null }
  ];

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
      get: function(key) {
        var sessions = ${sessionsJson};
        var sessionMessages = ${sessionMessagesJson};
        var found = null;
        for (var i = 0; i < sessions.length; i++) {
          if (sessions[i].key === key) { found = sessions[i]; break; }
        }
        return Promise.resolve({ key: key, title: found ? found.title : key, messages: sessionMessages[key] || [], tracked_files: [] });
      },
      delete: function() { return Promise.resolve({ deleted: true }); },
      archive: function() { return Promise.resolve({ archived: true }); },
      unarchive: function() { return Promise.resolve({ unarchived: true }); },
      listArchived: function() { return Promise.resolve({ sessions: [] }); },
      getTrackedFiles: function() { return Promise.resolve({ tracked_files: [] }); },
      clearTrackedFiles: function() { return Promise.resolve({ cleared: true }); },
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
      list: function() { return Promise.resolve({ jobs: _cronJobs.slice() }); },
      create: function(payload) {
        var job = _makeCronJob(payload || {});
        _cronJobs.unshift(job);
        return Promise.resolve({ job: job });
      },
      update: function(payload) {
        var idx = _cronJobs.findIndex(function(j) { return j.id === payload.jobId; });
        if (idx >= 0) {
          _cronJobs[idx] = Object.assign({}, _cronJobs[idx], _makeCronJob(Object.assign({}, _cronJobs[idx], payload || {})), { id: _cronJobs[idx].id, createdAtMs: _cronJobs[idx].createdAtMs });
          return Promise.resolve({ job: _cronJobs[idx] });
        }
        return Promise.resolve({ job: null });
      },
      toggle: function(jobId, enabled) {
        var job = _cronJobs.find(function(j) { return j.id === jobId; });
        if (job) {
          job.enabled = enabled;
          job.updatedAtMs = Date.now();
        }
        return Promise.resolve({ job: job });
      },
      run: function(jobId) {
        var job = _cronJobs.find(function(j) { return j.id === jobId; });
        if (job) {
          job.state.lastRunAtMs = Date.now();
          job.state.lastStatus = 'ok';
          _cronRuns.unshift({ jobId: job.id, jobName: job.name, startedAtMs: job.state.lastRunAtMs, status: 'ok', error: null });
        }
        return Promise.resolve({ ok: true });
      },
      delete: function(jobId) {
        _cronJobs = _cronJobs.filter(function(j) { return j.id !== jobId; });
        return Promise.resolve({ deleted: true });
      },
      testRun: function() { return Promise.resolve({ ok: true }); },
      runs: function() { return Promise.resolve({ runs: _cronRuns.slice() }); },
    },

    memory: {
      list: function() {
        return Promise.resolve({ files: _memoryFiles.map(function(f) {
          return { path: f.path, scope: f.scope, size: f.content.length, updatedAtMs: f.updatedAtMs };
        }) });
      },
      get: function(path) {
        var file = _memoryFiles.find(function(f) { return f.path === path; });
        return Promise.resolve(file ? { path: file.path, content: file.content, size: file.content.length } : { path: path, content: '', size: 0 });
      },
      update: function(path, content) {
        var file = _memoryFiles.find(function(f) { return f.path === path; });
        if (!file) {
          file = { path: path, scope: 'workspace', size: 0, updatedAtMs: Date.now(), content: '' };
          _memoryFiles.unshift(file);
        }
        file.content = content;
        file.size = content.length;
        file.updatedAtMs = Date.now();
        return Promise.resolve({ path: path, size: file.size });
      },
      save: function(path, content) { return window.miqi.memory.update(path, content || ''); },
      delete: function(path) {
        _memoryFiles = _memoryFiles.filter(function(f) { return f.path !== path; });
        return Promise.resolve({ deleted: true });
      },
      lessons: function() { return Promise.resolve({ lessons: _lessons.slice() }); },
      lessonUnlearn: function(id) {
        _lessons = _lessons.filter(function(l) { return l.id !== id; });
        return Promise.resolve({ unlearned: [id] });
      },
      unlearn: function(id) { return window.miqi.memory.lessonUnlearn(id); },
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
      list: function() {
        return Promise.resolve({ skills: _skills.map(function(s) {
          return { name: s.name, description: s.description, source: s.source, path: s.path, available: s.available, missingRequirements: s.missingRequirements };
        }) });
      },
      get: function(name) {
        var skill = _skills.find(function(s) { return s.name === name; });
        return Promise.resolve(skill || null);
      },
      create: function(name, description) {
        _skills.unshift({ name: name, description: description || '', source: 'workspace', path: '/mock/skills/' + name + '/SKILL.md', available: true, missingRequirements: null, content: '# ' + name + '\\n\\n' + (description || ''), metadata: null });
        return Promise.resolve({ ok: true });
      },
      upload: function(name, content) {
        _skills = _skills.filter(function(s) { return s.name !== name; });
        _skills.unshift({ name: name, description: 'Installed from SkillHub', source: 'workspace', path: '/mock/skills/' + name + '/SKILL.md', available: true, missingRequirements: null, content: content || '', metadata: null });
        return Promise.resolve({ ok: true });
      },
      delete: function(name) {
        _skills = _skills.filter(function(s) { return s.name !== name; });
        return Promise.resolve({ ok: true });
      },
      openFolder: function(name) {
        window.__miqiMock.calls.push({ type: 'skills.openFolder', name: name });
        return Promise.resolve({ ok: true });
      },
    },

    mcps: {
      list: function() { return Promise.resolve({ servers: _mcps.slice() }); },
      upsert: function(name, config) {
        _mcps = _mcps.filter(function(s) { return s.name !== name; });
        _mcps.unshift(Object.assign({ name: name }, config || {}));
        return Promise.resolve({ ok: true });
      },
      delete: function(name) {
        _mcps = _mcps.filter(function(s) { return s.name !== name; });
        return Promise.resolve({ ok: true });
      },
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
    calls: [],

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

    /**
     * Fire the final reply preserving the EXACT content, including an empty
     * string. Unlike final(), this does NOT fall back to a default response —
     * so it can exercise the empty-reply regression path.
     */
    _fireFinal: function(content) {
      _fire('progress', { text: 'Generating response…' });
      setTimeout(function() {
        _fire('final', { content: content });
      }, 50);
    },

    /** Fire a final event immediately, without adding mock progress. */
    rawFinal: function(content) {
      _fire('final', { content: content });
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
      this.calls = [];
    },
  };

  window.dispatchEvent(new Event('DOMContentLoaded'));
})();
`.trim();
}
