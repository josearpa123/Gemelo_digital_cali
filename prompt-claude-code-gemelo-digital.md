# Prompt para Claude Code · Gemelo digital de movilidad urbana

> Copia todo lo que está debajo de la línea y pégalo en Claude Code, en una carpeta vacía (idealmente un repo de GitHub recién clonado).

---

Eres el ingeniero principal de un proyecto académico de IA. Vas a montar el workspace completo de Claude Code (CLAUDE.md, hooks, subagentes, skills, comandos) y luego construir el proyecto en tres fases estrictas: **1) PLAN, 2) EJECUCIÓN, 3) TEST**. No pases a la siguiente fase sin mi aprobación explícita.

Responde y documenta en español. El código, nombres de archivos y commits en inglés.

## 1. Contexto del proyecto

**Nombre:** Gemelo digital de movilidad urbana con agentes de IA.
**Equipo:** Milton Quintero (simulación y RL) y Jose Arias (panel web y evaluación).
**Fechas:** hoy martes 27 oct 2026 · **demo jueves 29 oct** · entrega final 17 nov 2026.

**Objetivo general:** gemelo digital de un corredor vial de Cali en SUMO, donde cada intersección es un agente de aprendizaje por refuerzo que controla su semáforo vía TraCI y se coordina con sus vecinas, comparado contra estrategias convencionales en un panel web con mapa.

**Objetivos específicos (criterios de aceptación):**
1. **Todas las redes y mapas son de Cali, Colombia** (desde la demo): extraer de OpenStreetMap una zona real de Cali (osmWebWizard o descarga OSM → netconvert) con 4 a 9 intersecciones semaforizadas, carros, motos (vClass motorcycle) y peatones (andenes y cruces). Para la demo, una zona pequeña de 4 intersecciones; luego se amplía al corredor completo. Propuesta inicial de zona: un tramo de la Calle 5 o de la Avenida Roosevelt; confírmame la zona exacta en las preguntas abiertas. La cuadrícula sintética (netgenerate) solo se usa como respaldo para tests o si la red OSM falla.
2. Tres escenarios de demanda: hora valle, hora pico y evento (cierre de carril por accidente).
3. Tres estrategias sobre el mismo tráfico: tiempo fijo, adaptativo convencional (actuated de SUMO y/o max-pressure propio) y agentes RL multiagente.
4. Agentes RL que logren ≥ 15 % menos tiempo de espera promedio que tiempo fijo en hora pico.
5. Cuatro métricas con 5 semillas por escenario: tiempo de viaje, tiempo de espera, longitud de colas y equidad entre vías (índice de Jain).
6. Panel web con mapa en vivo, estado de semáforos, botones para inyectar eventos, selector de estrategia y gráficas comparativas.

**Diseño del componente de IA (MARL):**
- Agente: uno por semáforo (tls) de SUMO.
- Observación: fase actual (one-hot), tiempo en fase, densidad y cola por carril de entrada + colas agregadas de las vecinas.
- Acción: siguiente fase verde (discreta); amarillo de 3 s automático; verde mínimo 10 s.
- Recompensa: −(espera acumulada) − presión propia + α × recompensa de vecinas (α configurable; experimentos con α = 0 y α = 0,3).
- Algoritmo: PPO con parámetros compartidos (Stable-Baselines3 + SuperSuit sobre el entorno PettingZoo de sumo-rl). Alternativa: DQN independiente.
- Decisión cada 5 s simulados; episodios de 1 h simulada; entrenamiento con libsumo y sin GUI.

**Stack obligatorio:** Python 3.11, SUMO 1.2x, TraCI, libsumo, sumo-rl, Stable-Baselines3, SuperSuit, PyTorch CPU, TensorBoard, FastAPI + WebSocket, Leaflet sobre OpenStreetMap centrado en Cali, con la red de SUMO superpuesta en su ubicación real (coordenadas con `traci.simulation.convertGeo`; la red debe conservar la georreferencia de OSM), Chart.js, pandas + matplotlib, pytest, ruff.

**Requisito obligatorio: TODO corre en Docker.** Un solo `docker compose up` levanta el sistema, sin instalar SUMO ni Python en el host.

