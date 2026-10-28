SHELL := /bin/bash
RUN_SIM := docker compose run --rm --no-deps sim-api
RUN_TRAIN := docker compose --profile train run --rm trainer

.PHONY: build up down ps logs test test-all train-smoke grid demo demo-check dataset train tensorboard

build:
	docker compose --profile train build

up:
	docker compose up -d --build sim-api web

down:
	docker compose down

ps:
	docker compose ps

logs:
	docker compose logs -f --tail=100 sim-api web

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
	curl -fsS http://localhost:8080/health && echo
	curl -fsS -o /dev/null -w "web index: %{http_code}\n" http://localhost:8080/

ALPHA ?= 0
SEED ?= 0
STEPS ?= 3000000
ENVS ?= 4
EPISODE ?= 3600

dataset:
	$(RUN_SIM) python -m sim.demand --dataset

# long training in the background: make train ALPHA=0.3 SEED=1
train:
	docker compose --profile train run -d --name train_a$(ALPHA)_s$(SEED) \
		-e GIT_COMMIT=$$(git rev-parse --short HEAD) -e PYTHONWARNINGS=ignore trainer \
		python -m rl.train --alpha $(ALPHA) --seed $(SEED) --timesteps $(STEPS) \
		--n-envs $(ENVS) --episode-seconds $(EPISODE)
	@echo "logs: docker logs -f train_a$(ALPHA)_s$(SEED)  · curvas: make tensorboard"

tensorboard:
	docker compose --profile train up -d tensorboard
	@echo "http://localhost:6006"
