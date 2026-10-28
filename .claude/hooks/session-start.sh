#!/usr/bin/env bash
# SessionStart: current milestone from PLAN.md + docker compose ps.
set -uo pipefail
source "$(dirname "$0")/_lib.sh"
cd "$PROJECT_DIR" || exit 0

milestone="PLAN.md no existe todavía"
if [ -f PLAN.md ]; then
  milestone="$(grep -m1 -E '^\*\*Hito actual:\*\*' PLAN.md | sed -E 's/^\*\*Hito actual:\*\* *//')"
  [ -z "$milestone" ] && milestone="(PLAN.md sin línea '**Hito actual:**')"
fi

if [ -f docker-compose.yml ]; then
  ps="$(docker compose ps --format 'table {{.Service}}\t{{.State}}\t{{.Status}}' 2>&1 | head -10)"
  [ -z "$ps" ] && ps="(sin contenedores en marcha)"
else
  ps="(docker-compose.yml aún no existe)"
fi

echo "Hito actual: $milestone"
echo "docker compose ps:"
echo "$ps"
exit 0