| Servicio | Base | Qué corre | Puerto |
| --- | --- | --- | --- |
| `sim-api` | imagen oficial de SUMO (`ghcr.io/eclipse-sumo/sumo`) + Python | SUMO + TraCI + FastAPI/WebSocket | 8000 |
| `trainer` | misma imagen + PyTorch CPU + SB3 (perfil `train`) | entrenamiento con libsumo | — |
| `web` | `nginx:alpine` | página del mapa | 8080 |
| `tensorboard` | imagen del trainer | curvas de entrenamiento | 6006 |

Volúmenes: `./scenarios`, `./models`, `./outputs`. No usar `sumo-gui` dentro de contenedores. La web debe funcionar en `localhost:8080` y desde otros equipos en `http://<IP>:8080`; deja preparado (comentado) un servicio opcional de túnel (cloudflared).

## 2. Montaje del workspace de Claude Code (hazlo antes del plan)

### 2.1 `CLAUDE.md` en la raíz
Incluye: resumen del proyecto, estructura de carpetas, comandos clave (`make up`, `make test`, `make train-smoke`, `make demo`), convenciones (todo comando de Python/SUMO se ejecuta dentro del contenedor con `docker compose run --rm ...`), las tres fases y la regla de no avanzar sin aprobación, y la definición de "terminado" de cada hito.

### 2.2 Hooks en `.claude/settings.json`
Crea scripts en `.claude/hooks/` (bash + `jq`, ejecutables) y regístralos en `.claude/settings.json` con el formato oficial de hooks de Claude Code. Verifica el formato actual en la documentación antes de escribirlo.

- **PreToolUse (Bash):** bloquear (exit 2 con mensaje) comandos destructivos: `rm -rf /`, `rm -rf ~`, `docker system prune -a`, `git push --force` a main, y cualquier lectura o escritura de `.env` con secretos.
- **PreToolUse (Edit|Write):** impedir editar `models/` y `outputs/` a mano (son artefactos generados).
- **PostToolUse (Edit|Write):** si el archivo es `.py`, correr `ruff format` y `ruff check --fix` sobre ese archivo; si es `.xml` de SUMO (`.net.xml`, `.rou.xml`, `.sumocfg`), validar que sea XML bien formado.
- **Stop:** correr la suite rápida `pytest -m "not slow" -q` dentro del contenedor y mostrar el resumen; si falla, avisar sin bloquear.
- **SessionStart:** mostrar el hito actual leyendo `PLAN.md` y el estado de `docker compose ps`.

Prueba cada hook con un caso que deba pasar y uno que deba bloquearse, y muéstrame el resultado.

### 2.3 Subagentes en `.claude/agents/`
- `sumo-engineer`: redes, demanda, escenarios, TraCI.
- `rl-engineer`: entorno multiagente, recompensa, entrenamiento, evaluación.
- `web-engineer`: FastAPI, WebSocket, Leaflet, Chart.js, interacciones del panel.
- `test-reviewer`: escribe y revisa tests, no escribe código de producción; revisa cada hito con ojos frescos antes de declararlo terminado.

### 2.4 Skills
1. Revisa qué skills y plugins oficiales hay disponibles (por ejemplo, el marketplace `anthropics/skills` con `/plugin marketplace add anthropics/skills`) e instala solo las que sirvan aquí, como las de pruebas de aplicaciones web con Playwright y diseño de frontend. Confirma que existen antes de instalarlas y dime cuáles instalaste.
2. Crea skills propias del proyecto en `.claude/skills/<nombre>/SKILL.md`:
   - `sumo-scenario`: generar una red (netgenerate u OSM → netconvert con `--sidewalks.guess --crossings.guess`), la demanda con motos y peatones, y el `.sumocfg`.
   - `train-agent`: lanzar un entrenamiento con parámetros (red, α, timesteps, semilla) y guardar modelo y logs.
   - `evaluate-strategies`: correr las 3 estrategias × 3 escenarios × 5 semillas y producir tablas y figuras.
   - `run-demo`: levantar el sistema y verificar que la demo funciona de punta a punta.

### 2.5 Comandos y MCP
- Comandos en `.claude/commands/`: `/milestone` (estado del hito y siguiente paso), `/demo-check` (checklist de la demo).
- Si está disponible, configura en `.mcp.json` un servidor MCP de Playwright para los tests de la web. Confírmame antes de añadir cualquier MCP.

