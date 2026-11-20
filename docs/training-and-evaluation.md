# Entrenamiento, evaluación y reproducibilidad

Guía de la implementación del 18 de noviembre de 2026. Los comandos se ejecutan
desde WSL, en `/home/milton/Gemelo_digital_cali`, con Docker activo. La copia de
Windows en `/mnt/c/Users/mquui/Gemelo_digital_cali` es otra carpeta: no contiene
necesariamente los mismos cambios ni modelos.

## Preparación sin instalar Python ni SUMO en el host

```bash
cd /home/milton/Gemelo_digital_cali
export UID
export GID=$(id -g)
docker compose build sim-api
docker compose run --rm --no-deps sim-api python -m sim.demand --dataset --missing-only
docker compose --profile train run --rm -e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2 trainer \
  pytest -q tests/smoke/test_train_smoke.py
```

`--missing-only` conserva las rutas existentes y genera las que falten. Úselo
cuando haya un entrenamiento activo; regenerar archivos que ese proceso está
leyendo puede causar errores. Sin esa opción se reconstruye todo el dataset.
`make` es opcional: los comandos de esta guía funcionan sin él.

## Qué aprende el modelo

Un agente por semáforo; una política PPO compartida. Cada 5 s simulados decide
mantener o avanzar el verde, respetando el programa cíclico, amarillos y despejes.
La observación incluye fases, densidad y colas locales y colas de vecinas.
La recompensa mezcla cambio de espera y presión; `alpha` agrega recompensa vecina.

- `--alpha 0`: recompensa local; **la observación sigue incluyendo vecinas**.
  Por eso esta comparación aísla la cooperación en la recompensa, no elimina
  toda información compartida.
- `--alpha 0.3`: añade la media ponderada de recompensas vecinas.
- `--scenarios peak valley event`: cada episodio sortea un archivo de estos
  escenarios. Hay igual cantidad de archivos por escenario, no por volumen de tráfico.
- Un episodio `event` aplica el cierre de `.event.json`: carril solo para
  `authority`, velocidad 1 m/s; después restaura permisos y velocidad.
  `event` y `peak` pueden tener las mismas rutas: la diferencia es el cierre.

El entrenamiento sigue usando demanda sintética. No equivale a entrenar con
aforos reales. Véase [Calibración](calibration.md).

## Separación de datos

| Uso | Semillas de demanda | Escenarios | Archivos |
|---|---|---|---|
| Entrenamiento | 100–119 | pico, valle, evento | 60 |
| Validación | 200–204 | pico, valle, evento | 15 |
| Prueba final | 300–304 | pico, valle, evento | 15 |
| Histórico (`legacy`) | 0–4 | pico, valle, evento | 15 |

`manifest.csv` identifica cada archivo, split y conteos. Los modelos antiguos
ya se compararon con 0–4: esos resultados no son una prueba final independiente.
Las filas históricas conservan la etiqueta `eval` en el manifest; el CLI las
selecciona con `--split legacy`.
La semilla de entrenamiento `--seed` controla PPO/SUMO y el sorteo de rutas;
es distinta de las semillas que identifican los archivos del dataset.

Use validación para elegir parámetros. Fije el modelo y sus parámetros antes
de ejecutar la prueba final. Si vuelve a ajustar después de ver esa prueba,
ya no puede presentar sus semillas como no utilizadas para selección.

## Entrenar y validar automáticamente

```bash
docker compose --profile train run -d --name train_mixed_a0_s0 \
  -e GIT_COMMIT="$(git rev-parse --short HEAD)" \
  -e GIT_DIRTY="$(git status --porcelain --untracked-files=no | wc -l)" \
  -e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2 trainer \
  python -m rl.train --alpha 0 --seed 0 --timesteps 3000000 --n-envs 2 \
  --episode-seconds 3600 --scenarios peak valley event

docker logs -f train_mixed_a0_s0
docker compose --profile train up -d tensorboard
```

El nombre del contenedor debe ser único. TensorBoard está en
`http://localhost:6006`. Mantenga Windows encendido y WSL activo.
Al terminar, el CLI valida automáticamente contra fijo y max-pressure en
los tres escenarios, con semillas 200–204. `--skip-evaluation` omite esa etapa;
`--eval-workers 2` controla su paralelismo. La función Python `train()` solo
entrena; la automatización pertenece al CLI y al módulo de experimentos.

