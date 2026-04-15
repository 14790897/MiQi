# Configuration

MiQi reads configuration from `~/.miqi/config.json`. The interactive wizard (`miqi onboard`) generates this file. Config files are automatically saved with `0600` permissions to protect API keys.

---

## Config File Location

| Item | Default Path |
|---|---|
| Config file | `~/.miqi/config.json` |
| Workspace | `~/.miqi/workspace/` |
| Memory | `<workspace>/memory/` (default `~/.miqi/workspace/memory/`) |
| Sessions | `<workspace>/sessions/` (default `~/.miqi/workspace/sessions/`) |

---

## Minimal Config Skeleton

```json
{
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-v1-xxx"
    }
  },
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5",
      "name": "miqi",
      "temperature": 0.1
    }
  },
  "channels": {},
  "tools": {},
  "heartbeat": {
    "enabled": true,
    "intervalSeconds": 1800
  }
}
```

---

## Section Reference

### `providers`

API keys and base URLs for each LLM provider. Any provider supported by the OpenAI SDK can be added.

```json
"providers": {
  "openrouter": {
    "apiKey": "sk-or-v1-xxx"
  },
  "openai": {
    "apiKey": "sk-..."
  },
  "anthropic": {
    "apiKey": "sk-ant-..."
  },
  "deepseek": {
    "apiKey": "...",
    "apiBase": "https://api.deepseek.com/v1"
  },
  "aihubmix": {
    "apiKey": "...",
    "apiBase": "https://aihubmix.com/v1",
    "extraHeaders": {
      "APP-Code": "your-app-code"
    }
  }
}
```

Supported provider keys in the current schema: `custom`, `openrouter`, `openai`, `anthropic`, `deepseek`, `gemini`, `groq`, `moonshot`, `minimax`, `zhipu`, `dashscope`, `siliconflow`, `volcengine`, `aihubmix`, `vllm`, `ollama_local`, `ollama_cloud`, `openai_codex`, `github_copilot`.

---

### `agents`

#### `agents.defaults`

Default settings applied to all agent instances.

| Key | Type | Default | Description |
|---|---|---|---|
| `model` | string | — | Model identifier (e.g. `anthropic/claude-opus-4-5`) |
| `name` | string | `"miqi"` | Agent display name |
| `workspace` | string | `~/.miqi/workspace` | Working directory and runtime data root |
| `temperature` | float | `0.1` | LLM sampling temperature |
| `maxTokens` | int | `8192` | Maximum output tokens per response |
| `maxToolIterations` | int | `100` | Maximum tool-call rounds per turn |
| `memoryWindow` | int | `100` | Session history window used during context build |
| `reflectAfterToolCalls` | bool | `true` | Insert the internal reflection prompt after tool batches |
| `maxToolResultChars` | int | `16000` | Per-tool truncation cap for the live prompt |
| `contextLimitChars` | int | `600000` | Hard character ceiling before fallback trimming |
| `fallbackChain` | list | `[]` | Fallback model chain metadata. The helper module is shipped, but the packaged CLI/gateway path does not yet invoke it automatically. |

#### `agents.memory`

Controls memory persistence cadence.

| Key | Type | Default | Description |
|---|---|---|---|
| `flushEveryUpdates` | int | `8` | Flush memory to disk after this many updates |
| `flushIntervalSeconds` | int | `120` | Flush memory to disk every N seconds |
| `shortTermTurns` | int | `12` | In-memory recent-turn window per session |
| `pendingLimit` | int | `20` | Maximum pending memory items held per session |

#### `agents.sessions`

Controls session compaction.

| Key | Type | Default | Description |
|---|---|---|---|
| `compactThresholdMessages` | int | `400` | Trigger compaction above this many messages |
| `compactThresholdBytes` | int | `2000000` | Trigger compaction above this file size |
| `compactKeepMessages` | int | `300` | Number of recent messages to retain after compaction |
| `sessionToolResultMaxChars` | int | `500` | Tool-result truncation cap written into persisted session history |
| `useSqlite` | bool | `false` | Reserved flag for the shipped SQLite+FTS5 session backend module. The current CLI/gateway path still instantiates the JSONL `SessionManager`. |

