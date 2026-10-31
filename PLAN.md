# PLAN · Gemelo digital de movilidad urbana · Cali

**Hito actual:** H-TRAZAS · trazas, asistente de IA y panel en :8000: implementado (30 oct), pendiente revisión del usuario; trazado cuesta 8,35 % (> 5 %)

| Hito | Fecha | Estado |
|---|---|---|
| H0 Workspace + Docker + hooks | 27 oct | ✅ terminado (hooks 29/29, compose healthy, `make test` OK) |
| H1 Demo | **29 oct** | en curso: red `roosevelt4` ✅ |
| H-TRAZAS Trazas del sistema + asistente de IA + prueba del compañero | 30 oct – 3 nov | 🔄 implementado; `make test` 138 OK, e2e 17/17; **falta**: costo ≤ 5 % (medido 8,35 %), prueba `live` con clave, medición del compañero |
| H2 Corredor completo | 2 nov | pendiente |
| H3 MARL coordinado | 9 nov | pendiente |
| H4 Evaluación y cierre | 16 nov (entrega 17 nov) | pendiente |

---

## 1. Arquitectura

```
                         ┌──────────────── docker compose ────────────────┐
 scenarios/ (vol) ──────►│ sim-api :8000                                  │
  .net.xml (Cali, OSM,   │  SUMO 1.28 ◄─TraCI─► SimRunner (asyncio task)  │
  georreferenciada)      │      │                 │  Controller: fixed |   │
  .rou.xml .sumocfg      │      │                 │  maxpressure | rl ◄────┼── models/current (vol)
                         │      ▼                 ▼                        │
                         │  tripinfo/queue ──► outputs/ (vol)             │
                         │  FastAPI: /health  /api/network (GeoJSON)      │
                         │           /api/control  /ws/state (≈5 Hz)      │
                         └───────────────▲────────────────────────────────┘
                                         │ proxy /api, /ws
 navegador ◄── http://<host>:8000 ── sim-api sirve web/ (Leaflet + Chart.js); nginx :8080 solo con --profile nginx

 trainer (perfil train): libsumo + sumo-rl + SuperSuit + SB3 PPO ──► models/<run_id>/
                                                              └────► outputs/tb/ ──► tensorboard :6006
```

**Flujo en vivo.** `SimRunner` avanza SUMO un paso (1 s simulado) por tick, aplica el controlador activo, lee vehículos (`vehicle.getPosition` → `simulation.convertGeo` → lon/lat), semáforos (estado y fase) y métricas agregadas, y publica el último estado. Cada cliente del WebSocket recibe ese estado (sin bloquear la simulación). Los controles (`/api/control`) entran por una cola de comandos que el runner aplica entre pasos: estrategia, accidente (bloqueo de carril con `lane.setDisallowed`), escala de demanda, pausa, velocidad.

**Comparación lado a lado.** El runner puede mantener N simulaciones independientes con la misma semilla y rutas (una por estrategia); el panel muestra 2 mapas o 1 mapa + gráficas comparativas.

**Flujo de entrenamiento.** `trainer` usa la misma red y demanda, con `LIBSUMO_AS_TRACI=1`; guarda `models/<run_id>/model.zip` + `config.json`. `make promote` apunta `models/current` al modelo elegido; `sim-api` lo carga como estrategia `rl` (la misma clase de observación de `rl/` se usa en vivo y en entrenamiento, para evitar desajustes).

### Decisiones técnicas
| Tema | Decisión | Motivo |
|---|---|---|
| Imagen base | `ghcr.io/eclipse-sumo/sumo:1.28.0` (fijada) | imagen oficial; trae SUMO 1.28 + tools (randomTrips, osmGet) |
| Python 3.11 | La imagen trae Python **3.10** (Ubuntu 22.04). Se instala 3.11 desde deadsnakes y, en un venv 3.11, `traci`, `sumolib` y `libsumo` **==1.28.0** desde PyPI (ruedas cp311) | cumple el stack obligatorio sin cambiar de imagen. Ver pregunta 2 |
| Estrategia adaptativa | max-pressure propio (H1) + `actuated` de SUMO (H2) | max-pressure es comparable y testeable; actuated es gratis en SUMO |
| RL | PPO compartido (SB3 + SuperSuit sobre `sumo_rl.parallel_env`); DQN independiente como respaldo | según diseño |
| Recompensa | `r_i = −Δespera_i − presión_i`, `r̂_i = r_i + α·media(r_vecinas)` | función de recompensa propia pasada a sumo-rl |
| Mapa | Leaflet 1.9.4 + teselas OSM, red SUMO como GeoJSON | coordenadas reales; nada de coordenadas inventadas |
| Tests e2e | Playwright en contenedor `mcr.microsoft.com/playwright/python` | nada instalado en el host |

