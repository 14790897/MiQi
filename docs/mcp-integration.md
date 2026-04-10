# MCP Integration

MiQi supports the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) for connecting external tool servers. Both **stdio** (subprocess) and **HTTP** transports are supported.

---

## Bundled MCP Servers

MiQi ships with seven domain-specific MCP servers as git submodules under `mcps/`.

| Name | Submodule | Python | Description |
|---|---|---|---|
| **zeopp** | `mcps/zeopp-backend` | 3.10+ | Zeo++ porous material geometry — volume, pore size, channels |
| **raspa2** | `mcps/raspa-mcp` | 3.11+ | RASPA2 molecular simulation — input templates, output parsing |
| **mofstructure** | `mcps/mofstructure-mcp` | 3.9+ | MOF structural analysis — building blocks, topology, metal nodes |
| **mofchecker** | `mcps/mofchecker-mcp` | **<3.11** | MOF structure validation — CIF integrity, geometry defects |
| **miqrophi** | `mcps/miqrophi-mcp` | 3.10+ | Epitaxial lattice matching — CIF surface analysis, substrate screening, strain |
| **pdf2zh** | `mcps/pdftranslate-mcp` | 3.10–3.12 | PDF paper translation preserving LaTeX layout |
| **feishu** | `mcps/feishu-mcp` | 3.11+ | Feishu/Lark — messaging, docs, calendar, tasks |

### Setup

**1. Clone with submodules:**

```bash
git clone --recurse-submodules https://github.com/lichman0405/MiQi.git
# or if you already cloned without submodules:
git submodule update --init --recursive
```

**2. Install Python venvs for each MCP server:**

```bash
bash scripts/setup_mcps.sh
```

The script uses [`uv`](https://docs.astral.sh/uv/) and pins the correct Python version per server (note `mofchecker` requires Python < 3.11; `pdf2zh` requires ≤ 3.12).

**3. Register all MCPs with MiQi:**

```bash
bash scripts/configure_mcps.sh
```

This calls `miqi config mcp add` for every server with recommended timeouts and settings.

---

## Credentials {#credentials}

Two bundled servers require credentials. Add these to `~/.miqi/config.json` after running `scripts/configure_mcps.sh`:

```jsonc
"tools": {
  "mcpServers": {
    "pdf2zh": {
      "env": {
        "OPENAI_BASE_URL": "https://api.openai.com/v1",
        "OPENAI_API_KEY":  "sk-...",
        "OPENAI_MODEL":    "gpt-4o"
      }
    },
    "feishu": {
      "env": {
        "FEISHU_APP_ID":     "cli_...",
        "FEISHU_APP_SECRET": "..."
      }
    }
  }
}
```

Alternatively, use the guided setup commands:

```bash
miqi config pdf2zh     # auto-fills LLM credentials from configured provider
miqi config feishu     # configures Feishu channel + feishu-mcp together
```

!!! note "Security"
    MCP subprocesses launched via stdio transport inherit only a minimal environment (`HOME`, `PATH`, `SHELL`, `USER`, `TERM`, `LOGNAME`). Your LLM provider API keys are **never** exposed to MCP servers unless you explicitly add them to `env` as shown above.

---

## Adding a Custom MCP Server

### Via CLI

```bash
# Add a stdio MCP server
miqi config mcp add my-server

# Add an HTTP MCP server
miqi config mcp add my-http-server
```

### Via Config File

**Stdio transport (subprocess):**

```json
"tools": {
  "mcpServers": {
    "my-server": {
      "command": "python",
      "args": ["-m", "my_mcp_package"],
      "env": {
        "MY_API_KEY": "..."
      }
    }
  }
}
```

**HTTP transport:**

```json
"tools": {
  "mcpServers": {
    "my-http-server": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

---

## Tool Filtering

You can restrict which tools from an MCP server are exposed to the agent:

```json
"tools": {
  "mcpServers": {
    "feishu": {
      "command": "...",
      "allowedTools": ["send_message", "create_document"],
      "deniedTools": ["set_doc_permission", "set_doc_public_access"]
    }
  }
}
```

| Field | Behavior |
|---|---|
| `allowedTools` | When non-empty, only these tools are registered. All others are silently dropped. |
| `deniedTools` | These tools are never registered, regardless of `allowedTools`. |

---

## Timeouts and Progress Reporting

For long-running operations (e.g. scientific computing, PDF translation):

```json
"tools": {
  "mcpServers": {
    "raspa2": {
      "toolTimeout": 600,
      "progressIntervalSeconds": 30
    }
  }
}
```

| Field | Default | Description |
|---|---|---|
| `toolTimeout` | `30` | Seconds before a tool call is cancelled |
| `progressIntervalSeconds` | `15` | Heartbeat interval. Set `0` to disable. |

MiQi sends the user elapsed-time updates (e.g. "⏳ raspa_run_simulation — 1m 30s elapsed") every `progressIntervalSeconds` while a tool is running.

---

## Managing MCP Servers

```bash
miqi config mcp list             # list all configured MCP servers
miqi config mcp add <name>       # add or update a server
miqi config mcp remove <name>    # remove a server
```
