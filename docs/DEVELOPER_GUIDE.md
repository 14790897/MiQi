# FeatherFlow Developer Guide

## Requirements

- Python 3.11+
- A virtual environment is recommended (venv/conda)

## Local Installation

```bash
pip install -e .
```

Install optional dependencies as needed.

## Common Development Commands

```bash
# Run core tests
python -m pytest tests/test_commands.py tests/test_cron_commands.py -q

# Run additional core tests
python -m pytest tests/test_agent_loop_core.py tests/test_cron_service_core.py -q

# Paper tool coverage
python -m pytest tests/test_paper_tools.py -q
```

## Project Structure (Core)

- `featherflow/agent/`: Agent loop, context builder, memory system, and tool wiring
- `featherflow/cli/`: CLI entrypoint and command modules
- `featherflow/channels/`: Channel adapters
- `featherflow/providers/`: LLM provider integrations
- `featherflow/cron/`: Scheduled task service
- `featherflow/session/`: Session management
- `tests/`: Test cases

## CLI Split Conventions

- `commands.py`: entrypoint and compatibility exports (keeps test-dependent helpers)
- `onboard.py`: onboarding command registration
- `agent_cmd.py`: agent command registration
- `gateway_cmd.py`: gateway command registration
- `management.py`: channels/memory/session/cron/status/provider registrations

## Coding Style

- Use `loguru.logger` for runtime logging
- Avoid adding built-in `print()` in business logic
- Prefer minimal, testable, and reversible changes

## Testing Guidance

- Run nearby tests first, then broader suites
- For async tests, ensure `pytest-asyncio` is installed

## Commit Guidance

- Keep each commit focused on one theme (for example, "CLI split" or "papers parser dedup")
- Commit messages should include motivation, scope, and verification commands
- When adding/updating tools, keep docs in sync:
  - `featherflow/templates/TOOLS.md`
  - `docs/API.md`
  - `CHANGELOG.md`