## 2. Estructura de carpetas

```
.
├── CLAUDE.md  PLAN.md  README.md  Makefile  docker-compose.yml  pyproject.toml (ruff, pytest)
├── docker/        sim.Dockerfile · trainer.Dockerfile · nginx.conf
├── sim/
│   ├── network/   build_osm.py (Overpass→netconvert) · grid.py (respaldo) · geo.py (GeoJSON de la red)
│   ├── demand.py  (valley | peak | event; car/moto/ped; --seed)
│   ├── controllers/ base.py · fixed.py · maxpressure.py · rl_policy.py
│   ├── events.py  (accidente: cierre de carril; escala de demanda)
│   └── runner.py  (SimRunner: paso, estado, métricas, comandos)
├── rl/            env.py (wrapper sumo-rl) · observation.py · reward.py · train.py · evaluate.py
├── api/           main.py (FastAPI) · schemas.py · ws.py
├── web/           index.html · app.js · map.js · charts.js · style.css
├── eval/          metrics.py (viaje, espera, colas, Jain) · run_all.py · figures.py
├── scenarios/     <zona>/osm.xml · <zona>.net.xml · <zona>.<escenario>.rou.xml/.sumocfg · vtypes.add.xml
├── models/  outputs/      (generados; volúmenes; protegidos por hook)
├── tests/         unit/ · integration/ · smoke/ · e2e/   (marcador `slow`)
└── .claude/       settings.json · hooks/ · agents/ · skills/ · commands/
```

## 3. Hitos

### H0 · Workspace, Docker y hooks (hoy, 27 oct)
| Criterio de "terminado" | Test que lo demuestra |
|---|---|
| Workspace de Claude Code (CLAUDE.md, hooks, 4 subagentes, 4 skills propias + 2 oficiales, 2 comandos) | `.claude/hooks/test-hooks.sh` → 29/29 ✅ + SessionStart/Stop (hecho) |
| `docker compose build` construye sim-api, trainer, web | salida del build |
| `docker compose up -d` deja sim-api y web `healthy` | `tests/integration/test_health.py` (`/health` 200) |
| SUMO corre en consola dentro del contenedor | `tests/smoke/test_sumo_runs.py` (red 2×2, 300 pasos) |
| `make test` pasa y el hook Stop lo muestra | salida del hook Stop |
| Funciona igual en el equipo de Jose | `make up && make test` en su máquina |

### H1 · Demo (jueves 29 oct) — prioridad absoluta
| Criterio | Test |
|---|---|
| Zona real de Cali con **4 tls** desde OSM, georreferenciada, con andenes/cruces | `test_network.py`: 4 tls, `projParameter` presente, nodo dentro del bbox |
| Demanda pico con carros + motos (vClass motorcycle) | `test_demand.py`: rutas válidas (`duarouter`), ≥1 `moto` |
| Tiempo fijo y max-pressure | `test_controllers.py` (dobles de TraCI: verde mínimo, amarillo 3 s, elige mayor presión) |
| PPO corto (30–60 min reales) entrenado y cargable como estrategia `rl` | `test_train_smoke.py` (`slow`) + `models/current/config.json` |
| FastAPI + WebSocket con vehículos y semáforos | `test_ws.py`: estado con `vehicles` y `tls` |
| Mapa Leaflet en vivo con vehículos y semáforos coloreados en su sitio real | e2e Playwright: marcadores se mueven entre 2 capturas |
| Botón "accidente" cierra un carril | `test_events.py` + e2e |
| Selector de estrategia | `test_ws.py` + e2e |
| 2 gráficas (espera y cola por estrategia) | e2e: los datasets de Chart.js crecen |
| Humo: 300 pasos de cada estrategia | `test_smoke_strategies.py` |
| Respaldo: `make figures` genera gráficas desde el contenedor; video de 1 min | archivos en `outputs/` |

Orden de trabajo (28 oct): imágenes Docker → red OSM de 4 tls → demanda → controladores fixed/max-pressure → **lanzar PPO en segundo plano** → runner + FastAPI. (29 oct): mapa + controles + gráficas → cargar PPO → `make demo` + e2e → ensayo + video.

