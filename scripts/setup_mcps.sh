#!/usr/bin/env bash
# setup_mcps.sh — Install Python venvs for all bundled MCP submodules.
#
# Requirements:
#   - uv (https://docs.astral.sh/uv/getting-started/installation/)
#   - git submodules already initialised (run with --init if not)
#
# Usage:
#   bash scripts/setup_mcps.sh [--init]
#
#   --init   Also initialise / update git submodules before installing.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MCPS_DIR="$REPO_ROOT/mcps"

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'  # no colour

info()    { echo -e "${GREEN}[setup_mcps]${NC} $*"; }
warn()    { echo -e "${YELLOW}[setup_mcps] WARN:${NC} $*"; }
error()   { echo -e "${RED}[setup_mcps] ERROR:${NC} $*" >&2; exit 1; }

check_cmd() {
    command -v "$1" &>/dev/null || error "'$1' is not installed. $2"
}

# ──────────────────────────────────────────────────────────────────────────────
# Pre-flight checks
# ──────────────────────────────────────────────────────────────────────────────

check_cmd uv "Install via: curl -LsSf https://astral.sh/uv/install.sh | sh"
check_cmd git "Install git first."

# Optional: initialise / update submodules
if [[ "${1:-}" == "--init" ]]; then
    info "Initialising git submodules..."
    git -C "$REPO_ROOT" submodule update --init --recursive
fi

# Verify submodule directories are populated
for dir in zeopp-backend raspa-mcp mofstructure-mcp mofchecker-mcp pdftranslate-mcp feishu-mcp miqrophi-mcp; do
    [[ -d "$MCPS_DIR/$dir" ]] || error \
        "Directory mcps/$dir is missing. Run: bash scripts/setup_mcps.sh --init"
done

# ──────────────────────────────────────────────────────────────────────────────
# Helper: create venv + install package
# ──────────────────────────────────────────────────────────────────────────────

setup_venv() {
    local name="$1"
    local python_ver="$2"   # e.g. "3.10", "3.12", or "" to let uv choose
    local dir="$MCPS_DIR/$name"

    info "Setting up $name (Python ${python_ver:-auto})..."
    pushd "$dir" > /dev/null

    if [[ -n "$python_ver" ]]; then
        uv venv .venv --python "$python_ver"
    else
        uv venv .venv
    fi

    # Install package in editable mode into the new venv
    uv pip install --python .venv/bin/python -e . --quiet

    popd > /dev/null
    info "  ✓ $name"
}

# ──────────────────────────────────────────────────────────────────────────────
# Helper: uv sync (for projects whose pyproject.toml drives everything)
# ──────────────────────────────────────────────────────────────────────────────

setup_uv_sync() {
    local name="$1"
    local dir="$MCPS_DIR/$name"

    info "Setting up $name (uv sync)..."
    pushd "$dir" > /dev/null
    uv sync --quiet
    popd > /dev/null
    info "  ✓ $name"
}

# ──────────────────────────────────────────────────────────────────────────────
# Per-MCP setup
# ──────────────────────────────────────────────────────────────────────────────

# zeopp-backend — Python 3.10+, uses uv natively
setup_uv_sync "zeopp-backend"

# raspa-mcp — Python 3.11+, uses uv natively
setup_uv_sync "raspa-mcp"
warn "raspa-mcp: The RASPA2 simulation engine must be compiled separately."
warn "  After this script finishes, run once: cd mcps/raspa-mcp && uv run raspa-mcp-setup"

# mofstructure-mcp — Python 3.9+
setup_venv "mofstructure-mcp" "3.12"

# mofchecker-mcp — REQUIRES Python < 3.11 (pyeqeq / pybind11 constraint)
setup_venv "mofchecker-mcp" "3.10"

# pdftranslate-mcp — Python 3.10–3.12 (pdf2zh does NOT support 3.13+)
setup_venv "pdftranslate-mcp" "3.12"

# feishu-mcp — Python 3.11+
setup_venv "feishu-mcp" "3.12"

# miqrophi-mcp — Python 3.10+ (epitaxial lattice matching), install with MCP extras
info "Setting up miqrophi-mcp (Python 3.12)..."
pushd "$MCPS_DIR/miqrophi-mcp" > /dev/null
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -e ".[mcp]" --quiet
popd > /dev/null
info "  ✓ miqrophi-mcp"

# ──────────────────────────────────────────────────────────────────────────────
# Done
# ──────────────────────────────────────────────────────────────────────────────

echo ""
info "All MCP venvs installed successfully."
echo ""
echo "  ⚠️  RASPA2 engine still needs one-time compilation:"
echo "       cd mcps/raspa-mcp && uv run raspa-mcp-setup"
echo ""
echo "  Next step: register MCPs with featherflow:"
echo "    bash scripts/configure_mcps.sh"
echo ""
echo "  Or manually add the mcpServers block from docs/MCP_SETUP.md to your"
echo "  ~/.featherflow/config.json."
