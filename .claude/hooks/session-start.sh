#!/usr/bin/env bash
# SessionStart: what was done and what is next (BITACORA.md, PLAN.md, git, GitHub issues).
set -uo pipefail
source "$(dirname "$0")/_lib.sh"
HOOK_INPUT="$(cat)"
cd "$PROJECT_DIR" || exit 0

session="$(json_get .session_id)"
state_dir="$PROJECT_DIR/.claude/state"
mkdir -p "$state_dir"
head_now="$(git rev-parse HEAD 2>/dev/null || echo none)"
[ -n "$session" ] && printf '%s %s\n' "$head_now" "$(date +%s)" > "$state_dir/session-$session"

milestone="PLAN.md no existe todavía"
if [ -f PLAN.md ]; then
  milestone="$(grep -m1 -E '^\*\*Hito actual:\*\*' PLAN.md | sed -E 's/^\*\*Hito actual:\*\* *//')"
fi

echo "=== Contexto del proyecto (hook SessionStart) ==="
echo "Hito actual: $milestone"
echo "Rama: $(git branch --show-current 2>/dev/null) · usuario git: $(git config user.name 2>/dev/null)"

if [ -f BITACORA.md ]; then
  echo
  echo "--- Últimas entradas de BITACORA.md ---"
  # entries start with '## '; show the 3 most recent (newest first in the file)
  awk '/^## /{n++} n>=1 && n<=3' BITACORA.md | head -60
  last_hash="$(grep -m1 -oE 'HEAD `[0-9a-f]{7,}`' BITACORA.md | grep -oE '[0-9a-f]{7,}')"
  if [ -n "$last_hash" ] && git cat-file -e "$last_hash" 2>/dev/null; then
    new="$(git log --oneline "$last_hash"..HEAD 2>/dev/null | head -15)"
    [ -n "$new" ] && { echo; echo "--- Commits posteriores a la última entrada ---"; echo "$new"; }
  fi
fi

dirty="$(git status --short 2>/dev/null | head -10)"
[ -n "$dirty" ] && { echo; echo "--- Cambios sin commit ---"; echo "$dirty"; }

if command -v gh >/dev/null 2>&1; then
  issues="$(timeout 8 gh issue list --state open --limit 10 2>/dev/null)"
  [ -n "$issues" ] && { echo; echo "--- Issues abiertos en GitHub ---"; echo "$issues"; }
fi

if [ -f docker-compose.yml ]; then
  echo
  echo "--- docker compose ps ---"
  docker compose ps --format 'table {{.Service}}\t{{.State}}\t{{.Status}}' 2>&1 | head -8
fi
echo
echo "Al terminar trabajo con commits: agregar entrada en BITACORA.md (Hecho / Siguiente / Bloqueos)."
exit 0