### H-TRAZAS · Trazas del sistema, asistente de IA y prueba del compañero (propuesto 31 oct – 3 nov)
Objetivo: ver **en vivo y con datos reales** qué hace cada parte del gemelo (SUMO, agentes RL, eventos, asistente LLM, entrenamiento) en una sección **Trazas** del panel en `http://localhost:8000`. El LLM **no controla semáforos**: explica, traduce comandos a acciones de una lista blanca y resume corridas.

**Arquitectura**
```
 trainer ──(SB3 callback)──► outputs/traces/training/<run_id>.jsonl ──┐ (sim-api lo sigue con tail)
                                                                      ▼
 sim-api (FastAPI :8000) ─ / → web/ (panel, mapa, trazas: StaticFiles)
   SimRunner (hilo libsumo) ── Tracer.emit(evento) ──► cola en memoria (no bloquea el paso)
     · sim: agregado por segundo simulado        └► hilo escritor: SQLite outputs/traces.db (lotes)
     · rl: cada decisión por tls                                   + log JSON por evento (stdout)
     · event: accidente/demanda/pausa + impacto a +120 s           + difusión por /ws/state
   FaultInjector (fallo armado, un solo uso)
   /api/assistant → LLMClient (Groq | openai_compat/Ollama | fake) → Pydantic Action → SimRunner
```
Esquema del evento: `trace_id`, `ts` (hora real), `sim_t` (hora simulada), `component` (`sim` · `rl` · `event` · `llm` · `training`), `type`, `status` (`ok` · `warn` · `error` · `fallback`), `tls_id` (si aplica), `data` (JSON propio del tipo). Un `trace_id` agrupa eventos de una misma operación (p. ej. una llamada al LLM con sus reintentos, o un accidente y su impacto).

**Qué se traza**
| Componente | Eventos y datos |
|---|---|
| a) Simulación | `escenario_inicio` / `escenario_fin` (zona `roosevelt4`, escenario, estrategia, semilla) · `sim_segundo`: **agregado** por segundo simulado con vehículos activos por tipo (carro, moto, peatón), latencia media de paso libsumo en ms y factor de tiempo real · `error_traci`, `reconexion` |
| b) Agentes RL | `decision`: tls y nombre de la intersección (`config/intersections.yaml`, p. ej. "Av. Roosevelt × Cra 39"), fase anterior → elegida, motivo resumido (cola y espera por aproximación observadas), recompensa, α y si usó vecinas, latencia de inferencia ms, versión del modelo · `cambio_estrategia`, `carga_modelo` · `fallback_control`: si un agente falla o tarda > 200 ms, **ese** tls pasa a tiempo fijo · `observacion_incompleta` |
| c) Eventos | `accidente` (calle, carril, duración), `cambio_demanda`, `pausa`, `reanudacion`, cada uno con **impacto**: espera media y cola al inyectar y 120 s simulados después (evento `impacto` con el mismo `trace_id`) |
| d) Asistente IA | por llamada: proveedor, modelo, tokens entrada/salida, latencia, costo real, costo equivalente pago y estado (`respuesta_ok`, `accion_validada`, `accion_ejecutada`, `accion_rechazada`, `error_timeout`, `error_limite`, `respuesta_invalida`, `reintento`, `fallback_usado`) |
| e) Entrenamiento | por episodio: recompensa media, espera media, duración, timesteps acumulados. Callback nuevo en `rl/train.py` escribe JSONL en `outputs/traces/training/`; sim-api lo ingiere. Solo aparece en entrenamientos lanzados después de este hito (los modelos ya entrenados no tienen ese registro) |

Notas honestas sobre el sistema actual:
- La simulación en vivo usa **libsumo** (en proceso), no un socket TraCI: no hay una "desconexión" real posible. El fallo "Desconexión de TraCI" se implementa como: `saveState` → `libsumo.close()` → nuevo `start` → `loadState`, y el escenario sigue desde el mismo segundo. Los errores reales de libsumo (`TraCIException`/`FatalTraCIError`) usan el mismo camino de reconexión.
- La estrategia `actuated` es de H2; las trazas cubren las estrategias que existan (hoy: fijo, max-pressure, RL).
- La red de la demo es la **Av. Roosevelt (Calle 6) entre Cra 34 y Cra 39**. Una pregunta por "Calle 5 con Cra 39" no corresponde a ninguna intersección: el asistente lo dice y propone la más cercana por nombre, no inventa datos.

