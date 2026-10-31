# Gemelo digital de movilidad urbana · Cali

Gemelo digital de un corredor vial real de Cali (OSM → SUMO). Cada intersección semaforizada es un agente de RL (PPO con parámetros compartidos) que controla su semáforo vía TraCI/libsumo y se coordina con sus vecinas. Se compara contra tiempo fijo y max-pressure/actuated en un panel web con mapa (FastAPI + WebSocket + Leaflet + Chart.js).

- Equipo: Milton Quintero (simulación y RL), Jose Arias (panel web y evaluación).
- Fechas: demo **jueves 29 oct 2026** · entrega **17 nov 2026**.
- Plan, hitos y estado: `PLAN.md` (fuente de verdad; la línea `**Hito actual:**` la lee el hook de inicio).

## Idioma
Respuestas y documentación en español. Código, nombres de archivo, commits y ramas en inglés.

## Estructura
```
sim/        red (OSM→netconvert), demanda, controladores (fixed, maxpressure), runner TraCI
rl/         entorno multiagente (sumo-rl/PettingZoo), observación, recompensa, train, evaluate
api/        FastAPI: /health, /api/network, /api/control, /ws/state, /api/traces*, /api/faults, /api/assistant, /api/llm/*; sirve web/ en :8000
web/        HTML/JS estático (Leaflet, Chart.js) servido por sim-api (nginx :8080 opcional, perfil `nginx`)
config/     precios del LLM, nombres de intersecciones
secrets/    clave del LLM puesta desde el panel — no versionado, no leer
eval/       métricas (incluido índice de Jain), corrida 3×3×5, tablas y figuras
scenarios/  redes y demanda de Cali (.net.xml, .rou.xml, .sumocfg)   [volumen]
models/     modelos entrenados — GENERADO, no editar a mano         [volumen]
outputs/    tripinfo, métricas, tensorboard, figuras — GENERADO     [volumen]
tests/      pytest (unit, integración, humo; `slow` para lo lento) + e2e Playwright
docker/     Dockerfiles (sim, trainer) y nginx.conf
```

## Comandos clave
| Comando | Qué hace |
|---|---|
| `make up` | `docker compose up -d --build sim-api` (panel, API y trazas en `http://localhost:8000`) |
| `make test` | `pytest -m "not slow"` dentro de sim-api |
| `make test-all` | toda la suite, incluidos `slow` |
| `make train-smoke` | PPO 1000 timesteps en trainer; verifica que el modelo carga |
| `make train ...` | entrenamiento real en segundo plano (ver skill `train-agent`) |
| `make evaluate` | 3 estrategias × 3 escenarios × 5 semillas (skill `evaluate-strategies`) |
| `make demo` | levanta y corre la checklist de demo (skill `run-demo`) |
| `make e2e` | Playwright en contenedor contra el panel en `:8000` |
| `make test-live` | **una** llamada real a Groq (marcador `live`; nunca en `make test`) |
| `make bench-tracing` | costo del trazado sobre el RTF → `outputs/bench/tracing.json` (meta ≤ 5 %) |
| `scripts/medir_arranque.sh` / `.ps1` | `docker compose up -d --build` y minutos hasta que responde `localhost:8000` |

## Convenciones
- **Todo corre en Docker.** Cualquier comando de Python o SUMO: `docker compose run --rm sim-api <cmd>` (o `trainer` para RL). No instalar SUMO ni paquetes de Python en el host. Nada de `sumo-gui` en contenedores.
- Todas las redes son de **Cali, Colombia**, desde OSM, conservando la georreferencia. `netgenerate` (2×2) solo para tests o como último recurso declarado.
- Reproducibilidad: toda generación de demanda, simulación y entrenamiento recibe `--seed`.
- **No inventar resultados.** Todo número en README/PLAN/informe sale de un archivo en `outputs/` producido por una ejecución real, y se cita la ruta.
- Ramas `feat/h<n>-<tema>`, commits pequeños en inglés (imperativo). Sin push sin aprobación.
- Preguntar antes de: borrar archivos, cambiar el stack, añadir servicios externos o MCP, hacer push.
- Subagentes: `sumo-engineer` (sim/, scenarios/), `rl-engineer` (rl/), `web-engineer` (api/, web/), `test-reviewer` (tests/, revisa cada hito; no toca producción).

