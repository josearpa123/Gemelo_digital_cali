# PLAN · Gemelo digital de movilidad urbana · Cali

**Hito actual:** H0 · workspace, Docker y hooks (27 oct): workspace y hooks listos; Docker pendiente de aprobación del plan

| Hito | Fecha | Estado |
|---|---|---|
| H0 Workspace + Docker + hooks | 27 oct | workspace ✅ · hooks ✅ (29/29 casos + SessionStart/Stop) · Docker ⏳ |
| H1 Demo | **29 oct** | pendiente |
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
 navegador ◄── http://<host>:8080 ── web (nginx:alpine): index.html + Leaflet + Chart.js

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

### H2 · Corredor completo (2 nov)
Corredor de 6–9 tls revisado en netedit; peatones en todas las intersecciones; escenarios valley/peak/event; `actuated` como 4.ª estrategia; mapa completo (pausa, velocidad, cambio a pico, lado a lado, fase en cada semáforo). Tests: red 6–9 tls, peatones presentes, 3 escenarios × 3 estrategias × 300 pasos, e2e de todos los controles.

### H3 · MARL coordinado (9 nov)
PPO α=0 y α=0,3 (≥2 semillas de entrenamiento cada uno), curvas en TensorBoard, ajuste de recompensa si no supera a max-pressure. Tests: forma de observación con vecinas, efecto de α en la recompensa, reproducibilidad con semilla. Entregable: comparación preliminar en `outputs/eval/prelim.md`.

### H4 · Evaluación y cierre (16 nov)
3 estrategias × 3 escenarios × 5 semillas; tablas y figuras; `goal_check.md` con la reducción real de espera en pico (con IC 95 %) frente al objetivo de 15 %; panel final; README con instrucciones y resultados citando archivos. `test-reviewer` revisa todo el repo.

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

## 6. Preguntas abiertas
1. **Zona exacta de Cali.** No pude verificar hoy los semáforos en OSM (Overpass saturado); lo hago primero en H1. Recomendación: **Av. Roosevelt entre Cra 34 y Cra 44** (no tiene troncal MIO, así que la red es más limpia). Alternativa: **Calle 5 entre Cra 34 y Cra 44** (más emblemática, pero con carriles exclusivos del MIO). ¿Cuál prefieren, o tienen otro tramo? ¿Y cuál debe ser el corredor completo de H2 (6–9 tls)?
2. **Python 3.11 sobre la imagen oficial de SUMO** (que trae 3.10): ¿aprueban instalar 3.11 desde deadsnakes dentro de la imagen? La alternativa es aceptar 3.10.
3. **MCP de Playwright:** existe como plugin oficial (`playwright@claude-plugins-official`, ejecuta `npx @playwright/mcp@latest` en el host). ¿Lo añado a `.mcp.json`? Sin él, los e2e igual corren en contenedor.
4. **Proporción de motos** en pico: propongo 35 %. ¿Tienen un dato de Cali (p. ej. aforos de la Secretaría de Movilidad)?
5. **Comparación lado a lado:** ¿2 mapas sincronizados (más pesado) o 1 mapa + gráficas comparativas (recomendado para la demo)?
6. **Equipo de Jose:** ¿Windows con Docker Desktop o Linux? Afecta el acceso por LAN y los permisos de volúmenes.