**Asistente de IA**
| Variable | Por defecto | Notas |
|---|---|---|
| `LLM_PROVIDER` | `groq` | `groq` · `openai_compat` (Ollama u otro) · `fake` (tests y e2e, sin red) |
| `LLM_MODEL` | `openai/gpt-oss-120b` | |
| `LLM_BASE_URL` | `https://api.groq.com/openai/v1` | Ollama: `http://host.docker.internal:11434/v1` |
| `LLM_PLAN` | `free` | `free` → costo real US$ 0,0000; `paid` → costo real = equivalente |
| `GROQ_API_KEY` | vacío | solo en `.env` (no versionado; `.env.example` sin valores). Nunca en trazas, logs, respuestas ni commits; un test lo verifica |

- **Tarifas verificadas el 30 oct 2026** en `console.groq.com/docs/model/openai/gpt-oss-120b`: US$ 0,15 / M tokens de entrada, 0,075 / M entrada en caché, 0,60 / M salida (coinciden con la referencia del enunciado). Van en `config/llm_pricing.yaml` con fuente y fecha.
- **Límites**: `console.groq.com/docs/rate-limits` lista para `openai/gpt-oss-120b` 30 RPM, 1 000 RPD, 8 000 TPM y 200 000 TPD, pero no aclara si son los del plan gratis; los valores exactos de la cuenta se confirman con la prueba `live` (cabeceras `x-ratelimit-*`). Se configuran en el YAML; un limitador local de 30 RPM evita pasarse y registra `limite_alcanzado` cuando lo alcanza o cuando Groq responde 429 (con `retry-after`).
- Cliente con `httpx` (ya en la imagen). `pyyaml` 6.0.3 y `sqlite3` ya están en la imagen: **no se agregan dependencias**.
- Funciones: **explicar** (contexto = eventos `decision` reales de ese tls: colas, espera, fase, recompensa), **comandos** (JSON → Pydantic contra la lista blanca `provocar_accidente`, `cambiar_estrategia`, `cambiar_demanda`, `pausar`, `reanudar`, `comparar`; se ejecuta con las mismas funciones de `SimRunner` que `/api/control`; `comparar` resume `outputs/eval/summary.md`), **resumen** de una corrida con sus métricas reales.
- Resiliencia: timeout 20 s, 2 reintentos con backoff exponencial ante 429 y 5xx, fallback por reglas con las métricas. En fallback los comandos no ejecutan nada.

**Panel "Trazas"** (sección nueva en `web/`)
- Indicadores: factor de tiempo real, latencia media de paso, decisiones RL/min, latencia media de inferencia, semáforos en fallback, llamadas LLM, tokens, costo real y equivalente pago, fallos totales. Todos calculados desde `traces.db` por `/api/traces/summary`.
- Filtros por componente (Simulación, Agentes RL, Eventos, Asistente IA, Entrenamiento); línea de eventos en vivo con hora real y simulada; clic → detalle. Clic en un semáforo del mapa → filtra sus decisiones.
- **Armar fallo** (aplica una vez y se desarma): Agente RL sin respuesta → ese tls a tiempo fijo · Detector con datos perdidos → observación incompleta, el agente usa el último valor válido · Desconexión de TraCI → reconexión y reanudación · Timeout del LLM / 429 → reintentos y fallback · Respuesta inválida del LLM → acción rechazada.
- Endpoints: `GET /api/traces` (filtros `component`, `tls_id`, `desde`, `hasta`, `limit`), `GET /api/traces/{trace_id}`, `GET /api/traces/summary`, `GET /api/traces/export.csv`, `POST /api/faults/arm`, `POST /api/assistant`. Eventos nuevos por el `/ws/state` existente (campo `traces` con lo nuevo desde el último mensaje).
- **Rendimiento ≤ 5 %**: `emit` solo encola; la escritura a SQLite va en lotes en otro hilo; `sim_segundo` es agregado. Se mide con `eval/bench_tracing.py`: mismo escenario y semilla, N pasos a máxima velocidad (sin el límite de velocidad del panel), con y sin trazas, varias repeticiones; resultado en `outputs/bench/tracing.json`.

