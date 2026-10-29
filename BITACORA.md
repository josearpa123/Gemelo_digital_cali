# Bitácora

Registro de qué se hizo y qué sigue. La entrada más reciente va primero. El hook de inicio de sesión de Claude Code muestra las últimas entradas; el de cierre pide registrar una si hubo commits.

Formato: `## <fecha> · <autor> · <rama>`, luego `HEAD`, **Hecho**, **Siguiente** y **Bloqueos**.

## 2026-10-29 · Milton (con Claude Code) · feat/h1-milton-issues

HEAD `ed69113`

**Hecho**
- #2 Max-pressure (`sim/controllers/maxpressure.py`), registrado en el panel. Versión **cíclica** sobre el programa de SUMO: la versión que salta entre verdes arbitrarios bloqueaba los clusters unidos (pico s0–s1: 1.377–1.449 s de espera media vs 421–448 s con fijo, `outputs/eval_mp_check/`, corrida previa). Presión por carril de entrada (no por enlace) y normalizada por capacidad; verde mín. 10 s (o el programado si es menor), máx. 60 s, decisión cada 5 s. Tests unit (doble de TraCI) + smoke de 300 pasos + e2e (8/8 OK).
- #1 `tests/unit/test_demand.py` (rutas válidas, 30–40 % motos, semillas disjuntas, reproducible salvo la cabecera con fecha de duarouter) y escenario `event`: `scenarios/roosevelt4/roosevelt4.event.json` (cierre de carril 15:00–35:00), aplicado por `eval/run_all.py`. Bug corregido: el carril del accidente (`1007746271_2`) era la única conexión desde `-203502410#1` y SUMO abortaba con "no valid route"; `accident_candidate` ahora elige un carril que no rompe giros (`1007746271_1`). Afectaba también al botón del panel.
- #3 `tests/unit/test_rl.py` (tamaño de observación, recompensa calculada una vez por paso, α) y `tests/smoke/test_train_smoke.py`. `rl/train.py` guarda checkpoints cada 100k timesteps.
- #8 `eval/metrics.py` (Jain), `eval/run_all.py`, `make evaluate`. Corrida real fijo vs max-pressure, 3 escenarios × 5 semillas × 1 h (`outputs/eval/summary.md`, `goal_check.md`):
  - Pico: espera media fijo 449,7 ± 25,7 s · max-pressure 485,2 ± 50,5 s (−7,9 %, IC95 [−15,1; −0,7]). Jain 0,18 vs 0,24.
  - Evento: 448,6 ± 21,2 vs 489,9 ± 60,6 s (−9,2 %).
  - Valle: 230,0 ± 17,1 vs 174,2 ± 21,0 s (**+24,3 %**, IC95 [+18,9; +29,6]).
- #4 (parcial, sin netedit): pico s0 con fijo da 4 teletransportes, 2 por atasco y 2 por ceda el paso, ninguno por giro imposible. El programa fijo de netconvert del cluster de la Cra 34 tiene ciclo de **306 s** (9 grupos de 26 s); el de la Cra 39, verdes de 7 s. La línea base no es realista.
- `make test`: 40 passed, 1 skipped (RL sin modelo). `make train-smoke` OK.

