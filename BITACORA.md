# Bitácora

Registro de qué se hizo y qué sigue. La entrada más reciente va primero. El hook de inicio de sesión de Claude Code muestra las últimas entradas; el de cierre pide registrar una si hubo commits.

Formato: `## <fecha> · <autor> · <rama>`, luego `HEAD`, **Hecho**, **Siguiente** y **Bloqueos**.

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
