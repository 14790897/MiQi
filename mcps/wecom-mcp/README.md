# wecom-mcp

> 🤖 **WeCom AI Bot MCP Server** — Connect AI Agents to WeCom Smart Bot via WebSocket long connection (botId + secret only).

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![MCP](https://img.shields.io/badge/Protocol-MCP-purple)](https://modelcontextprotocol.io/)

---

## Features

| Capability | Functions |
|------------|-----------|
| 💬 Messages | Send messages (text/markdown/image/file/video/voice/textcard/news/template_card) to users or groups, reply to incoming messages |
| 📎 Media | Upload temporary media (image/voice/video/file → media_id), download encrypted media with automatic AES decryption |
| 🔔 Events | Receive enter_chat events and auto-send welcome messages via WebSocket callbacks |

---

## Quick Start

### 1. Create WeCom Smart Bot

1. Open WeCom Client → **Workbench** → **Smart Bot**
2. Click **Create Bot** → **Manual** → **API Mode**
3. Note down your **Bot ID** and **Secret**

### 2. Clone and install

```bash
git clone <repo-url>
cd mcps/wecom-mcp

python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -e .
```

### 3. Configure credentials

```bash
cp .env.example .env
```

Edit `.env`:

```env
WECOM_BOT_ID=aib5xg2K_xxxxxxxxxxxx
WECOM_BOT_SECRET=your_bot_secret_here
WECOM_WELCOME_MESSAGE=Hello! I am an AI assistant. How can I help you?
```

### 4. Verify installation

```bash
python -m wecom_mcp.server
```

You should see `WeCom AI Bot connected and authenticated` in the logs.

---

## Connect an AI Agent

### MiQi / Claude Desktop / Cursor

Edit your MCP configuration:

**MiQi** (`~/.miqi/config.json` or `mcpServers` in project config):

```json
{
  "mcpServers": {
    "wecom-mcp": {
      "command": "python",
      "args": ["-m", "wecom_mcp.server"],
      "env": {
        "WECOM_BOT_ID": "aib5xg2K_xxx",
        "WECOM_BOT_SECRET": "xxx",
        "WECOM_WELCOME_MESSAGE": "Hi! I'm your AI assistant."
      }
    }
  }
}
```

**Claude Desktop** (`%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "wecom-mcp": {
      "command": "C:/path/to/wecom-mcp/.venv/Scripts/python.exe",
      "args": ["-m", "wecom_mcp.server"],
      "env": {
        "WECOM_BOT_ID": "aib5xg2K_xxx",
        "WECOM_BOT_SECRET": "xxx"
      }
    }
  }
}
```

---

## Tool List

| Tool | Description |
|------|-------------|
| `send_message` | Send message to user or group (text/markdown/image/file/video/voice/textcard/news/template_card) |
| `reply_message` | Reply to a received message (passive reply using req_id) |
| `upload_media` | Upload local file → media_id (valid 3 days) |
| `download_media` | Download encrypted media from message URL (auto-decrypts) |

---

## Architecture

```
AI Agent (MiQi / Claude)
    ↕ stdio (MCP protocol)
wecom_mcp.server
    ↕ WebSocket long connection (wss://openws.work.weixin.qq.com)
WeCom Smart Bot
    ↕
WeCom Users / Groups
```

**Key differences from the old self-built app API:**

| | Self-built App (old) | Smart Bot AI Bot (this) |
|---|---|---|
| Credentials | corpid + corpsecret + agentid (3 vars) | botId + secret (2 vars) |
| Connection | Webhook HTTP callback (needs public IP) | WebSocket long connection (no public IP needed) |
| Message receive | Poll via callback URL | Push via WebSocket |
| Protocol | HTTP REST API | WebSocket + SDK |
| Auth | access_token (2h expiry, auto-refresh) | BotId + Secret (persistent) |

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
```

---

## License

[MIT](LICENSE) © 2026 wecom-mcp contributors
