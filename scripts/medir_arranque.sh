#!/usr/bin/env bash
# Measures the time from `docker compose up -d --build` until the panel answers on
# http://localhost:8000 (the "Prueba del compañero" in the README). Linux / macOS / WSL.
# Usage: bash scripts/medir_arranque.sh [url] [max_minutes]
set -euo pipefail
URL="${1:-http://localhost:8000}"
MAX_MIN="${2:-30}"
cd "$(dirname "$0")/.."
export UID GID="$(id -g)"

start=$(date +%s)
echo "[$(date '+%H:%M:%S')] docker compose up -d --build sim-api"
docker compose up -d --build sim-api
echo "[$(date '+%H:%M:%S')] esperando a $URL ..."
# the panel counts as "up" when the page loads and the simulation answers (not just /health)
until curl -fsS -o /dev/null "$URL/" 2>/dev/null && curl -fsS -o /dev/null "$URL/api/strategies" 2>/dev/null; do
  if (( $(date +%s) - start > MAX_MIN * 60 )); then
    echo "No respondió en $MAX_MIN minutos. Revisa: docker compose logs sim-api" >&2
    exit 1
  fi
  sleep 2
done
elapsed=$(( $(date +%s) - start ))
printf "La app respondió en %s tras %d s = %d min %02d s (%.1f minutos)\n" \
  "$URL" "$elapsed" $((elapsed / 60)) $((elapsed % 60)) "$(echo "$elapsed / 60" | bc -l)"
