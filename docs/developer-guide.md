# Developer Guide

## Requirements

- Python 3.11 or 3.12
- A virtual environment is strongly recommended

## Local Installation

```bash
git clone https://github.com/lichman0405/MiQi.git
cd MiQi
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

---

## Project Structure

```
miqi/
  agent/          # Agent loop, context builder, memory system, tool wiring
  cli/            # CLI entry point and subcommand modules
  channels/       # IM and messaging channel adapters
  providers/      # LLM provider integrations
  cron/           # Scheduled task service
  session/        # Session management
  bus/            # Message bus (inbound/outbound queues)
  config/         # Config loader and schema (Pydantic)
  heartbeat/      # Heartbeat service
  skills/         # Built-in skill files (SKILL.md per skill)
  templates/      # Agent system prompt templates
tests/            # Test cases
docs/             # Project documentation (this site)
mcps/             # Bundled MCP server submodules
scripts/          # Setup and configuration helpers
```

### CLI Module Structure

| File | Purpose |
|---|---|
| `cli/commands.py` | Entry point; compatibility exports for tests |
| `cli/onboard.py` | `miqi onboard` command |
| `cli/agent_cmd.py` | `miqi agent` command |
| `cli/gateway_cmd.py` | `miqi gateway` command |
| `cli/management.py` | channels / memory / session / cron / status / provider |
| `cli/config_cmd.py` | `miqi config` subcommands |

---

## Running Tests

```bash
# Core CLI and cron tests (run these first)
PYTHONPATH=. python -m pytest tests/test_commands.py tests/test_cron_commands.py -q

# Cron service and provider tests
PYTHONPATH=. python -m pytest tests/test_cron_service.py tests/test_provider_retry.py tests/test_provider_routing.py -q

# Tool validation and fallback behavior
PYTHONPATH=. python -m pytest tests/test_tool_validation.py tests/test_tool_call_fallback.py -q

# Run the full test suite
PYTHONPATH=. python -m pytest -q
```

**Available test files:**

| File | Coverage |
|---|---|
| `test_commands.py` | CLI command registration and dispatch |
| `test_cron_commands.py` | Cron CLI commands |
| `test_cron_service.py` | Cron service scheduling logic |
| `test_provider_retry.py` | LLM provider retry behavior |
| `test_provider_routing.py` | Multi-provider routing |
| `test_tool_validation.py` | Tool schema validation |
| `test_tool_call_fallback.py` | Tool call error fallback |
| `test_cli_input.py` | CLI input handling |
| `test_heartbeat_service.py` | Heartbeat service |
| `test_email_channel.py` | Email channel adapter |
| `test_consolidate_offset.py` | Session compaction offset logic |

---

## Linting

```bash
.venv/bin/ruff check .
```

Line length is set to 100. Target version is Python 3.11.

---

## Coding Style

- Use `loguru.logger` for all runtime logging; never use `print()` in business logic
- Prefer minimal, testable changes
- Keep each module focused on its domain
- Do not add docstrings or comments to code you didn't change

---

## Adding a New Tool

1. Create the tool in `miqi/agent/tools/<name>.py`
2. Register it in `miqi/agent/tools/registry.py`
3. Update `miqi/templates/TOOLS.md` with usage guidance
4. Update `docs/cli-reference.md` with the tool reference
5. Add tests in `tests/`

---

## Adding a New Channel Adapter

1. Create the adapter in `miqi/channels/<name>.py` extending `BaseChannel`
2. Register it in `miqi/channels/manager.py`
3. Add the channel config schema in `miqi/config/schema.py`

---

## Commit Guidance

- Keep each commit focused on one theme (e.g. "cron: fix UTC fallback", "CLI: split commands")
- Commit messages should include: motivation, scope, and test commands used
- When adding or updating tools, keep these in sync:
  - `miqi/templates/TOOLS.md`
  - `docs/cli-reference.md`
  - `CHANGELOG.md`

---

## Documentation

This docs site is built with [MkDocs Material](https://squidfunk.github.io/mkdocs-material/).

```bash
pip install mkdocs-material
mkdocs serve          # local preview at http://127.0.0.1:8000
mkdocs build          # build static site to site/
```

When changing behavior or interfaces, update the relevant doc in `docs/` and add an entry to `CHANGELOG.md`.
