#!/usr/bin/env bash
# For a training container already started before automatic validation was implemented.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo "Uso: bash scripts/watch_training.sh CONTENEDOR models/RUN [--allow-legacy]" >&2
  exit 2
fi
container="$1"
model="$2"
extra=()
if [ "${3:-}" = "--allow-legacy" ]; then
  extra=(--allow-legacy)
elif [ "$#" -eq 3 ]; then
  echo "Tercer argumento inválido" >&2
  exit 2
fi
result=$(docker wait "$container")
if [ "$result" != 0 ]; then
  echo "El entrenamiento terminó con código $result; no se evalúa un modelo incompleto." >&2
  exit 1
fi
export UID
export GID="$(id -g)"
run="$(basename "$model")"
docker compose --profile train run --rm -e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2 trainer \
  python -m eval.run_all --models "$model" --split validation \
  --scenarios valley peak event --workers 2 \
  --out "outputs/evaluations/$run/validation_$(date -u +%Y%m%d-%H%M%S)" "${extra[@]}"
