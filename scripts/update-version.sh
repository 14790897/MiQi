#!/usr/bin/env bash
# update-version.sh — Called by semantic-release to sync version across all manifests.
# Usage: ./scripts/update-version.sh <new-version>
#
# Updates:
#   - package.json (root)
#   - pyproject.toml
#   - apps/desktop/package.json

set -euo pipefail

VERSION="${1:?Usage: update-version.sh <version>}"

echo "📦 Updating all manifests to version: ${VERSION}"

# 1. Root package.json
sed -i "s/\"version\": \".*\"/\"version\": \"${VERSION}\"/" package.json
echo "  ✓ package.json → ${VERSION}"

# 2. pyproject.toml (Python uses PEP 440; semantic versions are compatible)
sed -i "s/^version = \".*\"/version = \"${VERSION}\"/" pyproject.toml
echo "  ✓ pyproject.toml → ${VERSION}"

# 3. apps/desktop/package.json
sed -i "s/\"version\": \".*\"/\"version\": \"${VERSION}\"/" apps/desktop/package.json
echo "  ✓ apps/desktop/package.json → ${VERSION}"

echo "✅ All versions updated to ${VERSION}"
