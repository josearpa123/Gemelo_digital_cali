#!/usr/bin/env bash
# Desktop entry point: keep this WSL client alive while the panel is in use.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$1" != "--check" ]; }; then
  echo "Uso: bash scripts/start_panel.sh [--check]" >&2
  exit 2
fi
printf 'Iniciando Gemelo digital de Cali...\n'
ready=0
for _ in {1..45}; do
  if docker info >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
if [ "$ready" != 1 ]; then
  echo "Docker no responde en WSL. Comprueba el servicio de Docker en Ubuntu." >&2
  exit 1
fi
export UID
export GID="$(id -g)"
docker compose up -d --no-deps sim-api
binding=$(docker compose port sim-api 8000)
port=${binding##*:}
if [[ ! "$port" =~ ^[0-9]+$ ]]; then
  echo "No se pudo determinar el puerto del panel." >&2
  exit 1
fi
powershell=$(command -v powershell.exe || true)
if [ -z "$powershell" ]; then
  powershell=/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe
fi
windows_script=$(wslpath -w "$PWD/scripts/open_panel.ps1")
options=()
if [ "${1:-}" = "--check" ]; then options=(-NoBrowser); fi
"$powershell" -NoProfile -ExecutionPolicy Bypass -File "$windows_script" \
  -Url "http://localhost:$port" "${options[@]}"
if [ "${1:-}" = "--check" ]; then exit 0; fi
printf '\nDeja esta ventana abierta mientras usas el panel.\n'
printf 'Ctrl+C cierra el seguimiento; no borra modelos ni resultados.\n\n'
exec docker compose logs --follow --tail 0 sim-api
