#!/usr/bin/env bash
# PreToolUse(Bash): block destructive commands and any access to .env secrets.
set -uo pipefail
source "$(dirname "$0")/_lib.sh"
HOOK_INPUT="$(cat)"
cmd="$(json_get .tool_input.command)"
[ -z "$cmd" ] && exit 0

# Split into simple commands on ; & | and newlines, then inspect words.
while IFS= read -r segment; do
  read -ra w <<<"$segment"
  [ ${#w[@]} -eq 0 ] && continue
  # skip leading sudo/env/command wrappers
  i=0
  while [ $i -lt ${#w[@]} ] && [[ "${w[$i]}" =~ ^(sudo|command|env|nice|time|xargs)$ ]]; do i=$((i + 1)); done
  prog="${w[$i]:-}"

  if [ "$prog" = "rm" ]; then
    recursive=0; danger=0
    for word in "${w[@]:$((i + 1))}"; do
      [[ "$word" =~ ^-[a-zA-Z]*[rR] || "$word" == "--recursive" ]] && recursive=1
      [[ "$word" == "--no-preserve-root" ]] && danger=1
      word="${word%\"}"; word="${word#\"}"; word="${word%\'}"; word="${word#\'}"
      [[ "$word" =~ ^(/|/\*|/\.|~|~/|~/\*|\$HOME|\$HOME/|\$HOME/\*|\$\{HOME\}|\$\{HOME\}/|\$\{HOME\}/\*|$HOME|$HOME/|$HOME/\*)$ ]] && danger=1
    done
    [ $recursive = 1 ] && [ $danger = 1 ] && block "rm recursivo sobre / o ~ no está permitido."
  fi

  if [ "$prog" = "docker" ] && [[ " ${w[*]} " =~ \ system\ +prune\  ]]; then
    for word in "${w[@]}"; do
      [[ "$word" == "--all" || "$word" =~ ^-[a-zA-Z]*a[a-zA-Z]*$ ]] && block "docker system prune -a borra imágenes de otros proyectos."
    done
  fi

  if [ "$prog" = "git" ] && [[ " ${w[*]} " == *" push "* ]]; then
    forced=0; refs=()
    after_push=0
    for word in "${w[@]}"; do
      if [ $after_push = 0 ]; then [ "$word" = "push" ] && after_push=1; continue; fi
      case "$word" in
        --force|--force-with-lease|--force-with-lease=*|--force-if-includes) forced=1 ;;
        --*) ;;
        -*) [[ "$word" =~ f ]] && forced=1 ;;
        +*) forced=1; refs+=("${word#+}") ;;
        *) refs+=("$word") ;;
      esac
    done
    if [ $forced = 1 ]; then
      for r in "${refs[@]:1}"; do
        [[ "${r##*:}" =~ ^(refs/heads/)?(main|master)$ ]] && block "git push forzado a main está prohibido."
      done
      if [ ${#refs[@]} -le 1 ]; then
        branch="$(git -C "$PROJECT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
        [[ "$branch" =~ ^(main|master)$ ]] && block "git push forzado estando en la rama $branch está prohibido."
      fi
    fi
  fi
done < <(printf '%s\n' "$cmd" | sed -E 's/(&&|\|\||[;&|])/\n/g')

# .env / .env.<algo> (excepto .env.example|sample|template), lectura o escritura
while IFS= read -r tok; do
  [[ "$tok" =~ \.env\.(example|sample|template)$ ]] && continue
  block "acceso a archivos .env con secretos no permitido (usa .env.example)."
done < <(printf '%s' "$cmd" | grep -oE '(^|[^A-Za-z0-9_-])\.env(\.[A-Za-z0-9_]+)?([^A-Za-z0-9_.-]|$)' | grep -oE '\.env(\.[A-Za-z0-9_]+)?')

exit 0
