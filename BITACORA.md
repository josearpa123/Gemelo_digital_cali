# Bitácora

Registro de qué se hizo y qué sigue. La entrada más reciente va primero. El hook de inicio de sesión de Claude Code muestra las últimas entradas; el de cierre pide registrar una si hubo commits.

Formato: `## <fecha> · <autor> · <rama>`, luego `HEAD`, **Hecho**, **Siguiente** y **Bloqueos**.

## 2026-10-31 · Thunderbolt (con Claude Code) · feat/h-traces

**Hecho**
- El caos con «Agentes RL» venía del agente, no del LLM. El modelo de este equipo es el de humo (2048 timesteps) y usa el `TrafficSignal` de sumo-rl, que salta entre verdes arbitrarios sin los despejes del programa.
- Nuevo `rl/cyclic_signal.py`: el agente decide **mantener o avanzar** sobre el ciclo del propio programa (como el max-pressure cíclico), con verde mínimo y máximo. Se usa en el entrenamiento (`rl/env.py`) y en vivo con los modelos cuyo `config.json` dice `"signal": "cyclic"`; los modelos viejos siguen con la lógica anterior.
- Tests `tests/integration/test_cyclic_signal.py`: con acciones aleatorias, cada semáforo solo muestra estados de su programa, avanza en orden y respeta el verde máximo. `make test`: 150 passed. `make train-smoke`: OK.
- Clave de Groq guardada desde el panel (`secrets/`, fuera de git). Llamada real: `openai/gpt-oss-120b`, 76 + 25 tokens, US$ 0 real (US$ 0,0000264 equivalente), límites de la cuenta: 1 000 peticiones/día y 8 000 tokens/min (cabeceras `x-ratelimit-*`).
- Push de `feat/h-traces` aprobado por el usuario.

**Siguiente**
- Mañana (usuario/Milton): entrenamiento largo con el semáforo cíclico, `make train ALPHA=0 SEED=0` (varias horas), y después `make evaluate` contra tiempo fijo y max-pressure. Hasta entonces, el modelo actual sigue siendo el viejo y causa caos: para mostrar el panel usar **Max-pressure**.
- Usuario: rotar la clave de Groq (se compartió en el chat).

**Bloqueos**
- Puerto 8000 ocupado en este equipo por otro proyecto: el panel se revisó en `:8001`.

## 2026-10-30 · Thunderbolt (con Claude Code) · feat/h-traces

HEAD `e540aea`

**Hecho**
- Hito H-TRAZAS implementado (plan en `PLAN.md`):
  - Trazas de simulación (por segundo simulado), decisiones RL por intersección, eventos con impacto a +120 s, asistente LLM y episodios de entrenamiento.
  - Almacenamiento en `outputs/traces.db` + `outputs/traces/events.jsonl`; API `/api/traces*` y `/api/faults/arm`; eventos por `/ws/state`.
- «Armar fallo» con 6 fallos de un solo uso y su respaldo: RL → tiempo fijo, último valor válido, reconexión con `saveState`/`loadState`, reintentos + fallback del LLM y acción rechazada.
- Asistente de IA (`api/llm/`):
  - Groq `openai/gpt-oss-120b` configurable por variables de entorno.
  - Lista blanca de acciones con Pydantic, timeout de 20 s, 2 reintentos exponenciales y fallback por reglas.
  - Costo real US$ 0 (plan free) y equivalente pago con las tarifas verificadas el 30 oct (`config/llm_pricing.yaml`).
  - La clave se puede poner desde el panel (`secrets/`, modo 600, nunca se devuelve).
- Panel servido por FastAPI en `:8000` (nginx `:8080` opcional), rediseñado como centro de mando: mapa nocturno, HUD, sección Trazas y asistente.
- README: guía desde cero (Win/macOS/Linux), `scripts/medir_arranque.{sh,ps1}` y sección «Prueba del compañero» (tiempo y problemas en blanco).
- Pruebas:
  - `make test`: 138 passed, 1 skipped (`live`).
  - e2e Playwright: 17/17 OK contra la app real (en `:8001`, porque el 8000 de este equipo lo usa otro proyecto); captura en `docs/img/panel_trazas.png`.
