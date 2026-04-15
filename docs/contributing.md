# Contributing

Thanks for contributing to MiQi.

## Before You Start

1. Fork the repository and create a branch.
2. Install the local development environment:
   ```bash
   uv sync --extra dev        # recommended
   # or: pip install -e '.[dev]'
   ```
3. Read these docs before making changes:
   - [Architecture](architecture.md)
   - [Developer Guide](developer-guide.md)

## Development Principles

- Make minimal and verifiable changes.
- Preserve backward compatibility (especially public CLI behavior).
- Use `loguru.logger` for logging; avoid `print()` in business logic.
- Do not refactor unrelated areas.

## Testing Requirements

Run at least the tests relevant to your changes before submitting:

```bash
PYTHONPATH=. python -m pytest tests/test_commands.py tests/test_cron_commands.py -q
```

If your change touches cron or agent core behavior, also run:

```bash
PYTHONPATH=. python -m pytest tests/test_cron_service.py tests/test_provider_routing.py -q
```

For the full suite:

```bash
PYTHONPATH=. python -m pytest -q
```

## Pull Request Guidelines

Your PR description should include:

- Background and goal
- Key changes made
- Risk and backward-compatibility notes
- Test commands run and their results

## Documentation

If your changes affect behavior or interfaces, update the relevant files:

- `docs/cli-reference.md` — CLI commands and tools
- `docs/configuration.md` — Config options
- `docs/architecture.md` — Module or data flow changes
- `miqi/templates/TOOLS.md` — Tool usage guidance
- `CHANGELOG.md` — Always add a changelog entry
