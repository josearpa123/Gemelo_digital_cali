#!/usr/bin/env bash
# PreToolUse(Read|Edit|Write): models/ and outputs/ are generated artifacts; .env holds secrets.
set -uo pipefail
source "$(dirname "$0")/_lib.sh"
HOOK_INPUT="$(cat)"
tool="$(json_get .tool_name)"
path="$(json_get .tool_input.file_path)"
[ -z "$path" ] && exit 0

case "$path" in /*) abs="$path" ;; *) abs="$PROJECT_DIR/$path" ;; esac
rel="${abs#"$PROJECT_DIR"/}"
base="$(basename "$abs")"

if [[ "$base" =~ ^\.env(\..+)?$ ]] && [[ ! "$base" =~ ^\.env\.(example|sample|template)$ ]]; then
  block "$tool sobre $rel: los .env con secretos no se leen ni se editan."
fi

if [ "$tool" != "Read" ] && [[ "$rel" =~ ^(models|outputs)/ ]]; then
  block "$rel es un artefacto generado; se produce con make train/evaluate, no a mano."
fi
exit 0
