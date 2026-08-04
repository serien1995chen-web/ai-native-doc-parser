#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

docker compose config -q
docker compose build api-server
docker compose run --rm api-server pytest tests/ -q
docker compose run --rm api-server ruff check .
