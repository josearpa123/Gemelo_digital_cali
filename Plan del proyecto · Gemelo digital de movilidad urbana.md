# Plan del proyecto · Gemelo digital de movilidad urbana

Oct 27, 2026 · @Milton

## Objetivos

En 3 semanas (entrega el 17 de noviembre) el proyecto demuestra, en simulación, que semáforos controlados por agentes de RL multiagente reducen la espera frente al tiempo fijo, con una demo navegable lista el jueves 29 de octubre.

**Objetivo general.** Construir un gemelo digital de un corredor vial de Cali en SUMO, donde cada intersección es un agente de aprendizaje por refuerzo que controla su semáforo vía TraCI y se coordina con sus vecinas, y compararlo contra estrategias convencionales en un panel web con mapa.

**Objetivos específicos (medibles).**

1. Modelar una red de 4 a 9 intersecciones semaforizadas (siempre sobre calles reales de Cali desde OpenStreetMap: 4 intersecciones para la demo y el corredor completo después) con carros, motos y peatones.
2. Generar al menos 3 escenarios de demanda: hora valle, hora pico y un evento (cierre de carril por accidente).
3. Implementar 3 estrategias sobre el mismo tráfico: tiempo fijo, adaptativo convencional (actuated de SUMO o max-pressure) y agentes RL multiagente.
4. Entrenar los agentes con recompensa basada en espera y presión, con información de vecinos, y lograr al menos **15 % menos tiempo de espera promedio** que el tiempo fijo en hora pico.
5. Medir las 4 métricas de la propuesta (tiempo de viaje, espera, colas y equidad entre vías) con 5 semillas por escenario.
6. Entregar un panel web con el mapa en vivo, estado de semáforos, botones para inyectar eventos y gráficas comparativas.

**Fuera del alcance en esta fase:** datos reales de sensores, hardware y despliegue en calle.

## Componente de IA

La IA del proyecto es aprendizaje por refuerzo multiagente (MARL): un agente PPO por intersección, con parámetros compartidos, que observa su estado y el de sus vecinas y decide la fase del semáforo cada 5 s.

| Elemento | Definición propuesta |
| --- | --- |
| Agente | Un controlador por semáforo (tls) de SUMO |
| Observación | Fase actual (one-hot), tiempo en fase, densidad y cola por carril de entrada, más colas agregadas de las vecinas |
| Acción | Elegir la siguiente fase verde (discreta); SUMO inserta el amarillo de 3 s; verde mínimo 10 s |
| Recompensa | Menos espera acumulada y menos presión propia, más 0,3 × la misma recompensa de las vecinas |
| Algoritmo | PPO con parámetros compartidos (Stable-Baselines3 + SuperSuit); alternativa más simple: DQN independiente |
| Paso de decisión | Cada 5 s simulados; episodios de 1 hora simulada |

**Coordinación.** Se logra de dos formas que se pueden comparar como experimento: (a) observación ampliada con datos de las vecinas y (b) recompensa compartida con peso α. Comparar α = 0 (independientes) contra α = 0,3 es un resultado concreto para el informe.

**Requisito del curso cubierto.** Hay aprendizaje, no reglas: la política se entrena, se evalúa contra líneas base y se analiza su comportamiento. Si el curso exige más IA, se puede añadir un módulo opcional de predicción de demanda (regresión o LSTM sobre los conteos simulados) o un asistente que explique en lenguaje natural lo que pasa en el panel.

## Stack tecnológico

Todo es Python y código libre: SUMO simula, TraCI lo controla, sumo-rl entrena a los agentes y un servidor FastAPI transmite el estado a un mapa web.

| Capa | Tecnología | Para qué |
| --- | --- | --- |
| Simulador | SUMO 1.2x + netedit | Red vial, vehículos, motos (vClass motorcycle) y peatones |
| Red real | OpenStreetMap → netconvert (o osmWebWizard) | Corredor de Cali con andenes y cruces peatonales |
| Demanda | randomTrips.py, routeSampler, flujos .rou.xml | Hora valle, pico y evento |
| Control | TraCI (visualización) y libsumo (entrenamiento, hasta 8× más rápido) | Leer colas, cambiar fases, inyectar eventos |
| Entorno RL | sumo-rl (Gymnasium / PettingZoo) | Un entorno multiagente listo para SUMO |
| Aprendizaje | Stable-Baselines3 (PPO, DQN) + SuperSuit | Política compartida entre intersecciones |
| Seguimiento | TensorBoard | Curvas de recompensa y espera |
| Backend | FastAPI + WebSocket | Transmitir posiciones y semáforos cada paso |
| Mapa | Leaflet (o MapLibre) sobre OpenStreetMap | Vehículos y semáforos en vivo, coordenadas vía traci.simulation.convertGeo |
| Gráficas | Chart.js | Comparar estrategias en tiempo real |
| Análisis | pandas + matplotlib sobre tripinfo.xml | Tablas y figuras del informe |
| Código | GitHub + Docker Compose (obligatorio) | Mismo entorno para ambos |

### Todo en Docker

Requisito del curso: el proyecto completo arranca con un solo `docker compose up`, sin instalar SUMO ni Python en los equipos.

| Servicio | Imagen base | Qué corre | Puerto |
| --- | --- | --- | --- |
| `sim-api` | Imagen oficial de SUMO (ghcr.io/eclipse-sumo/sumo) + Python | SUMO, TraCI y FastAPI con WebSocket | 8000 |
| `trainer` | La misma imagen + PyTorch CPU y Stable-Baselines3 | Entrenamiento con libsumo, sin GUI | — |
| `web` | nginx:alpine | Página del mapa (Leaflet + Chart.js) | 8080 |
| `tensorboard` | La misma imagen del trainer | Curvas de entrenamiento | 6006 |

