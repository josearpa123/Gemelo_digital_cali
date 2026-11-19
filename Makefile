SHELL := /bin/bash
# containers run as the host user (docker-compose.yml: ${UID}:${GID}); bash does not export
# UID, so without this every machine whose uid is not 1000 gets permission errors
export UID := $(shell id -u)
export GID := $(shell id -g)
RUN_SIM := docker compose run --rm --no-deps sim-api
RUN_TRAIN := docker compose --profile train run --rm trainer

# real LLM call with the key of the env file (manual, costs nothing on the free plan)
test-live:
	$(RUN_SIM) pytest -q -m live --run-live tests/live

# tracing overhead on the simulation (≤ 5 %), result in outputs/bench/tracing.json
bench-tracing:
	$(RUN_TRAIN) python -m eval.bench_tracing

.PHONY: test-live bench-tracing build up down ps logs test test-all train-smoke grid demo demo-check dataset train tensorboard e2e evaluate doctor test-portability clean-clone-check

# host preflight for a new machine (tools, memory, ports, permissions, stale image)
doctor:
	@bash scripts/doctor.sh

# portability checks inside the container (versions, permissions, reproducible dataset)
test-portability:
	$(RUN_SIM) pytest -q tests/portability

# fresh clone of HEAD in a temp dir: doctor + build + dataset + full test suite
clean-clone-check:
	bash scripts/clean_clone_check.sh

build:
	docker compose --profile train build

up:
	docker compose up -d --build sim-api
	@echo "panel: http://localhost:8000"

down:
	docker compose down

ps:
	docker compose ps

logs:
	docker compose logs -f --tail=100 sim-api

test:
	$(RUN_SIM) pytest -m "not slow" -q

test-all:
	$(RUN_TRAIN) pytest -q

train-smoke:
	$(RUN_TRAIN) pytest -m slow -q tests/smoke

grid:
	$(RUN_SIM) python -m sim.network.grid --out scenarios/grid2x2

demo: up demo-check

demo-check:
	docker compose ps
	curl -fsS http://localhost:8000/health && echo
	curl -fsS -o /dev/null -w "web index: %{http_code}\n" http://localhost:8000/
	curl -fsS http://localhost:8000/api/traces/summary && echo

ALPHA ?= 0
SEED ?= 0
STEPS ?= 3000000
ENVS ?= 2
EPISODE ?= 3600
TRAIN_SCENARIOS ?= peak
RUN_STAMP := $(shell date -u +%Y%m%d_%H%M%S)
RUN_NAME ?= train_a$(ALPHA)_s$(SEED)_$(RUN_STAMP)
RESUME ?=

dataset:
	$(RUN_SIM) python -m sim.demand --dataset --missing-only

# long training in the background: make train ALPHA=0.3 SEED=1
train:
	docker compose --profile train run -d --name $(RUN_NAME) \
		-e GIT_COMMIT=$$(git rev-parse --short HEAD) -e PYTHONWARNINGS=ignore \
		-e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2 trainer \
		python -m rl.train --alpha $(ALPHA) --seed $(SEED) --timesteps $(STEPS) \
		--n-envs $(ENVS) --episode-seconds $(EPISODE) --scenarios $(TRAIN_SCENARIOS) \
		$(if $(RESUME),--resume $(RESUME))
	@echo "logs: docker logs -f $(RUN_NAME)  · curvas: make tensorboard"

# strategies x scenarios x evaluation seeds: make evaluate MODELS="models/ppo_a models/ppo_b"
MODELS ?=
SCENARIOS ?= valley peak event
SPLIT ?= validation
SEEDS ?=
EVAL_ARGS ?=
evaluate:
	$(RUN_TRAIN) python -m eval.run_all --scenarios $(SCENARIOS) --split $(SPLIT) \
		$(if $(SEEDS),--seeds $(SEEDS)) $(foreach m,$(MODELS),--models $(m)) $(EVAL_ARGS)

tensorboard:
	docker compose --profile train up -d tensorboard
	@echo "http://localhost:6006"

PLAYWRIGHT_IMAGE := mcr.microsoft.com/playwright/python:v1.55.0-noble

e2e:
	docker run --rm --network host -u "$$(id -u):$$(id -g)" -e HOME=/tmp -v "$$PWD:/app" -w /app \
		$(PLAYWRIGHT_IMAGE) sh -c "pip install -q --user playwright==1.55.0 && python tests/e2e/panel_e2e.py http://localhost:8000"
