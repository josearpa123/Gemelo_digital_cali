---
name: train-agent
description: Lanza un entrenamiento MARL (PPO compartido o DQN) en el contenedor trainer con parámetros de red, α, timesteps y semilla, y guarda modelo, config y logs de TensorBoard. Úsala para cualquier entrenamiento, incluido el de humo.
---

# Entrenar agentes

## Parámetros
| Parámetro | Ejemplo | Nota |
|---|---|---|
| `NET` | `scenarios/<zona>/<zona>.net.xml` | red de Cali |
| `SCENARIO` | `peak` | demanda de entrenamiento |
| `ALPHA` | `0` o `0.3` | peso de la recompensa de vecinas |
| `STEPS` | `200000` | timesteps totales (suma de agentes) |
| `SEED` | `0` | semilla de SUMO, demanda y torch |
| `ALGO` | `ppo` | o `dqn` |

## Comandos
```bash
# humo (≈1 min, test slow): 1000 timesteps, verifica que el modelo carga
make train-smoke

# entrenamiento real en segundo plano
make train NET=... SCENARIO=peak ALPHA=0.3 STEPS=200000 SEED=0
#  = docker compose --profile train run -d --name train_<run_id> trainer \
#      python -m rl.train --net ... --scenario peak --alpha 0.3 --timesteps 200000 --seed 0

docker logs -f train_<run_id>          # progreso
docker compose up -d tensorboard       # http://localhost:6006
```

## Salidas (no editar a mano)
- `models/<run_id>/model.zip`, `models/<run_id>/config.json` (parámetros + commit git + duración real).
- `outputs/tb/<run_id>/` (recompensa media, espera media por episodio).
- `run_id = <algo>_<zona>_a<alpha>_s<seed>_<YYYYmmdd-HHMM>`.

## Al terminar
1. `python -m rl.evaluate --model models/<run_id>/model.zip --episodes 1` para un chequeo rápido.
2. Si sirve para la demo: `make promote RUN=<run_id>` crea `models/current -> <run_id>` (lo carga sim-api).
3. Reporta los números con la ruta del archivo de origen. Nada inventado.
