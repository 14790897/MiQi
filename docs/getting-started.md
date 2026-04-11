# Getting Started

## Requirements

- Python 3.11 or 3.12
- Linux or macOS (recommended for production; Windows supported for development)
- `git` (required for submodule-based MCP servers)

---

## Installation

### Standard Install

```bash
git clone https://github.com/lichman0405/MiQi.git
cd MiQi

python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

pip install --upgrade pip
pip install -e .

miqi --version
```

### With Dev Dependencies

```bash
pip install -e '.[dev]'
```

### Docker (Recommended for Production)

```bash
# Start the gateway
docker compose up --build miqi-gateway

# Run a one-off CLI command in the container
docker compose --profile cli run --rm miqi-cli status
```

The container runs as unprivileged user `miqi` (UID 1000). The gateway port is bound to `127.0.0.1:18790` by default.

| Location | Path |
|---|---|
| Host runtime data | `~/.miqi` |
| Container runtime data | `/home/miqi/.miqi` |

---

## First Run

### 1. Run the Onboarding Wizard

```bash
miqi onboard
```

This interactive wizard creates `~/.miqi/config.json` and configures:

- LLM provider and API key
- Default model, temperature, and agent identity
- Optional paper research tool (`tools.papers` provider, API key, limits)

### 2. Chat with the Agent

```bash
# Send a one-shot message and exit
miqi agent -m "hello"

# Start an interactive chat session
miqi agent
```

### 3. Start the Gateway

```bash
# Run channels + scheduled tasks as a long-running service
miqi gateway
```

The packaged gateway path currently wires Feishu, cron, memory/session persistence, and configured MCP servers. Additional channel adapter modules live in the repository but are not yet surfaced through the public config schema.

### 4. Check Status

```bash
miqi status
```

---

## MCP Server Setup (Optional)

MiQi ships with seven bundled domain-specific MCP servers as git submodules. See [MCP Integration](mcp-integration.md) for full details.

```bash
# Clone with submodules (if not done already)
git clone --recurse-submodules https://github.com/lichman0405/MiQi.git

# Or update submodules in an existing clone
git submodule update --init --recursive

# Install isolated Python venvs for each MCP server
bash scripts/setup_mcps.sh

# Register all bundled MCPs into ~/.miqi/config.json
bash scripts/configure_mcps.sh
```

Add credentials for servers that need them (pdf2zh, feishu) directly in `~/.miqi/config.json`. See [MCP Integration](mcp-integration.md#credentials).

---

## Bare-Metal Gateway Deployment

For running the gateway as a long-running service without Docker on Linux:

**1. Create the service file** at `/etc/systemd/system/miqi.service`:

```ini
[Unit]
Description=MiQi AI Agent Gateway
After=network.target

[Service]
Type=simple
User=miqi
WorkingDirectory=/home/miqi
ExecStart=/home/miqi/.local/bin/miqi gateway
Restart=on-failure
RestartSec=10
Environment=HOME=/home/miqi

[Install]
WantedBy=multi-user.target
```

**2. Enable and start:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now miqi
sudo journalctl -u miqi -f   # tail logs
```

On macOS, use `launchd` or `supervisord` instead.

**3. Optional: Reverse proxy for external access**

The gateway listens on `127.0.0.1:18790`. To expose it externally:

```nginx
server {
    listen 443 ssl;
    server_name miqi.example.com;

    location / {
        proxy_pass http://127.0.0.1:18790;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Upgrading

```bash
cd MiQi
git pull --recurse-submodules
pip install -e .
bash scripts/setup_mcps.sh          # update MCP venvs
bash scripts/configure_mcps.sh      # re-register MCPs (idempotent)
# then restart the gateway:
sudo systemctl restart miqi
# or for Docker:
docker compose up --build miqi-gateway
```

---

## Migration from `nanobot`

| Item | Old | New |
|---|---|---|
| Python package | `nanobot.*` | `miqi.*` |
| CLI command | `assistant` | `miqi` |
| Runtime directory | `~/.assistant` | `~/.miqi` |
| Workspace directory | `~/.assistant/workspace` | `~/.miqi/workspace` |

Backward-compatible fallbacks for old config and data paths are retained where possible.