Para verificar el pipeline con bajo presupuesto se puede usar `--out-root
models/verification --eval-seconds 300 --eval-seeds 200`. El reporte se marca como
comprobación parcial; no acredita el objetivo del 15 %. `--eval-out` permite
elegir una carpeta nueva para el reporte. Estas opciones no cambian el protocolo
de validación por defecto (5 semillas × 3600 s).

Las corridas iniciadas antes de esta mejora no adquieren evaluación automática
por editar el código. Para una de ellas:

```bash
bash scripts/watch_training.sh NOMBRE_CONTENEDOR models/NOMBRE_MODELO --allow-legacy
```

El script espera el contenedor y solo evalúa si termina con código 0.
`--allow-legacy` reconoce que un modelo antiguo no tiene huella de red; no demuestra
que sea compatible. Debe auditarse la red usada al entrenarlo.

## Reanudar un checkpoint

```bash
docker compose --profile train run -d --name train_resumed \
  -e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2 trainer python -m rl.train \
  --resume models/RUN_ORIGINAL/checkpoints/ppo_100000_steps.zip \
  --alpha 0 --seed 0 --n-envs 2 --scenarios peak valley event \
  --timesteps 500000
```

También se acepta `models/RUN_ORIGINAL/model.zip`. Los pasos indicados son
**adicionales**. PPO completa rollouts, por lo que el total real puede superar
ligeramente el solicitado. Se conserva el contador y el estado del optimizador,
y se crea una carpeta nueva; el original no se sobrescribe.

Se verifican red, rutas, tipos de vehículo, evento, alpha, semilla y escenarios.
La configuración se guarda antes del primer checkpoint, de modo que puede
verificarse incluso una corrida interrumpida. Los checkpoints antiguos sin
`config.json` verificable no se pueden reanudar con este flujo.

La reanudación no reproduce exactamente una ejecución sin interrupciones:
reinicia los episodios SUMO, el estado de muestreo y los generadores aleatorios.
No restaura una simulación que estuviera a mitad de episodio.

## Experimento con varias semillas de entrenamiento

Para ejecutar todo el protocolo con instantánea, selección fijada antes del test y
estado recuperable, véase [experimento de cooperación](cooperation-experiment.md).
El lanzador `bash scripts/run_experiment.sh IDENTIFICADOR` ejecuta las seis corridas,
valida, fija un candidato si cumple los criterios y prueba solo ese candidato.

```bash
docker compose --profile train run -d --name experiment_cooperation \
  -e GIT_COMMIT="$(git rev-parse --short HEAD)" \
  -e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2 trainer python -m rl.experiment \
  --alphas 0 0.3 --seeds 0 1 2 --timesteps 3000000 --n-envs 2 \
  --scenarios peak valley event
```

Ejecuta seis entrenamientos secuenciales y después evalúa todos con las mismas
semillas de validación. Consume seis veces el presupuesto de una corrida individual.
Sin `--final-test` se detiene después de seleccionar con validación. El reporte conserva
cada modelo por separado. Para conclusiones sobre alpha, considere la variación
entre semillas de entrenamiento, además de la variación de demanda.

## Evaluación manual y prueba final

```bash
# Validación: selección del modelo
docker compose --profile train run --rm trainer python -m eval.run_all \
  --models models/RUN --split validation --scenarios valley peak event --workers 2

# Prueba final: después de fijar modelo y configuración
docker compose --profile train run --rm trainer python -m eval.run_all \
  --models models/RUN --split test --final-test --scenarios valley peak event --workers 2

# Auditoría de modelos históricos (compatibilidad no verificada)
docker compose --profile train run --rm trainer python -m eval.run_all \
  --models models/RUN_ANTIGUO --split legacy --allow-legacy
```

Se pueden repetir `--models` para comparar varios. `--seeds` acepta solo semillas
del split elegido y sin duplicados. `--seconds 300` sirve para comprobar el
pipeline, pero no sustituye una evaluación de 3600 s ni alcanza necesariamente
el instante del accidente. Cada evaluación usa una carpeta nueva; una carpeta
con `evaluation.json` no se sobrescribe.

## Archivos y lectura de resultados

Entrenamiento: `models/RUN/config.json`, checkpoints y `model.zip`; curvas en
`outputs/tb/`, episodios JSONL en `outputs/traces/training/`.

La configuración registra estado (`initializing`, `training`, `completed`,
`failed`), pasos solicitados y reales, duración, modelo de origen y huellas de:

- red y programas semafóricos;
- rutas de entrenamiento, tipos de vehículo y definición del accidente;
- fuentes Python de `rl/`, `sim/` y `eval/`;
- versiones de Python, Torch, SB3, sumo-rl, libsumo y SuperSuit.