- **Costo del trazado: 8,35 % (> 5 %, no cumple)**: RTF 759 → 686 pasos/s, mediana de 7 pares, `outputs/bench/tracing.json`. La medición fue ruidosa por otros contenedores activos. Detalle y opciones en `PLAN.md`.

**Siguiente**
- Usuario: decidir cómo bajar el costo del trazado a ≤ 5 % (opciones a/b/c en `PLAN.md`) o medir en un equipo sin carga.
- Usuario: poner la clave de Groq (panel o archivo de entorno) y correr `make test-live` para confirmar modelo, tokens, costo y límites reales.
- Alexandra: correr `scripts/medir_arranque.ps1` en Windows y llenar tiempo y problemas en «Prueba del compañero».
- Claude: volver a pasar el hito por `test-reviewer` cuando se resuelva el costo del trazado.

**Revisión (actualización, misma sesión, HEAD `1ed410e` + docs)**
- `test-reviewer`: **NO APROBADO**. Ya corregido:
  - en un clon limpio, `sim-api` genera las rutas de demanda y la simulación arranca; probado en un clon nuevo en el puerto 8002, lista en 16 s con la imagen ya construida;
  - los fallos del LLM se ven aunque no haya clave;
  - `make test-live` apunta a Groq y no al servidor falso;
  - los tests ya no escriben en `outputs/`;
  - los 4xx no se reintentan;
  - la ingesta del entrenamiento resiste estados inválidos.
- `make test`: 147 passed, 1 skipped. e2e 17/17 (`outputs/e2e/result.json`).
- Sigue abierto: costo del trazado > 5 %. El reviewer midió 15,6 % con `tests/perf`; el último `make bench-tracing` dio 8,35 %.

**Bloqueos**
- En este equipo el puerto 8000 lo ocupa `oftalmologia-ia-backend-1`: `make up` falla hasta liberarlo.

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
- Portabilidad: `make doctor`, `tests/portability/`, `make clean-clone-check` y CI en GitHub (Linux uid 1001 + checkout Windows + ruff). CI verde en el PR #12: 65 passed, train-smoke y e2e 7/7.
- PPO 1M timesteps, 2 envs (`models/ppo_roosevelt4_a0_s0_20261029-1805`, `..._a0.3_s0_...`, ~54 min cada uno). Evaluación completa en `outputs/eval/summary.md` y `goal_check.md` (5 semillas × 1 h). Espera media en pico:
  - fijo 449,7 ± 25,7 s · max-pressure 484,0 ± 48,2 s · **RL α=0 658,4 ± 35,5 s (−46,9 %, IC95 [−56,2; −37,5])** · RL α=0,3 1.043,8 ± 65,6 s (−133,0 %).
  - Evento: RL α=0 −45,8 %, α=0,3 −141,5 %. Valle: RL α=0 −31,9 %, α=0,3 peor. **Ningún RL cumple el 15 %**; los dos empeoran frente a tiempo fijo y tienen más teletransportes (α=0: 218,6 en pico vs 10,4 con fijo).
  - `models/current` → α=0 (el menos malo). Ojo: se eligió con las mismas semillas de evaluación.
  - Hipótesis (sin verificar): el RL usa `TrafficSignal` de sumo-rl, que salta entre verdes arbitrarios igual que la primera versión de max-pressure, que bloqueaba los clusters unidos. Además 1M timesteps es poco.

**Siguiente**
- Milton: probar que el RL respete el orden/transiciones del programa (como max-pressure cíclico) o desunir los clusters en netconvert; reentrenar más de 1M. Si Jose tiene los modelos de 3M de anoche, evaluarlos con `make evaluate MODELS=...`.
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
