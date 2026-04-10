# Configuration

MiQi reads configuration from `~/.miqi/config.json`. The interactive wizard (`miqi onboard`) generates this file. Config files are automatically saved with `0600` permissions to protect API keys.

---

## Config File Location

| Item | Default Path |
|---|---|
| Config file | `~/.miqi/config.json` |
| Workspace | `~/.miqi/workspace` |
| Memory | `~/.miqi/memory/` |
| Sessions | `~/.miqi/sessions/` |

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
      "temperature": 0.7
    }
  },
  "channels": {},
  "tools": {
    "web": {
      "enabled": true
    }
  },
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

Supported providers: `openrouter`, `openai`, `anthropic`, `deepseek`, `gemini`, `groq`, `moonshot`, `minimax`, `zhipuai`, `dashscope`, `siliconflow`, `volcengine`, `aihubmix`, `vllm`, `ollama`, `openai-codex`.

---

### `agents`

#### `agents.defaults`

Default settings applied to all agent instances.

| Key | Type | Default | Description |
|---|---|---|---|
| `model` | string | — | Model identifier (e.g. `anthropic/claude-opus-4-5`) |
| `name` | string | `"miqi"` | Agent display name |
| `temperature` | float | `0.7` | LLM sampling temperature |
| `maxTokens` | int | — | Maximum output tokens per response |
| `maxToolIterations` | int | `20` | Maximum tool-call rounds per turn |
| `memoryWindow` | int | — | Short-term memory window size |
| `workspace` | string | `~/.miqi/workspace` | Working directory for file operations |

#### `agents.memory`

Controls memory persistence cadence.

| Key | Type | Default | Description |
|---|---|---|---|
| `flushEveryUpdates` | int | `10` | Flush memory to disk after this many updates |
| `flushIntervalSeconds` | int | `300` | Flush memory to disk every N seconds |

#### `agents.sessions`

Controls session compaction.

| Key | Type | Default | Description |
|---|---|---|---|
| `compactThresholdMessages` | int | `200` | Trigger compaction above this many messages |
| `compactThresholdBytes` | int | — | Trigger compaction above this file size |
| `compactKeepMessages` | int | `50` | Number of recent messages to retain after compaction |

#### `agents.selfImprovement`

Controls the lesson-extraction and self-improvement system. See [Self-Improvement](self-improvement.md) for details.

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Enable lesson extraction |
| `maxLessonsInPrompt` | int | `5` | Maximum lessons injected per prompt |
| `minLessonConfidence` | float | `0.5` | Minimum confidence score for a lesson to be included |
| `maxLessons` | int | `500` | Maximum lessons retained in store |
| `lessonConfidenceDecayHours` | int | `168` | Hours before lesson confidence starts decaying |
| `feedbackMaxMessageChars` | int | `500` | Maximum message length to treat as user feedback |
| `feedbackRequirePrefix` | bool | `true` | Require correction cue as a message prefix |
| `promotionEnabled` | bool | `true` | Allow session lessons to promote to global scope |
| `promotionMinUsers` | int | `2` | Minimum distinct user count to trigger promotion |
| `promotionTriggers` | list | — | Trigger pattern list for promotion candidates |

---

### `channels`

Configures IM channel adapters. Each channel is optional and disabled until configured.

#### Common Channel Fields

| Key | Type | Description |
|---|---|---|
| `enabled` | bool | Enable/disable the channel |
| `allowFrom` | list[string] | Allowlist of user/chat IDs. **Empty = allow all.** |
| `sendProgress` | bool | Stream intermediate LLM output to the channel |
| `sendToolHints` | bool | Stream tool-call hints to the channel |

#### `channels.sendQueueNotifications`

When `true` (default), users are notified of their position in the task queue when the agent is busy.

#### Feishu Channel

```json
"channels": {
  "feishu": {
    "enabled": true,
    "appId": "cli_...",
    "appSecret": "...",
    "verificationToken": "...",
    "encryptKey": "...",
    "allowFrom": ["ou_xxx", "oc_yyy"],
    "requireMentionInGroups": true
  }
}
```

| Key | Description |
|---|---|
| `requireMentionInGroups` | When `true` (default), only respond in group chats when @mentioned. Private chats are unaffected. |

#### Telegram Channel

```json
"channels": {
  "telegram": {
    "enabled": true,
    "token": "YOUR_BOT_TOKEN",
    "allowFrom": ["123456789"]
  }
}
```

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

### `tools`

#### `tools.web`

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Enable web tools |
| `search.provider` | string | `"brave"` | Search provider: `brave` \| `ollama` \| `hybrid` |
| `search.maxResults` | int | `5` | Maximum search results |
| `fetch.provider` | string | `"builtin"` | Fetch provider: `builtin` \| `ollama` \| `hybrid` |
| `fetch.ollamaApiBase` | string | — | Ollama API base URL when using ollama fetch |
| `fetch.ollamaApiKey` | string | — | Ollama API key |

#### `tools.papers`

| Key | Type | Default | Description |
|---|---|---|---|
| `provider` | string | `"hybrid"` | Paper search backend: `hybrid` \| `semantic_scholar` \| `arxiv` |
| `semanticScholarApiKey` | string | — | Semantic Scholar API key |
| `timeoutSeconds` | int | `30` | Request timeout |
| `defaultLimit` | int | `5` | Default result count |
| `maxLimit` | int | `20` | Maximum result count |

#### `tools.exec`

| Key | Type | Default | Description |
|---|---|---|---|
| `timeout` | int | `60` | Shell command timeout in seconds |
| `restrictToWorkspace` | bool | `false` | Restrict file operations to workspace directory |

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
      "toolTimeout": 30,
      "progressIntervalSeconds": 15,
      "allowedTools": [],
      "deniedTools": []
    }
  }
}
```

| Key | Type | Default | Description |
|---|---|---|---|
| `command` | string | — | Executable for stdio transport |
| `args` | list | `[]` | Command arguments |
| `env` | object | `{}` | Environment variables for the subprocess |
| `url` | string | — | HTTP transport URL (alternative to `command`) |
| `toolTimeout` | int | `30` | Seconds before a tool call is cancelled |
| `progressIntervalSeconds` | int | `15` | Heartbeat interval for long-running calls. `0` to disable. |
| `allowedTools` | list | `[]` | Allowlist of tool names. Empty = allow all. |
| `deniedTools` | list | `[]` | Denylist of tool names. Always excluded. |

---

### `heartbeat`

Periodic background prompts for proactive agent behaviors.

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Enable heartbeat |
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