**Puerto 8000, README y arranque**
- FastAPI sirve `web/` en `/`; panel, mapa y trazas en `http://localhost:8000`. nginx (`:8080`) pasa a perfil opcional `nginx`; `make e2e` y `make demo` apuntan a 8000.
- README: "Cómo correrlo desde cero" para Windows (PowerShell + Docker Desktop), macOS y Linux. Sin clave, el asistente funciona en modo fallback.
- `scripts/medir_arranque.ps1` y `scripts/medir_arranque.sh`: `docker compose up -d --build`, sondean `http://localhost:8000` hasta que responde (con tiempo máximo) e imprimen los minutos.
- Al final del README, la sección "Prueba del compañero" tal cual la diste; los dos últimos campos quedan en blanco.

| Criterio de "terminado" | Test que lo demuestra |
|---|---|
| Formato y guardado de eventos; indicadores; costo real y equivalente | `tests/unit/test_traces.py`, `test_trace_summary.py`, `test_llm_pricing.py` |
| Acciones del LLM: válidas, inválidas, fuera de lista blanca | `tests/unit/test_llm_actions.py` |
| Cliente LLM: timeout, reintentos, 429/5xx, fallback, limitador | `tests/unit/test_llm_client.py` con `httpx.MockTransport` (sin red) |
| La clave nunca aparece en DB, log ni respuestas | `tests/unit/test_traces.py` (clave falsa) |
| Cada uno de los 6 fallos genera sus eventos, activa su respaldo y se desarma tras usarse | `tests/integration/test_faults.py` (parametrizado) |
| 300 pasos con RL → decisiones trazadas para las 4 intersecciones; accidente con impacto a +120 s; `summary` = eventos guardados | `tests/integration/test_tracing_run.py` |
| Trazas cuestan ≤ 5 % del factor de tiempo real | `tests/perf/test_tracing_overhead.py` (`slow`) + `outputs/bench/tracing.json` |
| Panel: Trazas carga, filtros, clic en intersección filtra, "Agente RL sin respuesta" muestra el fallback en vivo | `make e2e` en `localhost:8000` (LLM `fake`) |
| Una llamada real a Groq: modelo, tokens, costo y cabeceras de límite | `tests/live/test_groq_live.py` (marcador `live`, `make test-live`, excluido de `make test`, `test-all` y el hook Stop) |
| Arranque medible | `scripts/medir_arranque.sh` corrido aquí (resultado real en la bitácora) |
| `test-reviewer` APROBADO; `PLAN.md`, `CLAUDE.md`, `README.md`, `BITACORA.md` actualizados | revisión + diff |

Archivos nuevos: `sim/tracing.py` (Tracer, cola, escritor SQLite, log JSON), `sim/faults.py`, `api/llm/{client,providers,actions,context,fallback}.py`, `config/{llm_pricing,intersections}.yaml`, `eval/bench_tracing.py`, `web/traces.js`, `scripts/medir_arranque.{ps1,sh}`, `.env.example`, tests. Cambios: `sim/runner.py` y `sim/controllers/rl_policy.py` (emitir trazas, fallback por tls, último valor válido), `rl/train.py` (callback de episodios), `api/main.py`, `web/index.html`/`app.js`, `docker-compose.yml` (`env_file: .env` opcional, montar `./web` y `./config`, nginx a perfil), `Makefile`, `pyproject.toml` (marcadores `live` y `perf`), `.gitignore`.

