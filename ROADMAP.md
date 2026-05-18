# MiQi Desktop — Engineering Roadmap

> **Scope:** Desktop Electron UI (`apps/desktop/`) changes required to reflect two major backend upgrades:  
> (1) Memory system overhaul shipped 2026-05-14, and  
> (2) Task Graph (git-like lesson system) shipped 2026-05-15.  
>
> This document is written for engineers implementing the desktop UI work.  
> All references are to source files in this repository unless otherwise noted.

---

## Table of Contents

1. [Background: What Changed in the Backend](#1-background-what-changed-in-the-backend)
2. [Priority 1 — Memory Page Updates (memory overhaul, 2026-05-14)](#2-priority-1--memory-page-updates)
3. [Priority 2 — Task History Page (Task Graph, 2026-05-15)](#3-priority-2--task-history-page)
4. [Cross-cutting: Bridge IPC Layer](#4-cross-cutting-bridge-ipc-layer)
5. [Navigation and Shell Changes](#5-navigation-and-shell-changes)
6. [Out of Scope](#6-out-of-scope)

---

## 1. Background: What Changed in the Backend

### 1.1 Memory System (2026-05-14)

Six commits on 2026-05-14 rewrote MiQi's self-improvement infrastructure:

| Commit | Change |
|---|---|
| `2d836b0` | Added `memory` agent tool (`miqi/agent/tools/memory.py`) |
| `12b9349` | Added `session_search` agent tool for FTS5 cross-session recall |
| `3b4f2ad` | Added `skill_manage` agent tool |
| `f43eae5` | Added turn-level nudge system for memory/skill persistence |
| `395ecd6` | Added `SkillCurator` for LLM-driven skill lifecycle management |
| `8ed6f30` | Added lesson state machine: `active → stale → archived` auto-transitions |
| `09488eb` | Added lesson state badge + unlearn button to `MemoryPage.tsx` ← **desktop partially updated** |

The partial desktop update (`09488eb`) added visual state badges and an unlearn button to the Lessons section of `MemoryPage.tsx`. However, several backend changes have **no desktop representation yet**.

Key gap: **`lessons_legacy_inject_enabled` kill-switch** (default `False` as of 2026-05-15, `miqi/agent/memory/store.py` line ~480 and `miqi/config/schema.py`). Lessons are no longer auto-injected into the agent system prompt. The current UI still presents the Lessons section as a first-class self-improvement mechanism without any indication that it has been superseded by Task Traces.

### 1.2 Task Graph System (2026-05-15)

Nine commits on 2026-05-15 implemented a git-like task tracing system:

| Commit | Phase |
|---|---|
| `c5398c7` | Phase 1: `miqi/agent/trace/` — `TraceStore`, `Embedder`, `TaskTrace`, `TaskStep` data model |
| `c10235b` | Phase 2: `task_begin`, `task_end`, `trace_search` agent tools |
| `d2290b1` | Phase 3: similar-history context injection into `build_system_prompt()` |
| `6f9ef94` | Phase 4: nudge + auto-close on `AgentLoop.stop()` and `/new` |
| `bad4cd1` | Phase 5: `lessons_legacy_inject_enabled=False` kill-switch; `migrate.py` |
| `85cdfd9` | Phase 6: `miqi trace` CLI sub-commands |

**The entire Task Graph system has zero desktop UI surface.** The bridge server (`miqi/bridge/server.py`) has no `traces:*` handlers. The Electron preload (`apps/desktop/src/preload/index.ts`) has no `window.miqi.traces` namespace. No `TracesPage.tsx` exists.

---

## 2. Priority 1 — Memory Page Updates

**Reference file:** `apps/desktop/src/renderer/features/memory/MemoryPage.tsx`  
**Reference IPC types:** `apps/desktop/src/shared/ipc.ts` (`MemoryLessonEntry`, `MemoryLessonsResult`)  
**Reference bridge handler:** `miqi/bridge/server.py` `handle_memory_lessons()` (line ~967)  

### 2.1 Lessons Section: Indicate Legacy Status

The `MemoryLessonsResult.lessons` array is already returned by the bridge with `state: "active" | "stale" | "archived"`. The current UI added state badges in `09488eb`. What is missing:

1. **Section heading should change** from something like "自我改进经验" to a heading that makes clear this is a legacy feature — e.g. "Legacy Lessons (deprecated)".
2. **Add an informational callout** below the heading explaining that lessons are no longer injected into the agent prompt by default and that the Task Graph (`miqi trace`) is the new mechanism. This prevents users from creating lessons and wondering why the agent ignores them.
3. **Add a settings link** to the `AgentSelfImprovementConfig` toggle for `lessons_legacy_inject_enabled`. In the SettingsPage (`apps/desktop/src/renderer/features/settings/SettingsPage.tsx`), a new toggle in the **Agent** tab should expose this field. When `false`, a subtle "not injected" badge on the Lessons section header gives visual feedback.

**Concrete change in `MemoryPage.tsx`:**

```tsx
// Where the lesson list header is rendered, add:
<div className="flex items-center gap-2">
  <h3 className="text-sm font-semibold text-[var(--text)]">Legacy Lessons</h3>
  <span className="text-xs px-1.5 py-0.5 rounded bg-[var(--surface-muted)] text-[var(--text-muted)]">
    deprecated
  </span>
  {!legacyInjectEnabled && (
    <span className="text-xs text-[var(--text-muted)]">· not injected into prompt</span>
  )}
</div>
<p className="text-xs text-[var(--text-muted)] mt-1">
  Lessons are superseded by Task Traces. New tasks learn from trace history automatically.
</p>
```

The `legacyInjectEnabled` value requires a new bridge call — see §4.1.

### 2.2 Lesson Lifecycle Filtering

The backend `LessonStore` now exposes `state` (`active` | `stale` | `archived`). The bridge handler `handle_memory_lessons()` already returns this field in the `MemoryLessonEntry` objects.

The current `MemoryPage.tsx` renders all lessons in a flat list without filtering by state. The recommended change:

- Add a tab strip or filter pills: **Active** / **Stale** / **Archived** / **All**
- Default to **Active** tab (hide archived by default to reduce noise)
- Show stale lessons with a yellow dot or badge warning that they may be promoted to archive soon
- Show archived lessons with a strikethrough style and no unlearn button (already archived)

**Reference:** `MemoryLessonEntry` in `apps/desktop/src/shared/ipc.ts` line 393 already has fields including `state`, `enabled`, `confidence`, `created_at`, `updated_at`.

### 2.3 Add "Migrate to Task Traces" Action

The backend provides `miqi/agent/trace/migrate.py::migrate_lessons_to_traces()`. Expose this in the UI as a one-time action:

- A button "Migrate all lessons → Task Traces" in the Lessons section header
- On click: call a new bridge method `traces:migrate_lessons` (see §4.2)
- Show a confirmation dialog: "This will copy N active lessons to Task Trace history. Original lessons are not deleted."
- On success: show a toast with count migrated

---

## 3. Priority 2 — Task History Page

This is a net-new page. Nothing in the desktop currently surfaces `{workspace}/traces/TRACES.sqlite`.

**New file to create:** `apps/desktop/src/renderer/features/traces/TracesPage.tsx`

### 3.1 Data Model (TypeScript)

Add to `apps/desktop/src/shared/ipc.ts`:

```typescript
export interface TaskStepEntry {
  tool_name: string
  args_summary: string    // ≤ 200 chars
  result_summary: string  // ≤ 200 chars
  timestamp: number       // Unix seconds float
}

export interface TaskTraceEntry {
  trace_hash: string
  parent_hash: string | null
  session_id: string
  task_name: string
  goal: string
  tool_calls: TaskStepEntry[]
  outcome: 'success' | 'partial' | 'failure'
  outcome_notes: string
  created_at: number   // Unix seconds float
  ended_at: number | null
  similarity_score: number  // 0–1; populated only by search results
  metadata: Record<string, unknown>
}

export interface TracesListResult {
  traces: TaskTraceEntry[]
  total: number
}

export interface TracesSearchResult {
  results: TaskTraceEntry[]
}

// IPC channel constants (add to the IpcChannel enum / object):
TRACES_LIST: 'traces:list',
TRACES_GET: 'traces:get',
TRACES_SEARCH: 'traces:search',
TRACES_EXPORT: 'traces:export',
TRACES_MIGRATE_LESSONS: 'traces:migrate_lessons',
```

**Reference data model:** `miqi/agent/trace/model.py` — `TaskTrace` and `TaskStep` dataclasses define the canonical field names and types.

### 3.2 Layout

Recommended layout: **master–detail**, matching the Sessions page pattern (`apps/desktop/src/renderer/features/sessions/`).

```
┌─────────────────────────────────────────────────────────────────┐
│  [Search traces...]                [Filter: All ▾]  [Export]    │
├──────────────────────┬──────────────────────────────────────────┤
│  Task list           │  Detail panel                            │
│  ─────────────────   │  ─────────────────                       │
│  ● fetch-arxiv-paper │  task_name: fetch-arxiv-paper            │
│    success · 2m ago  │  goal: Download the 2024 survey on …     │
│                      │  outcome: ✅ success                     │
│  ◑ compile-rust-code │  outcome_notes: All 3 papers fetched …   │
│    partial · 5m ago  │                                          │
│                      │  Tool chain:                             │
│  ✗ build-docker-img  │  web_search → read_file → write_file     │
│    failure · 1h ago  │                                          │
│                      │  Similar traces (score ≥ 0.65):         │
│                      │  · fetch-semantic-scholar (0.87)         │
│                      │  · get-paper-pdfs (0.71)                 │
└──────────────────────┴──────────────────────────────────────────┘
```

### 3.3 List Panel

Each list item should show:
- Outcome icon: ✅ (success) / ◑ (partial) / ✗ (failure) — use Lucide icons `CheckCircle2`, `CircleHalf` (or `AlertCircle`), `XCircle`
- `task_name` as primary label
- Relative time (`created_at`) as secondary label
- Outcome badge colored: green / amber / red

Filters at top:
- Free-text search → calls `traces:search` bridge method
- Outcome filter dropdown: All / Success / Partial / Failure
- Session filter: dropdown of known session keys

### 3.4 Detail Panel

When a trace is selected, show a detail view with:

1. **Header**: `task_name`, outcome badge, timestamps (`created_at` → `ended_at`, duration)
2. **Goal**: full text of `goal` field
3. **Tool chain**: ordered list of `tool_calls` as a horizontal chip sequence — `tool_name` only (no args/results in the primary view to avoid clutter)
4. **Outcome notes**: `outcome_notes` field in a collapsible section
5. **Expandable steps**: each `TaskStepEntry` in a collapsible accordion showing `args_summary` and `result_summary`
6. **Similar traces**: shown only if the trace was retrieved via semantic search (has non-zero `similarity_score`); otherwise a "Find similar" button that triggers a search using this trace's goal as query
7. **Metadata**: raw JSON in a collapsible section

### 3.5 Visualizations

Two optional visualizations to consider for a later iteration:

**a) Tool Chain Diagram (inline in detail panel)**  
A simple horizontal SVG flow: `tool_a → tool_b → tool_c → …` with colored nodes. No external library needed — pure SVG or a lightweight React flow library like `@xyflow/react` (formerly `reactflow`) if already a dep; otherwise plain `<svg>`.

**b) Outcome Timeline (top of page, collapsed by default)**  
A scrollable calendar-style heatmap showing outcome distribution over time, one cell per day colored by dominant outcome. Similar to GitHub's contribution graph. This is low-priority but high visual impact.

**c) Session context badge**  
The `session_id` field is a `"channel:chat_id"` string (e.g. `"desktop:1747123456789"`). Clicking it should navigate to the matching session in the Sessions page. This creates a two-way link between session history and task traces for the same conversation.

---

## 4. Cross-cutting: Bridge IPC Layer

All new UI features require new bridge handlers. No trace-related IPC exists in the bridge today.

**Reference file:** `miqi/bridge/server.py`  
**Pattern to follow:** any of the existing handler groups, e.g. `handle_memory_*` (lines 869–1047)

### 4.1 New handlers needed

| Handler | Method string | Params | Returns |
|---|---|---|---|
| `handle_traces_list` | `traces:list` | `outcome?: string`, `session_id?: string`, `limit?: int`, `offset?: int` | `TracesListResult` |
| `handle_traces_get` | `traces:get` | `trace_hash: string` | `TaskTraceEntry` |
| `handle_traces_search` | `traces:search` | `query: string`, `limit?: int` | `TracesSearchResult` |
| `handle_traces_export` | `traces:export` | `output_path?: string` | `{path: string, count: int}` |
| `handle_traces_migrate_lessons` | `traces:migrate_lessons` | _(none)_ | `{count: int}` |
| `handle_traces_config_get` | `traces:config` | _(none)_ | `{trace_enabled, lessons_legacy_inject_enabled, trace_inject_top_k, ...}` |

**Implementation sketch for `handle_traces_list`:**
```python
def handle_traces_list(req_id: str, params: dict) -> None:
    config = _state.load_config()
    from miqi.agent.trace.store import TraceStore
    store = TraceStore(
        workspace=config.workspace_path,
        enabled=config.agents.self_improvement.trace_enabled,
        embedding_model=config.agents.self_improvement.embedding_model,
    )
    outcome = params.get("outcome")  # None or "success"|"partial"|"failure"
    limit = int(params.get("limit", 50))
    traces = store.list_recent(n=limit, outcome=outcome)
    _result(req_id, {
        "traces": [_trace_to_dict(t) for t in traces],
        "total": len(traces),
    })
```

The `_trace_to_dict` helper already exists in `miqi/cli/trace_cmd.py` and can be copied/imported.

For `traces:config`, include `lessons_legacy_inject_enabled` from `config.agents.self_improvement` so the MemoryPage can show the "not injected" badge (§2.1).

### 4.2 Preload API additions

Add to `apps/desktop/src/preload/index.ts`:
```typescript
traces: {
  list: (params?: { outcome?: string; session_id?: string; limit?: number }) =>
    ipc('traces:list', params ?? {}),
  get: (trace_hash: string) =>
    ipc('traces:get', { trace_hash }),
  search: (query: string, limit?: number) =>
    ipc('traces:search', { query, limit: limit ?? 5 }),
  export: (output_path?: string) =>
    ipc('traces:export', { output_path }),
  migrateLessons: () =>
    ipc('traces:migrate_lessons', {}),
  config: () =>
    ipc('traces:config', {}),
},
```

### 4.3 Electron main IPC handlers

Add the new channel constants to `apps/desktop/src/main/ipc/index.ts` alongside the existing `MEMORY_*` channels, following the same Zod-validation pattern.

---

## 5. Navigation and Shell Changes

**Reference files:** `apps/desktop/src/renderer/App.tsx`, `apps/desktop/src/renderer/components/Sidebar.tsx`

### 5.1 New NavId

Add `'traces'` to the `NavId` union in `App.tsx`:
```typescript
type NavId =
  | 'chat' | 'providers' | 'channels' | 'approvals'
  | 'cron' | 'memory' | 'skills' | 'workspace'
  | 'traces'   // NEW
  | 'settings'
```

### 5.2 Sidebar Entry

Add a sidebar entry for Traces. Suitable Lucide icon: `GitBranch` or `Network` (both in lucide-react).  
Recommended label: **Task History** (or **Trace Log**).  
Position: between Memory and Skills in the sidebar order.

### 5.3 Import and Render

In `App.tsx`, import and conditionally render `TracesPage`:
```typescript
import { TracesPage } from './features/traces/TracesPage'
// ...
{activeNav === 'traces' && <TracesPage />}
```

---

## 6. Out of Scope

The following are **not** covered by this roadmap and should be tracked separately if needed:

- **Real-time "in-progress" task indicator in the chat toolbar**: showing a live badge when `TraceStore._open_tasks[session_key]` is non-empty would require a new polling or push mechanism over the bridge. The current bridge protocol is request/response only.
- **Embedding model download progress**: first use of `task_begin`/`task_end` with `fastembed` installed triggers a ~92 MB model download. A progress UI in the setup wizard or first-run experience would be user-friendly but is non-trivial.
- **Trace DAG visualization**: the `parent_hash` field enables a directed acyclic graph of task lineage. A full graph visualization (e.g. using `@xyflow/react`) is a future milestone, not an immediate requirement.
- **Mobile / gateway channel UI**: this roadmap applies only to the Electron desktop app.