## 3. FASE 1 · PLAN (usa modo plan; no escribas código del proyecto)

Entrega `PLAN.md` con:
- Arquitectura (componentes y flujo de datos SUMO → TraCI → FastAPI → WebSocket → navegador; y trainer → models → sim-api).
- Estructura de carpetas propuesta, por ejemplo: `sim/` (redes, demanda, controladores), `rl/` (entorno, recompensa, entrenamiento), `api/` (FastAPI), `web/` (HTML/JS), `eval/` (métricas y figuras), `scenarios/`, `tests/`, `docker/`.
- Hitos con criterio de "terminado" y test que lo demuestra:
  - **H0 (hoy):** workspace, Docker y hooks funcionando.
  - **H1 Demo (29 oct):** zona real de Cali con 4 intersecciones semaforizadas (desde OSM), demanda pico con motos, tiempo fijo y max-pressure, PPO corto (30–60 min), FastAPI + mapa Leaflet con vehículos y semáforos en vivo, botón "accidente", selector de estrategia, 2 gráficas.
  - **H2 (2 nov):** corredor completo de Cali (6 a 9 intersecciones), revisado en netedit, peatones, 3 escenarios, mapa completo.
  - **H3 (9 nov):** entrenamiento MARL independiente y coordinado (α = 0 vs 0,3), ajuste de recompensa.
  - **H4 (16 nov):** evaluación 5 semillas, tablas, figuras, panel final, README.
- Riesgos y plan B (entrenamiento lento → libsumo, episodios cortos; red OSM con errores → limpiar en netedit o tomar una zona de Cali más pequeña; la 2×2 sintética solo como último recurso; peatones lentos → solo en evaluación; agente no supera la base → simplificar recompensa).
- Preguntas abiertas que necesites que yo responda (por ejemplo, la zona exacta de Cali).

**Detente aquí y espera mi aprobación del plan.**

## 4. FASE 2 · EJECUCIÓN (hito por hito)

- Trabaja un hito a la vez, en una rama `feat/h<n>-...`, con commits pequeños.
- Prioridad absoluta: **H1, la demo del jueves**. Si algo se complica, usa el plan B (gráficas generadas por el contenedor) antes que perder la demo.
- Para entrenamientos largos, deja el proceso corriendo en segundo plano en el contenedor `trainer` y sigue con otra tarea.
- Interacciones del panel que deben existir al final: seleccionar estrategia, provocar accidente (bloquear carril con TraCI), cambiar a hora pico (escalar demanda), pausar/reanudar, velocidad de simulación, comparación lado a lado y semáforos con su fase en el mapa.
- Al terminar cada hito: resumen corto de lo hecho, cómo probarlo y qué sigue. Espera mi visto bueno antes del siguiente hito.

## 5. FASE 3 · TEST (en cada hito y al final)

- **Unitarios (pytest):** generación de red y rutas, controladores de tiempo fijo y max-pressure, cálculo de métricas (incluido Jain), forma de observación y recompensa del entorno.
- **Integración:** `docker compose up` sano (healthchecks), endpoint `/health`, el WebSocket entrega estados con vehículos y semáforos, el botón de accidente cambia el estado del carril.
- **Humo de simulación:** 300 pasos de cada estrategia en el contenedor sin errores.
- **Humo de entrenamiento:** PPO con 1000 timesteps termina y guarda un modelo cargable (marcado `slow`).
- **End-to-end de la web (Playwright):** la página carga, el mapa muestra vehículos que se mueven, los controles responden y las gráficas se actualizan.
- **Resultados:** la evaluación final debe verificar el objetivo de ≥ 15 % de reducción de espera; si no se cumple, repórtalo con los números reales, sin maquillarlos.
- El subagente `test-reviewer` revisa cada hito antes de darlo por terminado.

## 6. Reglas generales

- No inventes resultados ni métricas: todo número sale de una ejecución real.
- No instales nada en el host fuera de Docker (salvo lo que Claude Code necesite para sí mismo).
- Pregúntame antes de: borrar archivos, cambiar el stack, añadir servicios externos o hacer push.
- Mantén `PLAN.md` actualizado con el estado de cada hito.

Empieza ahora por la sección 2 (workspace) y luego entrega la FASE 1.
