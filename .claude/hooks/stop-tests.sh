#!/usr/bin/env bash
# Stop: fast test suite inside the container. Warns, never blocks.
set -uo pipefail
source "$(dirname "$0")/_lib.sh"
HOOK_INPUT="$(cat)"
[ "$(json_get .stop_hook_active)" = "true" ] && exit 0
cd "$PROJECT_DIR" || exit 0

if [ ! -f docker-compose.yml ] || [ ! -d tests ]; then
  json_msg "pytest (Stop): omitido, aún no existen docker-compose.yml o tests/."
  exit 0
fi
if ! docker compose config --services 2>/dev/null | grep -qx sim-api; then
  json_msg "pytest (Stop): omitido, el servicio sim-api no está definido."
  exit 0
fi

out="$(timeout 170 docker compose run --rm --no-deps -T sim-api pytest -m "not slow" -q -p no:cacheprovider 2>&1)"
code=$?
summary="$(printf '%s\n' "$out" | grep -E '(passed|failed|error|no tests ran)' | tail -1)"
[ -z "$summary" ] && summary="$(printf '%s\n' "$out" | tail -3 | tr '\n' ' ')"
if [ $code -eq 0 ]; then
  json_msg "pytest rápido OK: $summary"
else
  json_msg "AVISO pytest rápido falló (código $code): $summary"
fi
exit 0