**Estado al 30 oct (resultados reales)**
- `make test`: 138 passed, 1 skipped (`live`). Incluye `tests/integration/test_tracing_run.py` con el modelo RL de este equipo (`ppo_roosevelt4_a0_s0_20261028-0402`, de humo, 2048 timesteps): decisiones de las 4 intersecciones en 300 pasos, impacto del accidente a +120 s, los 6 fallos con su respaldo y desarme, y la igualdad de la recompensa rápida con la de sumo-rl.
- `make e2e` contra la app real (puerto 8001 de prueba, porque el 8000 de este equipo lo usa otro proyecto): 17/17 OK; captura en `docs/img/panel_trazas.png` (copiada de `outputs/e2e/panel_traces_fallback.png`).
- **Costo del trazado: 8,35 %** (mediana de 7 pares; RTF 759 → 686 pasos/s a máxima velocidad, RL, `outputs/bench/tracing.json`, 31 oct 04:23). **No cumple el 5 %** y `tests/perf/test_tracing_overhead.py` (`slow`) falla. La medición es ruidosa en este equipo (pares de 5,9 % a 17,9 %; la misma corrida sin trazas varió entre 543 y 849 pasos/s con otros contenedores activos). Partes medidas dentro del hilo de simulación: recompensa ≈ 3 %, colas por aproximación ≈ 1,2 %, `sim_segundo` ≈ 1,1 %, `emit` ≈ 0,7 %. Ya aplicado: sin despertar hilos por evento (de 15 % a 9 %), escritura SQLite/JSONL en un proceso aparte, ids baratos, recompensa con caché y sin carriles peatonales, colas por `edge`. A la velocidad del panel (≤ 50×) la simulación tiene ~15× de margen y el factor de tiempo real no cambia.
- Opciones para bajar de 5 % (a decidir): (a) recompensa y aproximaciones solo cuando la fase cambia; (b) agregar `sim_segundo` cada 5 s simulados al ir a > 100×; (c) medir en un equipo sin otras cargas.
- Sin probar aún: la llamada real a Groq (`make test-live`, falta la clave) y `scripts/medir_arranque.*` en este equipo (puerto 8000 ocupado).

### H2 · Corredor completo (2 nov)
Corredor de 6–9 tls revisado en netedit; peatones en todas las intersecciones; escenarios valley/peak/event; `actuated` como 4.ª estrategia; mapa completo (pausa, velocidad, cambio a pico, lado a lado, fase en cada semáforo). Tests: red 6–9 tls, peatones presentes, 3 escenarios × 3 estrategias × 300 pasos, e2e de todos los controles.

### H3 · MARL coordinado (9 nov)
PPO α=0 y α=0,3 (≥2 semillas de entrenamiento cada uno), curvas en TensorBoard, ajuste de recompensa si no supera a max-pressure. Tests: forma de observación con vecinas, efecto de α en la recompensa, reproducibilidad con semilla. Entregable: comparación preliminar en `outputs/eval/prelim.md`.

### H4 · Evaluación y cierre (16 nov)
3 estrategias × 3 escenarios × 5 semillas; tablas y figuras; `goal_check.md` con la reducción real de espera en pico (con IC 95 %) frente al objetivo de 15 %; panel final; README con instrucciones y resultados citando archivos. `test-reviewer` revisa todo el repo.

### Dataset de escenarios para entrenar y evaluar (transversal, H1–H4)
En RL el agente aprende de la experiencia que genera en SUMO, pero **el entrenamiento sí requiere un dataset de escenarios de demanda generado por nosotros**:
- `sim/demand.py` genera archivos `.rou.xml` reproducibles por `(escenario, semilla)`, con 35 % de motos en pico y peatones.
- **Split de entrenamiento:** semillas 100–119 (pico en H1; valle, pico y evento desde H2). Cada episodio toma un archivo al azar de este split.
- **Split de evaluación:** semillas 0–4 por escenario, nunca vistas en el entrenamiento (objetivo del 15 % medido aquí).
- `scenarios/<zona>/demand/manifest.csv` registra split, escenario, semilla, archivo y conteos; un test verifica que los splits son disjuntos.
- Opcional: calibrar volúmenes con aforos reales de Cali (Secretaría de Movilidad o datos abiertos) y citar la fuente.
- Issues en GitHub: #1 (dataset), #2 (controladores), #3 (PPO), #4 (netedit), milestone «H1 · Demo (29 oct)».

## 4. Pruebas (FASE 3, transversal)
- **Unitarias:** red y rutas, fixed y max-pressure, métricas (Jain con casos conocidos: iguales → 1, uno solo → 1/n), observación y recompensa.
- **Integración:** healthchecks de compose, `/health`, WebSocket con vehículos y tls, accidente cambia el carril.
- **Humo:** 300 pasos por estrategia; PPO 1000 timesteps guarda y carga (`slow`).
- **E2E:** Playwright en contenedor: carga, movimiento, controles, gráficas.
- **Resultados:** verificación del ≥15 % con números reales, cumpla o no.