#### `agents.smartRouting`

Schema for cheap-model routing of short/simple turns. `AgentLoop` supports these fields programmatically, but the packaged CLI/gateway path currently uses the default disabled settings.

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Enable smart routing |
| `cheapModel.provider` | string | `""` | Provider name for the cheaper model |
| `cheapModel.model` | string | `""` | Model name for the cheaper model |
| `maxChars` | int | `160` | Turns longer than this stay on the primary model |
| `maxWords` | int | `28` | Turns longer than this stay on the primary model |

#### `agents.commandApproval`

Schema for interactive approval of dangerous shell commands. The repository includes the helper implementation in `miqi/agent/command_approval.py`; the current default `exec` tool path still enforces a static deny-list safety guard instead of prompting.

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Enable the approval helper when embedded programmatically |
| `mode` | string | `"manual"` | Approval mode: `manual` or `off` |
| `timeout` | int | `60` | Approval prompt timeout in seconds |
| `allowlist` | list[string] | `[]` | Permanently approved danger-pattern descriptions |

#### `agents.selfImprovement`

Controls the lesson-extraction and self-improvement system. See [Self-Improvement](self-improvement.md) for details.

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Enable lesson extraction |
| `maxLessonsInPrompt` | int | `5` | Maximum lessons injected per prompt |
| `minLessonConfidence` | int | `1` | Minimum confidence score for a lesson to be included |
| `maxLessons` | int | `200` | Maximum lessons retained in store |
| `lessonConfidenceDecayHours` | int | `168` | Hours before lesson confidence starts decaying |
| `feedbackMaxMessageChars` | int | `220` | Maximum message length to treat as user feedback |
| `feedbackRequirePrefix` | bool | `true` | Require correction cue as a message prefix |
| `promotionEnabled` | bool | `true` | Allow session lessons to promote to global scope |
| `promotionMinUsers` | int | `3` | Minimum distinct user count to trigger promotion |
| `promotionTriggers` | list | `["response:length", "response:language"]` | Trigger pattern list for promotion candidates |

---

### `channels`

Configures channel delivery behavior and the currently wired Feishu adapter.

#### Global Channel Fields

| Key | Type | Description |
|---|---|---|
| `sendProgress` | bool | Stream intermediate LLM output to the channel |
| `sendToolHints` | bool | Stream tool-call hints to the channel |
| `sendQueueNotifications` | bool | Notify queued users when the agent is busy |

Other adapter modules exist in the repository, but the current public config schema surfaces Feishu as the packaged gateway adapter.

#### Feishu Channel

```json
"channels": {
  "feishu": {
    "enabled": true,
    "appId": "cli_...",
    "appSecret": "...",
    "allowFrom": ["ou_xxx", "oc_yyy"],
    "replyDelayMs": 3000,
    "requireMentionInGroups": true
  }
}
```

| Key | Description |
|---|---|
| `enabled` | Enable/disable Feishu gateway mode |
| `appId` / `appSecret` | Feishu app credentials |
| `allowFrom` | Allowlist of sender open_ids. Empty means allow all. |
| `replyDelayMs` | Debounce window for rapid message bursts |
| `requireMentionInGroups` | When `true` (default), only respond in group chats when @mentioned. Private chats are unaffected. |

!!! warning "Security"
    An empty `allowFrom` list allows **all users**. Always configure `allowFrom` before exposing to any channel in production.

---

### `gateway`

HTTP gateway listen configuration.

| Key | Type | Default | Description |
|---|---|---|---|
| `host` | string | `"0.0.0.0"` | Bind address (bare-metal). Use `"127.0.0.1"` to restrict to loopback. |
| `port` | int | `18790` | Listen port |

!!! note "Docker"
    When using Docker Compose, the port is bound to `127.0.0.1:18790` by default regardless of the `host` setting.

---

### `cron`

