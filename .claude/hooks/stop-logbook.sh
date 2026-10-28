#!/usr/bin/env bash
# Stop: if this session made commits but BITACORA.md was not updated, ask once for an entry.
set -uo pipefail
source "$(dirname "$0")/_lib.sh"
HOOK_INPUT="$(cat)"
[ "$(json_get .stop_hook_active)" = "true" ] && exit 0
cd "$PROJECT_DIR" || exit 0
session="$(json_get .session_id)"
state="$PROJECT_DIR/.claude/state/session-$session"
[ -z "$session" ] || [ ! -f "$state" ] && exit 0
read -r start_head start_ts asked < "$state"
[ "${asked:-}" = "asked" ] && exit 0

commits="$(git log --oneline "$start_head"..HEAD 2>/dev/null | wc -l)"
[ "$commits" -eq 0 ] && exit 0
log_ts="$(stat -c %Y BITACORA.md 2>/dev/null || echo 0)"
[ "$log_ts" -ge "$start_ts" ] && exit 0

printf '%s %s asked\n' "$start_head" "$start_ts" > "$state"
reason="Hubo $commits commit(s) en esta sesión y BITACORA.md no se actualizó. Agrega al inicio (debajo del título) una entrada '## <fecha> · <autor> · <rama>' con: HEAD \`<hash corto>\`, **Hecho** (viñetas con resultados reales), **Siguiente** (pasos concretos y responsable), **Bloqueos**. Luego haz commit de BITACORA.md."
if command -v jq >/dev/null 2>&1; then
  jq -n --arg r "$reason" '{decision: "block", reason: $r}'
else
  python3 -c 'import json,sys; print(json.dumps({"decision": "block", "reason": sys.argv[1]}))' "$reason"
fi
exit 0