- Volúmenes compartidos: `./scenarios` (redes y rutas), `./models` (políticas entrenadas) y `./outputs` (tripinfo y métricas).
- No se usa `sumo-gui` dentro del contenedor (requiere X11); la visualización es el mapa web, que además sirve igual en Windows, Mac y Linux.
- El servicio `trainer` corre por perfil aparte (`docker compose --profile train up trainer`) para no frenar la demo.
- PyTorch en versión CPU mantiene la imagen liviana; si alguien tiene GPU NVIDIA se añade un override con el runtime de GPU.

**Cómo se ve la web:** en el mismo equipo en `http://localhost:8080`; desde otros dispositivos de la misma red en `http://<IP-del-equipo>:8080`; y desde internet, si hace falta, con un túnel temporal (Cloudflare Tunnel o ngrok) como servicio adicional del compose.

## Demo en 2 días (jueves 29 de octubre)

La demo muestra 4 intersecciones reales de Cali en un mapa web, con tráfico en vivo, tiempo fijo contra un controlador adaptativo y un botón que provoca un accidente; el agente RL aparece como primer entrenamiento corto.

**Lo que se verá:** el mapa con vehículos moviéndose, semáforos de colores por intersección, un contador de espera y cola por estrategia, y el efecto del accidente sobre la congestión.

**Día 1 · miércoles 28**

- [ ] Montar el repositorio con Dockerfile y docker-compose.yml (SUMO, sumo-rl, Stable-Baselines3, FastAPI) y verificar en ambos equipos `que SUMO corre` en modo consola dentro del contenedor
- [ ] Extraer de OpenStreetMap una zona de Cali con 4 semáforos (osmWebWizard o netconvert) y limpiarla en netedit; la cuadrícula 2×2 queda solo como respaldo
- [ ] Crear demanda de hora pico con randomTrips.py, incluyendo motos
- [ ] Script TraCI que corre la simulación y registra espera y colas por paso
- [ ] Estrategia 1 tiempo fijo y estrategia 2 actuated o max-pressure
- [ ] Lanzar en segundo plano un PPO corto (unos 30 a 60 min) sobre la 2×2

**Día 2 · jueves 29**

- [ ] Servidor FastAPI que avanza la simulación y envía el estado por WebSocket
- [ ] Página con Leaflet: vehículos como puntos, semáforos coloreados, panel con 2 gráficas
- [ ] Botón "accidente" (bloquea un carril con TraCI) y selector de estrategia
- [ ] Cargar el modelo PPO entrenado como tercera estrategia, aunque aún sea preliminar
- [ ] Ensayar la demo y grabar un video de respaldo de 1 minuto

**Plan B:** si el mapa web no está listo, la demo muestra las gráficas generadas por el contenedor y un video grabado con sumo-gui en un equipo local; el mapa se completa la semana 1.

## Cronograma de 3 semanas

La semana 1 pasa de la demo a la red real de Cali, la semana 2 entrena y coordina los agentes y la semana 3 evalúa y cierra el informe.

&#91;embedded content: cronograma · 3 semanas, demo y entrega\]

- **Semana 1 (27 oct a 2 nov):** demo, red del corredor de Cali con motos y peatones, 3 escenarios, mapa completo.
- **Semana 2 (3 a 9 nov):** entrenamiento independiente y luego coordinado (α = 0 contra α = 0,3), ajuste de recompensa.
- **Semana 3 (10 a 16 nov):** 5 semillas por escenario y estrategia, tablas de métricas, panel final, informe y ensayo.

## Reparto, apoyo de Claude y riesgos

Cada uno lidera un frente y Claude escribe el código base de ambos, para que el equipo dedique su tiempo a probar, ajustar y analizar.

| Frente | Responsable sugerido | Qué incluye |
| --- | --- | --- |
| Simulación y RL | Milton Quintero | Red, demanda, entorno sumo-rl, entrenamiento, recompensa |
| Panel y evaluación | Jose Arias | FastAPI, mapa, eventos, métricas, gráficas del informe |

**Cómo apoya Claude**

- Scripts de red y demanda (netconvert, randomTrips, escenarios con motos y peatones)
- Puente TraCI → FastAPI → WebSocket y la página del mapa con Leaflet
- Interacciones del panel: accidente, cambio de demanda, selector de estrategia, comparación lado a lado
- Entorno multiagente, recompensa con vecinas y script de entrenamiento con PPO
- Controlador max-pressure, cálculo de métricas (incluido el índice de equidad de Jain) y figuras
- Revisión del informe y las diapositivas finales

**Riesgos y respuesta**

| Riesgo | Respuesta |
| --- | --- |
| El entrenamiento tarda demasiado | Usar libsumo, sin GUI, episodios de 1 h y red pequeña; entrenar de noche |
| La red de OSM sale con errores | Limpiarla en netedit o usar una zona más pequeña; la cuadrícula siempre sirve de respaldo |
| Los peatones vuelven lenta la simulación | Activarlos solo en los escenarios de evaluación |
| El agente no supera la línea base | Simplificar la recompensa (solo espera), subir verde mínimo, más pasos de entrenamiento |

**Entregables:** repositorio con código y README, red y escenarios, modelos entrenados, panel web, informe con resultados y presentación final.
