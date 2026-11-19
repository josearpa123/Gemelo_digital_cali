# Experimento de cooperación PPO · protocolo fijado antes de ejecutar

## Objetivo y presupuesto

Comparar alpha 0 (recompensa local con observación de vecinas) y alpha 0,3
(recompensa coordinada), con semillas de entrenamiento 0, 1 y 2.
Son **seis entrenamientos secuenciales de 3 millones de pasos cada uno**,
dos entornos por corrida y episodios de 3600 s. Cada episodio sortea demanda
de pico, valle o evento del split de entrenamiento 100–119.

Se usan los mismos parámetros PPO, mezcla de escenarios y red en ambas familias.
No se modifica recompensa ni arquitectura a mitad de la comparación. El modelo
actual del panel se conserva durante todo el experimento.

## Iniciar con código y datos congelados

Desde WSL:

```bash
cd /home/milton/Gemelo_digital_cali
bash scripts/run_experiment.sh cooperation_20261119
```

El lanzador crea una instantánea de `rl/`, `sim/`, `eval/`, `scenarios/`,
`config/` y `pyproject.toml`, excluyendo cachés Python. No copia `secrets/`,
archivos de entorno ni modelos anteriores. Registra revisión Git, estado del
árbol e identificador de la imagen. Monta esa instantánea de solo lectura
en el contenedor para que cambios posteriores en la aplicación no alteren
las siguientes corridas ni la evaluación.

El contenedor se llama `experiment_cooperation_20261119`. Usa dos hilos
OMP/MKL y ejecuta una sola corrida a la vez para limitar memoria.
Mantenga Windows encendido, sin suspensión, y WSL activo. El acceso directo
del panel mantiene una sesión WSL mientras su ventana esté abierta.

```bash
docker logs -f experiment_cooperation_20261119
cat outputs/evaluations/cooperation_20261119/experiment.json
```

El estado registra la combinación en curso y los modelos ya completados.
Cada modelo conserva checkpoints y su configuración con huellas de entrada.
Si se interrumpe el proceso, `docker start experiment_cooperation_20261119`
reutiliza la misma imagen, argumentos, instantánea y estado. Omite corridas
completadas; una corrida interrumpida vuelve a empezar conservando sus
checkpoints anteriores. La reanudación de un checkpoint específico sigue
disponible mediante `rl.train --resume`, pero no se realiza automáticamente.

No reutilice un identificador para un experimento distinto. El lanzador no
sobrescribe una instantánea existente ni inicia un contenedor duplicado.

## Validación: comparación con idéntica demanda

Al terminar los seis modelos, se comparan los seis, fijo y max-pressure:
8 estrategias × 3 escenarios × 5 semillas 200–204 = **120 corridas** de 1 h.
Los resultados se guardan en `validation/` bajo la carpeta del experimento,
con CSV, reportes JSON/Markdown y figuras.

`experiment.md` resume el score medio y su desviación entre las tres semillas
de entrenamiento de cada alpha. Esto se distingue de la variación entre las
cinco semillas de demanda. Tres entrenamientos por familia permiten observar
variación; no bastan por sí solos para afirmar una superioridad universal.

## Regla de selección predefinida

Cada candidato debe cumplir, en validación:

1. Reducción media emparejada de espera **≥15 % frente a fijo en pico**.
2. En cada escenario, teletransportes medios no mayores que fijo.
3. En cada escenario, viajes completados medios ≥99 % de fijo.

Entre los candidatos elegibles se minimiza:

`score = media(espera_media_RL / espera_media_fijo)`

Los tres escenarios tienen el mismo peso. Los empates se resuelven por nombre
de estrategia. El índice de Jain, P95 y otras métricas se reportan para mostrar
compromisos, pero no se añaden umbrales después de conocer los resultados.
La prueba usa métricas de simulación; la tasa de completitud sigue excluyendo
vehículos que aún no lograron insertarse, según los límites documentados.

Si ningún candidato es elegible, se registra `no_eligible_candidate` y no se
ejecuta la prueba final. No se relajan los criterios automáticamente.

## Fijar modelo antes de la prueba final

`selection.json` se escribe antes de usar semillas finales. Conserva:

- ranking y motivos de exclusión;
- ruta del único modelo seleccionado;
- SHA-256 del modelo, configuración y reporte de validación;
- fecha de selección y regla utilizada.

El lanzador incluye `--final-test`, autorizado al continuar este protocolo.
Solo el candidato fijado se compara con fijo y max-pressure en semillas
300–304: 3 estrategias × 3 escenarios × 5 semillas = **45 corridas**.
Los hashes del modelo y configuración se verifican antes y después.
El resultado final no cambia el ranking ni inicia una búsqueda de otro candidato.
El módulo puede usarse sin `--final-test` para detenerse en `awaiting_final_test`.

No se modifica `models/current` automáticamente. La decisión de desplegar
otro modelo se toma después de revisar su prueba final y las métricas de equidad.

## Artefactos

Todo queda en `outputs/evaluations/IDENTIFICADOR/`:

| Archivo o carpeta | Contenido |
|---|---|
| `source/` | código y datos congelados para todas las corridas |
| `git-revision.txt`, `git-status.txt`, `image-id.txt` | procedencia del lanzamiento |
| `experiment.json` | protocolo, estado, combinación actual y modelos completados |
| `validation/` | comparación de los seis modelos con ambas referencias |
| `selection.json` | candidato y huellas fijados antes de la prueba final |
| `test/` | prueba independiente del único candidato seleccionado |
| `experiment.md` | comparación por alpha y rutas de evidencia |

Los modelos están bajo `models/ppo_…/`, fuera de Git. Las evaluaciones completas
aparecen en “Resultados de evaluación” del panel al pulsar Actualizar resultados.
Un fallo técnico conserva su estado y no se presenta como evaluación completada;
al reintentar se crea otra carpeta de evaluación, sin sobrescribir la anterior.

## Verificación

`tests/unit/test_experiment_selection.py` cubre exclusión por viajes no completados,
teletransportes, objetivo de pico no alcanzado, rechazo de reportes parciales o finales
para selección, cambio del artefacto después de fijarlo y reinicio sin repetir corridas
completadas ni la prueba final.

La separación de semillas y las huellas de red siguen cubiertas por la suite existente.
Verificación previa: 190 pruebas aprobadas, 1 omitida (LLM real) y 2 deseleccionadas,
en `outputs/verification/cooperation-protocol-20261119-tests.log`; Ruff aprobado.
Los resultados numéricos de este experimento se publican solo al terminar sus corridas.
