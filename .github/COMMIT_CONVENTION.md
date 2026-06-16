# Commit Convention

This project uses [Conventional Commits](https://www.conventionalcommits.org/) with [semantic-release](https://semantic-release.gitbook.io/) for automated versioning.

## Format

```
<type>(<scope>): <subject>

[body]

[footer]
```

## Types

| Type | Description | Version Bump |
|------|-------------|-------------|
| `feat` | New feature | Minor (0.x.0) |
| `fix` | Bug fix | Patch (0.0.x) |
| `perf` | Performance improvement | Patch |
| `refactor` | Code refactoring | Patch |
| `docs` | Documentation only | No release |
| `style` | Code style (formatting) | No release |
| `test` | Adding/updating tests | No release |
| `ci` | CI/CD changes | No release |
| `chore` | Maintenance tasks | No release |
| `build` | Build system changes | No release |
| `revert` | Revert a commit | Depends |

## Breaking Changes

Add `BREAKING CHANGE:` in the footer or `!` after the type:

```
feat!: drop support for Python 3.10

BREAKING CHANGE: minimum Python version is now 3.11
```

This triggers a **major** version bump (x.0.0).

## Examples

```bash
# Feature
feat(agent): add parallel tool execution support

# Bug fix
fix(sandbox): resolve UTF-16LE encoding in WSL output

# With scope
fix(desktop): reset streaming state on session switch

# Breaking change
feat(api)!: change chat.send return type to include req_id

# Multi-line
feat(wsl): add WSL status monitoring page

Add a dedicated page for monitoring WSL distro status including
CPU, memory, and disk usage with auto-refresh.

Closes #42
```

## Tools

```bash
# Interactive commit helper
npm run commit

# Dry-run release (see what would happen)
npm run release:dry
```

## Scopes (optional)

Common scopes for this project:
- `agent` — AgentLoop, tools, LLM integration
- `sandbox` — bwrap sandbox isolation
- `desktop` — Electron frontend
- `bridge` — Python bridge server
- `wsl` — WSL integration
- `ci` — GitHub Actions workflows