Scheduler-wide limits.

| Key | Type | Default | Description |
|---|---|---|---|
| `jobTimeoutSeconds` | int | `86400` | Maximum runtime for a single cron job |

---

### `tools`

#### `tools.web`

| Key | Type | Default | Description |
|---|---|---|---|
| `search.provider` | string | `"brave"` | Search provider: `brave` \| `ollama` \| `hybrid` |
| `search.apiKey` | string | `""` | Brave Search API key |
| `search.ollamaApiKey` | string | `""` | Ollama web-search API key |
| `search.ollamaApiBase` | string | `"https://ollama.com"` | Ollama API base |
| `search.maxResults` | int | `5` | Maximum search results |
| `fetch.provider` | string | `"builtin"` | Fetch provider: `builtin` \| `ollama` \| `hybrid` |
| `fetch.ollamaApiBase` | string | `"https://ollama.com"` | Ollama API base URL when using ollama fetch |
| `fetch.ollamaApiKey` | string | `""` | Ollama API key |

#### `tools.papers`

| Key | Type | Default | Description |
|---|---|---|---|
| `provider` | string | `"hybrid"` | Paper search backend: `hybrid` \| `semantic_scholar` \| `arxiv` |
| `semanticScholarApiKey` | string | — | Semantic Scholar API key |
| `timeoutSeconds` | int | `20` | Request timeout |
| `defaultLimit` | int | `8` | Default result count |
| `maxLimit` | int | `20` | Maximum result count |

#### `tools.exec`

| Key | Type | Default | Description |
|---|---|---|---|
| `timeout` | int | `60` | Shell command timeout in seconds |
| `envPassthrough` | list[string] | `[]` | Credential variable names allowed to pass through to `exec` subprocesses |

#### `tools.restrictToWorkspace`

Global boolean flag on `tools` (not inside `tools.exec`). When `true`, file tools and shell execution are constrained to the configured workspace directory.

#### `tools.mcpServers`

Define external MCP tool servers. See [MCP Integration](mcp-integration.md) for full reference.

```json
"tools": {
  "mcpServers": {
    "my-server": {
      "command": "python",
      "args": ["-m", "my_mcp_server"],
      "env": {
        "MY_API_KEY": "..."
      },
      "headers": {},
      "toolTimeout": 30,
      "progressIntervalSeconds": 15,
      "lazy": true,
      "description": "Domain-specific tools exposed through a lazy gateway"
    }
  }
}
```

| Key | Type | Default | Description |
|---|---|---|---|
| `command` | string | — | Executable for stdio transport |
| `args` | list | `[]` | Command arguments |
| `env` | object | `{}` | Environment variables for the subprocess. If omitted, the stdio server inherits the current MiQi process environment. |
| `url` | string | — | HTTP transport URL (alternative to `command`) |
| `headers` | object | `{}` | Custom HTTP headers for streamable HTTP transport |
| `toolTimeout` | int | `30` | Seconds before a tool call is cancelled |
| `progressIntervalSeconds` | int | `15` | Heartbeat interval for long-running calls. `0` to disable. |
| `lazy` | bool | `false` | Register one gateway tool and activate the full MCP tool set on demand |
| `description` | string | `""` | LLM-facing description shown for lazy gateway mode |

---

### `heartbeat`

Periodic background prompts for proactive agent behaviors.

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Enable heartbeat |
| `intervalSeconds` | int | `1800` | Heartbeat interval in seconds |

---

## Environment Variable Overrides

Every config field can be overridden at runtime using the prefix `MIQI_` and `__` as the nesting delimiter:

```bash
# Override the default model
MIQI_AGENTS__DEFAULTS__MODEL=deepseek/deepseek-chat miqi agent

# Inject an API key without editing config.json
MIQI_PROVIDERS__OPENROUTER__API_KEY=sk-or-v1-xxx miqi gateway

# Override the gateway port
MIQI_GATEWAY__PORT=18791 miqi gateway
```

This is especially useful in containerized deployments where secrets are injected as environment variables.
