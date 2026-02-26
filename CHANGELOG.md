# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Added modular CLI command files:
  - `featherflow/cli/onboard.py`
  - `featherflow/cli/agent_cmd.py`
  - `featherflow/cli/gateway_cmd.py`
  - `featherflow/cli/management.py`
- Added core regression tests:
  - `tests/test_agent_loop_core.py`
  - `tests/test_cron_service_core.py`
- Added project documentation:
  - `docs/API.md`
  - `docs/DEVELOPER_GUIDE.md`
  - `docs/ARCHITECTURE.md`
  - `CONTRIBUTING.md`

### Changed
- Refactored `featherflow/cli/commands.py` into an entry/compatibility layer that registers split command modules.
- Refactored arXiv XML parsing in `featherflow/agent/tools/papers.py` by extracting shared `_parse_arxiv_entry` logic.
- Replaced remaining built-in `print()` calls with `loguru.logger` warnings in `featherflow/config/loader.py`.
- Split memory implementation into package modules with `MemoryStore` facade in `featherflow/agent/memory/store.py`.
