#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Run: cp .env.example .env" >&2
  exit 1
fi

docker compose config -q
docker compose build api-server
docker compose run --rm --no-deps api-server pytest tests/ -q
docker compose run --rm --no-deps api-server ruff check .
