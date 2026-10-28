#!/usr/bin/env bash
# PostToolUse(Edit|Write): ruff on .py files; XML well-formedness on SUMO files.
set -uo pipefail
source "$(dirname "$0")/_lib.sh"
HOOK_INPUT="$(cat)"
path="$(json_get .tool_input.file_path)"
[ -z "$path" ] || [ ! -f "$path" ] && exit 0

RUFF_IMAGE="ghcr.io/astral-sh/ruff:0.14.0-alpine"

run_ruff() {
  if command -v ruff >/dev/null 2>&1; then
    (cd "$PROJECT_DIR" && ruff "$@")
  elif command -v docker >/dev/null 2>&1; then
    docker run --rm -u "$(id -u):$(id -g)" -v "$PROJECT_DIR:/src" -w /src "$RUFF_IMAGE" ruff "$@"
  else
    echo "ruff no disponible (ni host ni docker)" >&2; return 0
  fi
}

case "$path" in
  *.py)
    rel="${path#"$PROJECT_DIR"/}"
    run_ruff format "$rel" >/dev/null 2>&1
    if ! out="$(run_ruff check --fix "$rel" 2>&1)"; then
      echo "ruff check encontró problemas en $rel:" >&2
      echo "$out" >&2
      exit 2   # PostToolUse: stderr llega a Claude para que lo corrija
    fi
    ;;
  *.net.xml|*.rou.xml|*.sumocfg|*.add.xml|*.poly.xml|*.trips.xml)
    if ! out="$(python3 -c '
import sys, xml.etree.ElementTree as ET
try:
    ET.parse(sys.argv[1])
except ET.ParseError as e:
    sys.exit(str(e))' "$path" 2>&1)"; then
      echo "XML mal formado en $path: $out" >&2
      exit 2
    fi
    ;;
esac
exit 0
