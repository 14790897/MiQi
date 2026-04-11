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
  For stdio transport, MiQi forwards the `env` mapping you configure for that server. If you omit `env`, the MCP subprocess inherits the current MiQi process environment. Treat stdio MCP servers as trusted local code and explicitly scope `env` when you need tighter isolation.

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

## Lazy Gateway Mode

When an MCP server exposes many tools, send the tool surface lazily instead of registering everything on every model call:

```json
"tools": {
  "mcpServers": {
    "raspa2": {
      "command": "/path/to/python",
      "args": ["-m", "raspa_mcp.server"],
      "lazy": true,
      "description": "RASPA molecular simulation: gas adsorption, GCMC and MD workflows"
    }
  }
}
```

In lazy mode, MiQi initially registers one gateway tool such as `use_raspa2`. Once the model activates it, the concrete MCP tools are loaded into the registry for the remainder of that agent-loop run.

Equivalent CLI example:

```bash
miqi config mcp add raspa2 \
  --command /path/to/python \
  --arg -m \
  --arg raspa_mcp.server \
  --lazy \
  --description "RASPA molecular simulation: gas adsorption, GCMC and MD workflows"
```

---

## Runtime Fields

For long-running operations (e.g. scientific computing, PDF translation), these fields control transport and execution behavior:

```json
"tools": {
  "mcpServers": {
    "raspa2": {
      "toolTimeout": 600,
      "progressIntervalSeconds": 30,
      "lazy": true,
      "description": "RASPA molecular simulation workflows"
    }
  }
}
```

| Field | Default | Description |
|---|---|---|
| `command` | — | Executable for stdio transport |
| `args` | `[]` | Arguments for the stdio process |
| `env` | `{}` | Environment mapping passed to the stdio server. If omitted, the server inherits the current process environment. |
| `url` | — | Streamable HTTP endpoint |
| `headers` | `{}` | Custom HTTP headers for streamable HTTP transport |
| `toolTimeout` | `30` | Seconds before a tool call is cancelled |
| `progressIntervalSeconds` | `15` | Heartbeat interval. Set `0` to disable. |
| `lazy` | `false` | Register one lightweight gateway tool until activation |
| `description` | `""` | LLM-facing description for lazy gateway mode |

MiQi sends the user elapsed-time updates (e.g. "⏳ raspa_run_simulation — 1m 30s elapsed") every `progressIntervalSeconds` while a tool is running.

---

## Managing MCP Servers

```bash
miqi config mcp list             # list all configured MCP servers
miqi config mcp add <name>       # add or update a server
miqi config mcp remove <name>    # remove a server
```
