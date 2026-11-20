#!/usr/bin/env bash
# Six sequential runs; frozen inputs; validation selection before optional final test.
set -euo pipefail
cd "$(dirname "$0")/.."
experiment_id=${1:-cooperation_$(date -u +%Y%m%d_%H%M%S)}
if [ "$#" -gt 2 ] || [[ ! "$experiment_id" =~ ^[A-Za-z0-9_-]+$ ]] \
  || { [ "$#" -eq 2 ] && [ "$2" != "--reuse-snapshot" ]; }; then
  echo "Uso: bash scripts/run_experiment.sh [identificador] [--reuse-snapshot]" >&2
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
  if [ "${2:-}" != "--reuse-snapshot" ]; then
    echo "La instantanea ya existe sin contenedor; usa --reuse-snapshot para conservarla." >&2
    exit 1
  fi
  test -f "$experiment_dir/git-revision.txt"
  test -f "$experiment_dir/git-status.txt"
  test -f "$experiment_dir/image-id.txt"
else
  if [ "${2:-}" = "--reuse-snapshot" ]; then
    echo "No existe una instantanea para reutilizar." >&2
    exit 1
  fi
  mkdir -p "$snapshot"
  tar --exclude='__pycache__' --exclude='*.pyc' -cf - \
    rl sim eval scenarios config pyproject.toml | tar -xf - -C "$snapshot"
  git rev-parse HEAD > "$experiment_dir/git-revision.txt"
  git status --porcelain > "$experiment_dir/git-status.txt"
  docker image inspect gemelo-cali/trainer:dev --format '{{.Id}}' > "$experiment_dir/image-id.txt"
fi
docker run -d --name "$container" --init --user "$(id -u):$(id -g)" --workdir /app \
  --cap-drop ALL --security-opt no-new-privileges \
  -e GIT_COMMIT="$(cat "$experiment_dir/git-revision.txt")" \
  -e GIT_DIRTY="$(wc -l < "$experiment_dir/git-status.txt" | tr -d ' ')" \
  -e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2 -e PYTHONWARNINGS=ignore \
  --mount "type=bind,src=$snapshot/rl,dst=/app/rl,readonly" \
  --mount "type=bind,src=$snapshot/sim,dst=/app/sim,readonly" \
  --mount "type=bind,src=$snapshot/eval,dst=/app/eval,readonly" \
  --mount "type=bind,src=$snapshot/scenarios,dst=/app/scenarios,readonly" \
  --mount "type=bind,src=$snapshot/config,dst=/app/config,readonly" \
  --mount "type=bind,src=$snapshot/pyproject.toml,dst=/app/pyproject.toml,readonly" \
  --mount "type=bind,src=$PWD/models,dst=/app/models" \
  --mount "type=bind,src=$PWD/outputs,dst=/app/outputs" \
  "$(cat "$experiment_dir/image-id.txt")" python -m rl.experiment --alphas 0 0.3 --seeds 0 1 2 \
  --timesteps 3000000 --n-envs 2 --scenarios peak valley event \
  --out "outputs/evaluations/$experiment_id" --final-test
printf 'EXPERIMENT_CONTAINER=%s\n' "$container"
printf 'Estado: %s/experiment.json\n' "$experiment_dir"
printf 'Logs: docker logs -f %s\n' "$container"
echo 'Mantener Windows encendido y WSL activo hasta terminar.'
