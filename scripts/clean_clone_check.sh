#!/usr/bin/env bash
# Simulates a new machine: clones the committed HEAD into a temp dir (no models, no outputs,
# no dataset, no local changes) and runs doctor, build, dataset and the whole test suite there.
#   make clean-clone-check            KEEP=1 to keep the temp clone
set -euo pipefail
src="$(cd "$(dirname "$0")/.." && pwd)"
dir="$(mktemp -d /tmp/gemelo-clean-XXXXXX)"
cleanup() { [ "${KEEP:-0}" = 1 ] && echo "clon en $dir" || rm -rf "$dir"; }
trap cleanup EXIT

step() { printf '\n=== %s\n' "$1"; }
step "clon limpio de HEAD ($(git -C "$src" rev-parse --short HEAD)) en $dir"
git clone -q --no-hardlinks "$src" "$dir"
cd "$dir"
# separate compose project: never touches the running panel or trainings
export COMPOSE_PROJECT_NAME=gemelo-cali-cleancheck

step "doctor"
bash scripts/doctor.sh || { echo "doctor reportó fallos"; exit 1; }
step "build"
make build
step "dataset (debe reproducir manifest.csv)"
make dataset
git diff --exit-code -- scenarios/roosevelt4/demand/manifest.csv
step "tests rápidos + portabilidad"
make test
step "tests lentos (entrenamiento corto)"
make train-smoke
step "sin cambios en archivos versionados tras correr todo"
git status --porcelain --untracked-files=no | { ! grep .; }
echo
echo "clean-clone-check: OK"
