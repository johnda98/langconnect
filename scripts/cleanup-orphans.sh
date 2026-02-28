#!/usr/bin/env bash
set -euo pipefail

# Runs the LangConnect orphan embedding cleanup inside the API service container.
# Usage:
#   ./scripts/cleanup-orphans.sh        # deletes orphans
#   ./scripts/cleanup-orphans.sh --dry-run
#
# Requirements:
# - docker compose (uses docker-compose.yml in repo root)
# - API service reachable via compose service name "api"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE_ARGS=()
if [[ "${1:-}" == "--dry-run" ]]; then
  MODE_ARGS+=(--dry-run)
fi

echo "Running orphan cleanup in compose service 'api' …"
docker compose run --rm api python -m langconnect.maintenance.cleanup "${MODE_ARGS[@]}"
