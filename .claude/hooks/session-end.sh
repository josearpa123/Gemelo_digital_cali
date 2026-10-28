#!/usr/bin/env bash
# SessionEnd: fallback logbook entry with this session's commits when nobody wrote one.
set -uo pipefail
source "$(dirname "$0")/_lib.sh"
HOOK_INPUT="$(cat)"
cd "$PROJECT_DIR" || exit 0
session="$(json_get .session_id)"
state="$PROJECT_DIR/.claude/state/session-$session"
[ -z "$session" ] || [ ! -f "$state" ] && exit 0
read -r start_head start_ts _ < "$state"
rm -f "$state"

commits="$(git log --format='- `%h` %s' "$start_head"..HEAD 2>/dev/null)"
[ -z "$commits" ] && exit 0
log_ts="$(stat -c %Y BITACORA.md 2>/dev/null || echo 0)"
[ "$log_ts" -ge "$start_ts" ] && exit 0

entry="## $(date '+%Y-%m-%d %H:%M') · $(git config user.name) · $(git branch --show-current) (automática)

HEAD \`$(git rev-parse --short HEAD)\`

**Hecho** (commits de la sesión, sin resumen manual):
$commits

**Siguiente:** ver PLAN.md e issues abiertos.
"
python3 - "$entry" <<'PY'
import sys
from pathlib import Path
path = Path("BITACORA.md")
text = path.read_text() if path.exists() else "# Bitácora\n"
head, sep, rest = text.partition("\n## ")
new = head.rstrip() + "\n\n" + sys.argv[1].rstrip() + "\n" + (("\n## " + rest) if sep else "")
path.write_text(new)
PY
exit 0