Los XML se leen sin comentarios: una fecha en la cabecera de duarouter no cambia
la huella. No se recopilan archivos de entorno ni claves. Las huellas identifican
los archivos; conserve también el código y los datos para reproducir una corrida.
`git_commit` y `git_dirty` dependen de las variables pasadas por el host, porque
el contenedor no monta `.git`. La lista de huellas refleja incluso fuentes sin commit.

Evaluación: `outputs/evaluations/…/` contiene:

| Archivo | Contenido |
|---|---|
| `evaluation.json` | estado, split, semillas, modelos y huellas de entrada |
| `runs.csv` | una fila por modelo/estrategia, escenario y semilla |
| `summary.csv`, `summary.md` | media y desviación entre semillas de demanda |
| `goal_check.md` | objetivo histórico de 15 % frente a fijo |
| `report.json` | resumen y reducciones frente a fijo y max-pressure, con IC 95 % |
| `fig_mean_wait.png`, `fig_wait_p95.png`, `fig_completed.png` | figuras exportables |
| `tripinfo/` | resultados individuales originales de SUMO |

La reducción empareja estrategias con la misma semilla:
`(espera_referencia − espera_RL) / espera_referencia`. Es positiva cuando mejora.
Si la referencia tiene espera cero, la reducción relativa no está definida.
El bootstrap usa semillas de demanda como unidad; con una sola semilla su
intervalo no aporta evidencia de generalización. El objetivo histórico indica
la mejora media, no una garantía estadística ni que RL supere max-pressure.
Con menos de cinco semillas o episodios menores de 3600 s, `goal_check.md`
informa “COMPROBACIÓN PARCIAL” y no declara cumplimiento.

## Métricas y limitaciones

- Espera media, P95 y máxima por viaje incluyen vehículos sin terminar.
- `completed`: vehículos con llegada registrada. `unfinished`: los que siguen
  circulando al cerrar la simulación.
- `completion_rate`: completados / viajes presentes en tripinfo; **no** divide
  entre todos los viajes programados. Los vehículos que no lograron insertarse
  no están representados. No se debe interpretar como cobertura total de demanda.
- Cola media y máxima se calculan por aproximación (suma de carriles del acceso),
  no por carril individual. Jain usa la espera media por vehículo y acceso.
- `approach_wait_max`: mayor espera media entre los accesos utilizados;
  no es el máximo tiempo continuo en rojo.
- Los teletransportes son una señal de problemas de circulación: una espera
  menor con más teletransportes no demuestra un mejor controlador.
- El P95 es el cuantil empírico con interpolación lineal. El P95 mostrado en
  el resumen es la media de los P95 de cada semilla, no un cuantil agrupado.
- Al cortar a 3600 s hay viajes censurados: su espera posterior se desconoce.
- Hay cruces peatonales en la red, pero el generador actual crea carros y motos;
  no se afirma haber evaluado espera peatonal ni una restricción de rojo máximo.

## Panel y API

`http://localhost:8000` incorpora “Resultados de evaluación”: selector de corrida,
split, semillas, duración, métricas y comparación con ambas referencias.
“Actualizar resultados” consulta reportes completados; no inicia simulaciones.
Se distingue una corrida corta y un modelo antiguo sin compatibilidad verificada.
El CSV se descarga desde el panel.

- `GET /api/evaluations`: lista de reportes completos.
- `GET /api/evaluations/report?run=ID`: resumen de una evaluación.
- `GET /api/evaluations/runs.csv?run=ID`: filas originales.

Tras cambiar código del API hay que reiniciar `sim-api`; editar los archivos no
recarga el servidor automáticamente. No reinicie `trainer` para ver el panel.
Los resultados históricos en `outputs/eval/` se conservan, pero no se convierten
en reportes nuevos ni adquieren métricas que no se calcularon.

## Comprobaciones

```bash
docker compose --profile train run --rm -e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2 trainer \
  pytest -q -m 'not slow'
docker compose --profile train run --rm -e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2 trainer \
  pytest -q tests/smoke/test_train_smoke.py
```

La prueba de humo entrena, guarda y reanuda un modelo y comprueba que avanzan
sus pasos. Las pruebas nuevas cubren particiones de semillas, huellas de red,
incidentes durante entrenamiento, métricas de espera y acceso a reportes.
Las llamadas reales al LLM quedan fuera de estas comprobaciones.