**Siguiente**
- Milton: terminar PPO α=0 y α=0,3 (1M, relanzado con checkpoints) y correr `make evaluate MODELS=...` con valle/pico/evento. Si Jose tiene los modelos de 3M de anoche, evaluar esos.
- Milton (#4): revisar en netedit y fijar ciclos de tiempo fijo realistas antes de reentrenar.
- Milton y Jose: #9 ensayo de la demo y video.

**Bloqueos**
- En este equipo la VM de WSL se congela por falta de RAM en Windows (438 MB libres de 16 GB con un juego abierto): se perdieron 2 entrenamientos (sin checkpoints). Ahora guarda cada 100k.

## 2026-10-28 (cierre) · Jose (con Claude Code) · feat/h1-demo

HEAD `ver git log`

**Hecho**
- Panel (`sim-api`, `web`) apagado con `docker compose down`.
- Entrenamientos dejados corriendo hasta terminar solos (solo guardan el modelo al final): `train_a0_s0` en ~1,23M/3M y `train_a0.3_s0` en ~0,98M/3M timesteps al cierre. Al terminar quedan en `models/ppo_roosevelt4_a0_s0_*` y `models/ppo_roosevelt4_a0.3_s0_*`.

**Siguiente (mañana)**
- Comprobar que terminaron: `docker ps -a --filter name=train_` (estado `Exited (0)`) y `ls models/`. Si el equipo se apagó antes, relanzar: `make train ALPHA=0 SEED=0` y `make train ALPHA=0.3 SEED=0 ENVS=3`.
- Limpiar los contenedores terminados: `docker rm train_a0_s0 train_a0.3_s0`.
- Milton: #2 (max-pressure, prioridad), #8 (evaluación con los modelos nuevos), #3, #1, #4. Juntos: #9 ensayo de la demo.
- Levantar el panel: `make up` → http://localhost:8080.

**Bloqueos**
- Milton aún no es colaborador del repo.

## 2026-10-28 · Jose (con Claude Code) · feat/h1-demo

HEAD `ver git log`

**Hecho**
- Panel web de la demo: `sim/runner.py` (libsumo en un hilo dedicado, estrategias intercambiables, accidente, demanda pico/valle, métricas), `api/main.py` (`/api/network` GeoJSON, `/api/control`, `/ws/state`) y `web/` (Leaflet + Chart.js, semáforo por carril, ⚠️ del accidente, KPIs, 2 gráficas con una serie por corrida).
- Estrategia RL en vivo (`sim/controllers/rl_policy.py`) con la misma lógica de fases de sumo-rl; carga `models/current` o el modelo más reciente. `sim-api` usa ahora la imagen del trainer (torch + SB3).
- Tests: `make test` 11 passed (incluye WebSocket con 4 tls y vehículos, accidente cambia `allowed` del carril, selector). `make e2e` (Playwright en Docker): 7/7 OK (simulación avanza, vehículos se mueven, gráficas, accidente, RL activa, pausa, sin errores JS).
- Entrenamientos en curso: α = 0 en ~606k/3M timesteps, α = 0,3 en ~455k/3M (ep_rew_mean de −542 a −427 en α = 0; aún no es una métrica de evaluación).

**Siguiente**
- Claude/Jose: cuando terminen los entrenamientos, apuntar `models/current` al mejor modelo y comparar RL vs tiempo fijo en las semillas de evaluación 0–4 (pico) con números reales.
- Milton (issues actualizados el 28 oct): #2 max-pressure (**prioridad demo**), #8 evaluación preliminar RL vs fijo y elegir `models/current`, #3 tests de RL y revisión de curvas, #1 tests de demanda y escenario evento, #4 netedit, #9 ensayo de la demo (con Jose), #10 corredor completo (H2).
- Ensayo de la demo y video de respaldo (jueves).

**Bloqueos**
- Milton aún no es colaborador del repo.

## 2026-10-27 · Jose (con Claude Code) · feat/h1-demo

HEAD `2aafe37` (antes de este commit de docs)

**Hecho**
- H0 cerrado: workspace de Claude Code (CLAUDE.md, hooks probados, 4 subagentes, skills, comandos), Docker con SUMO 1.28 + Python 3.11, `sim-api` y `web` healthy, `make test` en verde.
- Red real `scenarios/roosevelt4`: Av. Roosevelt (OSM `Calle 6`) entre Cra 34 y Cra 39, **4 semáforos** (Cra 34, 36, 36A Bis, 39), georreferenciada, con andenes y 174 cruces peatonales.
- Dataset de demanda (`sim/demand.py`): 20 archivos de entrenamiento (pico, semillas 100–119) + 15 de evaluación (valle/pico/evento, semillas 0–4), 35 % motos. Pico ≈ 1.300 veh/h: 1 h con tiempo fijo da 4 teletransportes y ~200 vehículos en red (la primera versión con randomTrips colapsaba la malla residencial).
- Entorno MARL (`rl/`): observación con colas de vecinas, recompensa con α, PPO compartido con SuperSuit. Arreglos: PettingZoo 1.24.3 (sumo-rl 1.4.5 no soporta 1.25), procesos `spawn` (libsumo no es fork-safe).
- Entrenamientos lanzados en segundo plano: `train_a0_s0` (α = 0, 4 envs) y `train_a0.3_s0` (α = 0,3, 3 envs), 3M timesteps, ~1.100 fps cada uno.
- Issues #1–#4 para Milton en GitHub (milestone H1); README y hooks de bitácora.

**Siguiente**
- Claude/Jose: runner TraCI + FastAPI (`/ws/state`, `/api/control`) + mapa Leaflet con vehículos, semáforos, accidente, selector y 2 gráficas.
- Claude: cuando terminen los entrenamientos, comparar RL vs tiempo fijo en las semillas de evaluación y registrar los números reales.
- Milton (mañana): revisar #1 y #3 (ya hay una primera versión; calibrar demanda y revisar recompensa), hacer #2 (max-pressure) y #4 (netedit).

**Bloqueos**
- Milton aún no es colaborador del repo (falta su usuario de GitHub para asignarle los issues).
