#!/usr/bin/env bash
# Six sequential runs; frozen inputs; validation selection before optional final test.
set -euo pipefail
cd "$(dirname "$0")/.."
experiment_id=${1:-cooperation_$(date -u +%Y%m%d_%H%M%S)}
if [ "$#" -gt 1 ] || [[ ! "$experiment_id" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "Uso: bash scripts/run_experiment.sh [identificador_sin_espacios]" >&2
  exit 2
fi
export UID
export GID="$(id -g)"
container="experiment_$experiment_id"
if docker container inspect "$container" >/dev/null 2>&1; then
  if [ "$(docker inspect --format '{{.State.Running}}' "$container")" = true ]; then
    echo "Experimento ya activo: $container"
  else
    docker start "$container"
    echo "Continuando con la instantanea y modelos completados del experimento."
  fi
  exit 0
fi
experiment_dir="$PWD/outputs/evaluations/$experiment_id"
snapshot="$experiment_dir/source"
if [ -e "$snapshot" ]; then
  echo "La instantanea ya existe sin contenedor; usa otro identificador para no sobrescribirla." >&2
  exit 1
fi
mkdir -p "$snapshot"
tar --exclude='__pycache__' --exclude='*.pyc' -cf - \
  rl sim eval scenarios config pyproject.toml | tar -xf - -C "$snapshot"
git rev-parse HEAD > "$experiment_dir/git-revision.txt"
git status --porcelain > "$experiment_dir/git-status.txt"
docker image inspect gemelo-cali/trainer:dev --format '{{.Id}}' > "$experiment_dir/image-id.txt"
docker compose --profile train run -d --name "$container" \
  -e GIT_COMMIT="$(cat "$experiment_dir/git-revision.txt")" \
  -e GIT_DIRTY="$(wc -l < "$experiment_dir/git-status.txt" | tr -d ' ')" \
  -e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2 -e PYTHONWARNINGS=ignore \
  -v "$snapshot/rl:/app/rl:ro" -v "$snapshot/sim:/app/sim:ro" \
  -v "$snapshot/eval:/app/eval:ro" -v "$snapshot/scenarios:/app/scenarios:ro" \
  -v "$snapshot/config:/app/config:ro" -v "$snapshot/pyproject.toml:/app/pyproject.toml:ro" \
  trainer python -m rl.experiment --alphas 0 0.3 --seeds 0 1 2 \
  --timesteps 3000000 --n-envs 2 --scenarios peak valley event \
  --out "outputs/evaluations/$experiment_id" --final-test
printf 'EXPERIMENT_CONTAINER=%s\n' "$container"
printf 'Estado: %s/experiment.json\n' "$experiment_dir"
printf 'Logs: docker logs -f %s\n' "$container"
echo 'Mantener Windows encendido y WSL activo hasta terminar.'