## Fases y aprobación
1. **PLAN** → `PLAN.md`. 2. **EJECUCIÓN** hito por hito. 3. **TEST** en cada hito y al final.
**Regla:** no se pasa de fase ni de hito sin aprobación explícita del usuario. Al cerrar un hito: resumen corto, cómo probarlo, qué sigue, y esperar visto bueno.

## Definición de "terminado" por hito
Un hito está terminado cuando (a) todos sus criterios de `PLAN.md` tienen un test o salida real que los demuestra, (b) `make test` pasa en un clon limpio tras `docker compose build`, (c) `test-reviewer` emite APROBADO, y (d) `PLAN.md` está actualizado.
- **H0** workspace, hooks y Docker: `docker compose up` sano, `/health` OK, `make test` pasa, hooks probados.
- **H1 demo (29 oct)**: zona real de Cali con 4 tls; pico con motos; fixed + max-pressure + PPO corto; mapa en vivo con accidente y selector; 2 gráficas; `make demo` OK.
- **H2 (2 nov)**: corredor de 6–9 tls revisado en netedit, peatones, 3 escenarios, mapa completo.
- **H3 (9 nov)**: MARL α=0 vs α=0,3 entrenados y comparados; recompensa ajustada.
- **H4 (16 nov)**: evaluación 5 semillas, tablas, figuras, verificación ≥15 %, panel final, README.
- **H-TRAZAS (30 oct – 3 nov)**: trazas de sim/RL/eventos/LLM/entrenamiento (`sim/tracing.py`, SQLite `outputs/traces.db` + `outputs/traces/events.jsonl`), panel «Trazas» con «Armar fallo» (6 fallos, `sim/faults.py`), asistente LLM (`api/llm/`) que **no controla semáforos**, panel servido en `:8000`, costo del trazado ≤ 5 %.

## Asistente de IA y trazas
- Variables (archivo de entorno, ver `.env.example`): `LLM_PROVIDER` (`groq` · `openai_compat` · `fake`), `LLM_MODEL`, `LLM_BASE_URL`, `LLM_PLAN` (`free` → costo real US$ 0), `GROQ_API_KEY`. La clave también se puede poner desde el panel: queda en `secrets/llm_api_key` (modo 600, ignorado por git) y gana sobre la del archivo de entorno.
- Precios y límites del proveedor en `config/llm_pricing.yaml` (con fuente y fecha); nombres de intersecciones en `config/intersections.yaml`.
- Los tests usan `LLM_PROVIDER=fake` (lo fija `tests/conftest.py`): **nunca** llamadas reales en tests automáticos.
- Las acciones del LLM pasan por la lista blanca de `api/llm/actions.py` (Pydantic) antes de tocar la simulación.
- Nada en `sim/` o `rl/` debe escribir trazas fuera de `Tracer.emit`; lo caro (recompensa, aproximaciones) se calcula solo si `tracer.enabled`.

## Hooks (`.claude/hooks/`, registrados en `.claude/settings.json`)
- PreToolUse Bash: bloquea `rm -rf /` o `~`, `docker system prune -a`, `git push --force` a main y acceso a `.env`.
- PreToolUse Read/Edit/Write: bloquea `.env` y la edición manual de `models/` y `outputs/`.
- PostToolUse Edit/Write: `ruff format` + `ruff check --fix` en `.py` (ruff del host o imagen `ghcr.io/astral-sh/ruff`); XML bien formado en archivos SUMO.
- Stop: `pytest -m "not slow" -q` en sim-api; avisa sin bloquear. `stop-logbook.sh`: si hubo commits en la sesión y `BITACORA.md` no cambió, pide (una vez) registrar la entrada.
- SessionStart: hito actual, últimas entradas de `BITACORA.md`, commits posteriores a la última entrada, cambios sin commit, issues abiertos (`gh`) y `docker compose ps`.
- SessionEnd: si nadie escribió la entrada, agrega una automática con los commits de la sesión.

## Bitácora (`BITACORA.md`, versionada)
Al terminar trabajo con commits, agregar arriba una entrada `## <fecha> · <autor> · <rama>` con `HEAD`, **Hecho** (resultados reales), **Siguiente** (con responsable) y **Bloqueos**, y hacer commit. Es la memoria compartida entre Jose, Milton y las sesiones de Claude Code.
- Autoprueba: `.claude/hooks/test-hooks.sh`.
- Requisito del host: `jq` (los hooks usan `python3` como respaldo si falta).