## 5. Riesgos y plan B
| Riesgo | Señal | Plan B |
|---|---|---|
| Entrenamiento lento | < 300 pasos/s con libsumo | episodios de 15–20 min simulados para la demo, red de 4 tls, entrenar de noche; varias semillas en paralelo (8 núcleos) |
| Red OSM con errores (giros imposibles, tls partidos, teletransportes) | warnings de netconvert, `teleports > 0` en 300 pasos | `--tls.join`/`--junctions.join`, limpieza en netedit, o zona de Cali más pequeña; **2×2 sintética solo como último recurso y declarado** |
| Overpass saturado (ya ocurrió hoy) | 502/timeout | espejos (kumi, private.coffee) con reintentos; `osm.xml` se versiona en `scenarios/` para no depender de la red |
| Corredor con carriles MIO (p. ej. Calle 5) | carriles `psv` en la red | modelarlos como exclusivos de bus o excluir `psv` en la demo |
| Peatones vuelven lenta la simulación | caída fuerte de pasos/s | peatones solo en evaluación y en el mapa de demo, no en entrenamiento |
| El agente no supera la base | espera RL ≥ fijo en pico | recompensa solo de espera, subir verde mínimo, más timesteps, DQN independiente; reportar la verdad |
| Mapa web no listo el jueves | e2e falla el 29 a mediodía | gráficas generadas por el contenedor + video de respaldo |
| Acceso desde otros equipos (WSL2) | `<IP>:8080` no responde | `networkingMode=mirrored` en WSL o `netsh portproxy`; túnel cloudflared (comentado en compose) |

## 6. Decisiones tomadas (27 oct)
- Zona demo: **Av. Roosevelt (OSM `Calle 6`, `alt_name=Avenida Roosevelt`) entre Cra 34 y Cra 39**: 4 tls (Cra 34, Cra 36, Cra 36A Bis, Cra 39), recortada con `--keep-edges.in-geo-boundary`; `scenarios/roosevelt4/osm.xml` versionado. El corredor H2 puede extenderse hasta Cra 42/44 (5.º tls en Cra 42) y más al sur.
- Python 3.11 en la imagen oficial vía `uv` (equivalente a deadsnakes, sin depender del PPA).
- Contenedores corren con el UID/GID del host (archivos de `scenarios/`, `models/`, `outputs/` no quedan como root).
- Sin MCP de Playwright por ahora; e2e en contenedor.

## 7. Preguntas abiertas
1. **Zona exacta de Cali.** No pude verificar hoy los semáforos en OSM (Overpass saturado); lo hago primero en H1. Recomendación: **Av. Roosevelt entre Cra 34 y Cra 44** (no tiene troncal MIO, así que la red es más limpia). Alternativa: **Calle 5 entre Cra 34 y Cra 44** (más emblemática, pero con carriles exclusivos del MIO). ¿Cuál prefieren, o tienen otro tramo? ¿Y cuál debe ser el corredor completo de H2 (6–9 tls)?
2. **Python 3.11 sobre la imagen oficial de SUMO** (que trae 3.10): ¿aprueban instalar 3.11 desde deadsnakes dentro de la imagen? La alternativa es aceptar 3.10.
3. **MCP de Playwright:** existe como plugin oficial (`playwright@claude-plugins-official`, ejecuta `npx @playwright/mcp@latest` en el host). ¿Lo añado a `.mcp.json`? Sin él, los e2e igual corren en contenedor.
4. **Proporción de motos** en pico: propongo 35 %. ¿Tienen un dato de Cali (p. ej. aforos de la Secretaría de Movilidad)?
5. **Comparación lado a lado:** ¿2 mapas sincronizados (más pesado) o 1 mapa + gráficas comparativas (recomendado para la demo)?
6. **Equipo de Jose:** ¿Windows con Docker Desktop o Linux? Afecta el acceso por LAN y los permisos de volúmenes.

### Decisiones de H-TRAZAS (30 oct, al ejecutar)
7. **Puerto:** panel servido por FastAPI en `:8000`; nginx (`:8080`) en perfil opcional `nginx`. CI, `make demo` y `make e2e` apuntan a 8000.
8. **"Desconexión de TraCI":** simulada con `saveState` → cerrar libsumo → reabrir → `loadState` (mismo segundo). Errores reales: desde el último punto de control (cada 300 s).
9. **Fechas:** H-TRAZAS en paralelo con lo de Milton (H2).
10. **Prueba del compañero:** la sección queda con los datos dados; tiempo y problemas se llenan con `scripts/medir_arranque.ps1`.
11. **Clave desde el panel** (pedido del usuario el 30 oct): `POST/DELETE /api/llm/key`, `POST /api/llm/test`; se guarda en `secrets/llm_api_key` (modo 600, fuera de git) y gana sobre la del archivo de entorno. Nunca se devuelve.
