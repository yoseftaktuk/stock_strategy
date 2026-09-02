#!/usr/bin/env bash
# Local development helper — always uses the project virtualenv.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d ".venv" ]]; then
  echo "Creating virtualenv..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

pip install -q -r requirements.txt -e .

export POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
export POSTGRES_PORT="${POSTGRES_PORT:-5433}"
export POSTGRES_DB="${POSTGRES_DB:-momentum_trader}"
export POSTGRES_USER="${POSTGRES_USER:-momentum}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-change_me}"
export POSTGRES_TEST_DB="${POSTGRES_TEST_DB:-momentum_trader_test}"

case "${1:-help}" in
  postgres)
    docker compose up postgres -d
    ;;
  migrate)
    alembic upgrade head
    ;;
  test-unit)
    pytest -m unit -v
    ;;
  test-integration)
    docker compose up postgres -d
    pytest -m integration -v
    ;;
  test)
    pytest -m unit -v
    docker compose up postgres -d
    pytest -m integration -v
    ;;
  help|*)
    echo "Usage: scripts/dev.sh [postgres|migrate|test-unit|test-integration|test]"
    echo ""
    echo "Always activates .venv and sets POSTGRES_PORT=${POSTGRES_PORT} by default."
    echo "Copy .env.example to .env to override settings."
    ;;
esac
