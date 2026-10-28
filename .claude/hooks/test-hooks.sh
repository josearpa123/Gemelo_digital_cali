#!/usr/bin/env bash
# Self-test for project hooks: each case states whether it must PASS (exit 0) or BLOCK (exit 2).
set -u
H="$(cd "$(dirname "$0")" && pwd)"
export CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$H/../.." && pwd)}"
fails=0
j() { python3 -c 'import json,sys; print(json.dumps(json.loads(sys.argv[1])))' "$1"; }
check() {  # expect hook json label
  local expect="$1" hook="$2" input="$3" label="$4" code
  out="$(printf '%s' "$input" | "$H/$hook" 2>&1)"; code=$?
  local got=PASS; [ $code -eq 2 ] && got=BLOCK; [ $code -ne 0 ] && [ $code -ne 2 ] && got="ERR($code)"
  if [ "$got" = "$expect" ]; then mark=ok; else mark=FALLO; fails=$((fails + 1)); fi
  printf '%-5s %-6s %-22s %s\n' "$mark" "$got" "$hook" "$label"
  [ "$got" = BLOCK ] && [ -n "$out" ] && printf '      └ %s\n' "$out"
}
bash_in() { python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","tool_input":{"command":sys.argv[1]}}))' "$1"; }
file_in() { python3 -c 'import json,sys; print(json.dumps({"tool_name":sys.argv[1],"tool_input":{"file_path":sys.argv[2]}}))' "$1" "$2"; }

echo "== PreToolUse(Bash) =="
check PASS  pre-bash-guard.sh "$(bash_in 'rm -rf build/ outputs/tmp')"        "rm -rf build/"
check PASS  pre-bash-guard.sh "$(bash_in 'docker compose ps')"                 "docker compose ps"
check PASS  pre-bash-guard.sh "$(bash_in 'docker system prune -f')"            "docker system prune -f (sin -a)"
check PASS  pre-bash-guard.sh "$(bash_in 'git push origin feat/h1-demo')"     "git push normal a rama"
check PASS  pre-bash-guard.sh "$(bash_in 'git push --force origin feat/h1-demo')" "push --force a rama feature"
check PASS  pre-bash-guard.sh "$(bash_in 'cp .env.example .env.example.bak')" "cp .env.example"
check PASS  pre-bash-guard.sh "$(bash_in 'python -c "import os; os.environ"')" "os.environ no es .env"
check BLOCK pre-bash-guard.sh "$(bash_in 'rm -rf /')"                          "rm -rf /"
check BLOCK pre-bash-guard.sh "$(bash_in 'cd x && sudo rm -fr /*')"            "sudo rm -fr /*"
check BLOCK pre-bash-guard.sh "$(bash_in 'rm -rf ~')"                          "rm -rf ~"
check BLOCK pre-bash-guard.sh "$(bash_in 'rm -r -f $HOME')"                    "rm -r -f \$HOME"
check BLOCK pre-bash-guard.sh "$(bash_in 'docker system prune -a')"            "docker system prune -a"
check BLOCK pre-bash-guard.sh "$(bash_in 'docker system prune --all --volumes')" "docker system prune --all"
check BLOCK pre-bash-guard.sh "$(bash_in 'git push --force origin main')"      "git push --force origin main"
check BLOCK pre-bash-guard.sh "$(bash_in 'git push -f origin HEAD:main')"      "git push -f origin HEAD:main"
check BLOCK pre-bash-guard.sh "$(bash_in 'git push origin +main')"             "git push origin +main"
check BLOCK pre-bash-guard.sh "$(bash_in 'cat .env')"                          "cat .env"
check BLOCK pre-bash-guard.sh "$(bash_in 'echo TOKEN=x >> .env')"              "echo >> .env"
check BLOCK pre-bash-guard.sh "$(bash_in 'grep KEY api/.env.local')"           "grep api/.env.local"

echo "== PreToolUse(Read|Edit|Write) =="
check PASS  pre-edit-guard.sh "$(file_in Write "$CLAUDE_PROJECT_DIR/sim/controllers.py")" "Write sim/controllers.py"
check PASS  pre-edit-guard.sh "$(file_in Read  "$CLAUDE_PROJECT_DIR/outputs/metrics.csv")" "Read outputs/ (leer sí)"
check PASS  pre-edit-guard.sh "$(file_in Edit  "$CLAUDE_PROJECT_DIR/.env.example")"        "Edit .env.example"
check BLOCK pre-edit-guard.sh "$(file_in Write "$CLAUDE_PROJECT_DIR/models/ppo.zip")"      "Write models/ppo.zip"
check BLOCK pre-edit-guard.sh "$(file_in Edit  "outputs/tripinfo.xml")"                   "Edit outputs/ (relativa)"
check BLOCK pre-edit-guard.sh "$(file_in Read  "$CLAUDE_PROJECT_DIR/.env")"                "Read .env"

echo "== PostToolUse(Edit|Write) =="
tmp="$CLAUDE_PROJECT_DIR/.claude/hooks/.selftest"; mkdir -p "$tmp"
printf 'import os,sys\nx=[1,2 ,3]\nprint( x )\n' > "$tmp/ok.py"
printf 'def f():\n    return undefined_name\n' > "$tmp/bad.py"
printf '<net version="1.20"><edge id="a"/></net>\n' > "$tmp/ok.net.xml"
printf '<routes><vehicle id="v0"></routes>\n' > "$tmp/bad.rou.xml"
check PASS  post-edit-check.sh "$(file_in Write "$tmp/ok.py")"      "ok.py (ruff arregla imports/formato)"
echo "      └ contenido tras ruff: $(tr '\n' '|' < "$tmp/ok.py")"
check BLOCK post-edit-check.sh "$(file_in Write "$tmp/bad.py")"     "bad.py (F821 nombre indefinido)"
check PASS  post-edit-check.sh "$(file_in Write "$tmp/ok.net.xml")" "ok.net.xml bien formado"
check BLOCK post-edit-check.sh "$(file_in Write "$tmp/bad.rou.xml")" "bad.rou.xml mal formado"
rm -r "$tmp"

echo "== SessionStart / Stop =="
printf '{}' | "$H/session-start.sh"
printf '{"stop_hook_active":false}' | "$H/stop-tests.sh"; echo "      (Stop exit $?)"

echo; [ $fails -eq 0 ] && echo "TODOS LOS CASOS OK" || echo "$fails CASOS FALLARON"
exit $fails
