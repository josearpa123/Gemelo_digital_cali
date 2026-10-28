---
name: evaluate-strategies
description: Corre la evaluación completa del proyecto (3 estrategias × 3 escenarios × 5 semillas) y produce tablas CSV/Markdown y figuras con tiempo de viaje, espera, colas e índice de Jain; verifica el objetivo de ≥15 % menos espera del RL frente a tiempo fijo en hora pico.
---

# Evaluar estrategias

```bash
make evaluate MODEL=models/current SEEDS="0 1 2 3 4"
# = docker compose --profile train run --rm trainer python -m eval.run_all --model ... --seeds 0 1 2 3 4
```

## Matriz
- Estrategias: `fixed`, `maxpressure` (y `actuated` de SUMO si aplica), `rl`.
- Escenarios: `valley`, `peak`, `event`. Semillas: 0–4 (mismas rutas para todas las estrategias en cada semilla).
- Episodio de 3600 s; peatones activos en evaluación.

## Métricas (por corrida, desde `tripinfo.xml` y muestreo TraCI)
- Tiempo de viaje medio (`duration`), espera media (`waitingTime`), cola media y máxima por carril entrante, índice de Jain sobre la espera media por aproximación: J = (Σx)² / (n·Σx²).

## Salidas
- `outputs/eval/runs.csv` (una fila por corrida), `outputs/eval/summary.csv` y `summary.md` (media ± desviación por estrategia × escenario).
- `outputs/eval/fig_*.png` (barras con error, boxplots por semilla).
- `outputs/eval/goal_check.md`: reducción de espera RL vs fijo en pico = (fijo − rl)/fijo, con media, IC 95 % por bootstrap y CUMPLE / NO CUMPLE frente a 15 %.

## Reglas
Si no se cumple el 15 %, se reporta tal cual con los números reales. Nunca se ajustan semillas ni se descartan corridas para mejorar el resultado.
