#!/usr/bin/env bash
# configure_mcps.sh — Register all bundled MCP servers into your featherflow config.
#
# This script calls `featherflow config mcp add` for each bundled MCP so you
# do not have to edit config.json by hand.  Credentials (API keys etc.) are
# purposely NOT written here — see the prompts at the end.
#
# Prerequisites:
#   1. featherflow is installed (pip install -e . or uv pip install -e .)
#   2. scripts/setup_mcps.sh has already been run (venvs exist)
#
# Usage:
#   bash scripts/configure_mcps.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MCPS_DIR="$REPO_ROOT/mcps"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[configure_mcps]${NC} $*"; }
warn()  { echo -e "${YELLOW}[configure_mcps] WARN:${NC} $*"; }
error() { echo -e "${RED}[configure_mcps] ERROR:${NC} $*" >&2; exit 1; }

# ──────────────────────────────────────────────────────────────────────────────
# Pre-flight
# ──────────────────────────────────────────────────────────────────────────────

command -v featherflow &>/dev/null || error \
    "featherflow is not in PATH. Install it first: pip install -e ."

for dir in zeopp-backend raspa-mcp mofstructure-mcp mofchecker-mcp pdftranslate-mcp feishu-mcp miqrophi-mcp; do
    [[ -d "$MCPS_DIR/$dir/.venv" || -f "$MCPS_DIR/$dir/uv.lock" ]] || {
        warn "mcps/$dir does not appear set up — run scripts/setup_mcps.sh first."
    }
done

# ──────────────────────────────────────────────────────────────────────────────
# Resolve per-MCP Python interpreters
# ──────────────────────────────────────────────────────────────────────────────

MOFSTRUCTURE_CMD="$MCPS_DIR/mofstructure-mcp/.venv/bin/python"
MOFCHECKER_CMD="$MCPS_DIR/mofchecker-mcp/.venv/bin/python"
PDF2ZH_CMD="$MCPS_DIR/pdftranslate-mcp/.venv/bin/python"
FEISHU_CMD="$MCPS_DIR/feishu-mcp/.venv/bin/python"
MIQROPHI_CMD="$MCPS_DIR/miqrophi-mcp/.venv/bin/python"

# ──────────────────────────────────────────────────────────────────────────────
# Register each server (non-interactive, no credentials)
# ──────────────────────────────────────────────────────────────────────────────

register() {
    local label="$1"
    shift
    info "Registering $label..."
    featherflow config mcp add "$@"
    info "  ✓ $label"
}

# zeopp-backend — no credentials needed, long-running analysis
register "zeopp" zeopp \
    --command "$ZEOPP_CMD" \
    --arg run \
    --arg --project \
    --arg "$MCPS_DIR/zeopp-backend" \
    --arg python \
    --arg -m \
    --arg app.mcp.stdio_main \
    --timeout 300 \
    --lazy \
    --description "Zeo++ porous material geometry analysis: accessible volume, pore size, channel detection"

# raspa-mcp — RASPA2 simulation templates
register "raspa2" raspa2 \
    --command "$RASPA2_CMD" \
    --arg run \
    --arg --directory \
    --arg "$MCPS_DIR/raspa-mcp" \
    --arg raspa-mcp \
    --timeout 60 \
    --lazy \
    --description "RASPA2 molecular simulation: build input files, parse outputs, GCMC/MD workflows"

# mofstructure-mcp — MOF structural analysis
register "mofstructure" mofstructure \
    --command "$MOFSTRUCTURE_CMD" \
    --arg -m \
    --arg mofstructure.mcp_server \
    --timeout 120 \
    --lazy \
    --description "MOF structural analysis: identify building blocks, topology, metal nodes, linkers"

# mofchecker-mcp — MOF structure validation (Python 3.10 venv)
register "mofchecker" mofchecker \
    --command "$MOFCHECKER_CMD" \
    --arg -m \
    --arg mofchecker.mcp_server \
    --timeout 120 \
    --lazy \
    --description "MOF structure checker: validate CIF files, detect common defects, check geometry"

# pdftranslate-mcp — needs OPENAI_* credentials (not set here)
register "pdf2zh" pdf2zh \
    --command "$PDF2ZH_CMD" \
    --arg -m \
    --arg pdf2zh.mcp_server \
    --timeout 600 \
    --lazy \
    --description "PDF scientific paper translation (pdf2zh): translate full PDFs preserving LaTeX layout"

# feishu-mcp — needs FEISHU_APP_ID / FEISHU_APP_SECRET (not set here)
register "feishu" feishu \
    --command "$FEISHU_CMD" \
    --arg -m \
    --arg feishu_mcp.server \
    --timeout 30 \
    --description "Feishu/Lark: send messages, manage docs, create/assign tasks"

# miqrophi-mcp — epitaxial lattice matching, no credentials needed
register "miqrophi" miqrophi \
    --command "$MIQROPHI_CMD" \
    --arg -m \
    --arg miqrophi.mcp_server \
    --timeout 120 \
    --lazy \
    --description "Epitaxial lattice matching: CIF surface analysis, substrate screening, strain calculation"

# ──────────────────────────────────────────────────────────────────────────────
# Post-registration credential reminder
# ──────────────────────────────────────────────────────────────────────────────

echo ""
info "All MCP servers registered."
echo ""
echo -e "${YELLOW}⚠️  Credentials still required — edit ~/.featherflow/config.json:${NC}"
echo ""
echo "  pdf2zh  →  tools.mcpServers.pdf2zh.env:"
echo '               "OPENAI_BASE_URL": "https://api.openai.com/v1"'
echo '               "OPENAI_API_KEY":  "sk-..."'
echo '               "OPENAI_MODEL":    "gpt-4o"'
echo ""
echo "  feishu  →  tools.mcpServers.feishu.env:"
echo '               "FEISHU_APP_ID":     "cli_..."'
echo '               "FEISHU_APP_SECRET": "..."'
echo ""
echo "  For restricted feishu tool access, also add an allowedTools list."
echo "  See docs/MCP_SETUP.md for the recommended allowedTools subset."
echo ""
