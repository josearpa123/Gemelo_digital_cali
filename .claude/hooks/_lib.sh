#!/usr/bin/env bash
# Shared helpers for project hooks. Sourced, not executed.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

# json_get <jq-path>  (reads hook JSON from $HOOK_INPUT)
# Uses jq; falls back to python3 only if jq is missing so hooks never fail open silently.
json_get() {
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$HOOK_INPUT" | jq -r "$1 // empty"
  else
    printf '%s' "$HOOK_INPUT" | python3 -c '
import json, sys
data = json.load(sys.stdin)
for key in sys.argv[1].lstrip(".").split("."):
    data = data.get(key) if isinstance(data, dict) else None
print("" if data is None else data)' "$1"
  fi
}

# json_msg <text>  -> {"systemMessage": text}
json_msg() {
  if command -v jq >/dev/null 2>&1; then
    jq -n --arg m "$1" '{systemMessage: $m}'
  else
    python3 -c 'import json,sys; print(json.dumps({"systemMessage": sys.argv[1]}))' "$1"
  fi
}

block() {
  echo "BLOQUEADO por hook del proyecto: $1" >&2
  exit 2
}
