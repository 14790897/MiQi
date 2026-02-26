# Contributing

Thanks for contributing to FeatherFlow.

## Before You Start

1. Fork the repository and create a branch.
2. Install the local development environment: `pip install -e .`
3. Read these docs before making changes:
   - `README.md`
   - `docs/DEVELOPER_GUIDE.md`
   - `docs/ARCHITECTURE.md`

## Development Principles

- Make minimal and verifiable changes.
- Preserve backward compatibility (especially public CLI behavior).
- Use `loguru.logger` for logging and avoid adding built-in `print()`.
- Do not refactor unrelated areas.

## Testing Requirements

Run at least the tests relevant to your changes before submitting:

```bash
python -m pytest tests/test_commands.py tests/test_cron_commands.py -q
```

If your change touches cron or agent core behavior, also run:

```bash
python -m pytest tests/test_agent_loop_core.py tests/test_cron_service_core.py -q
```

## Pull Request Guidelines

Your PR description should include:
- Background and goal
- Key changes
- Risk and compatibility notes
- Test commands and results

## Documentation

If your changes affect behavior or interfaces, update these files as needed:
- `docs/API.md`
- `docs/DEVELOPER_GUIDE.md`
- `docs/ARCHITECTURE.md`
- `CHANGELOG.md`
