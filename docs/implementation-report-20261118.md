# Informe de mejoras · 18 de noviembre de 2026

## Alcance y ubicación

Implementación en `/home/milton/Gemelo_digital_cali` dentro de WSL Ubuntu.
Se conservaron los cambios locales previos de red, señales, runner, panel,
README, PLAN y bitácora. La copia de Windows no se sincronizó automáticamente.

## Cambios implementados

| Área | Resultado |
|---|---|
| Entrenamiento | Mezcla configurable de pico, valle y evento; cierre real del carril durante episodios de evento |
| Recuperación | `--resume` desde modelo o checkpoint; configuración disponible antes del primer checkpoint; salida nueva |
| Reproducibilidad | Huellas de red, rutas, vtypes, incidente y fuentes; versiones de dependencias; pasos reales y estado de corrida |
| Compatibilidad | Rechazo de redes diferentes para modelos con huella; modelos antiguos señalados como no verificados |
| Protocolo | Semillas separadas: entrenamiento 100–119, validación 200–204, prueba final 300–304; histórico 0–4 |
| Automatización | Validación al terminar el CLI; script para corridas ya iniciadas; experimento secuencial α=0/0,3 con varias semillas |
| Evaluación | Fijo y max-pressure como referencias; reducciones emparejadas e IC 95 %; P95, máxima, completados y teletransportes |
| Resultados | CSV, Markdown, JSON y figuras exportables; carpetas de evaluación sin sobrescritura |
| Panel | Selector de reportes completos, métricas, referencias, descarga CSV y aviso de comprobaciones parciales |
| Documentación | Guía WSL, protocolo de calibración y plantilla vacía para aforos |

No se cambiaron la recompensa ni la arquitectura neuronal de la corrida larga.
Los cambios de entrenamiento se aplican a procesos nuevos. Tampoco se promovió
un modelo basándose en la recompensa de entrenamiento.

## Evidencia de verificación

| Comprobación | Resultado | Evidencia |
|---|---|---|
| Construcción de Docker | correcta | `outputs/verification/build_20261118.log` |
| Ruff | sin errores | `outputs/verification/ruff_20261118.log` |
| Suite `not slow` | 167 passed, 1 skipped (`live`), 2 deselected | `outputs/verification/pytest_20261118.log` |
| Humo y reanudación desde checkpoint | 1 passed | `outputs/verification/resume_20261118.log` |
| Navegador | 8 comprobaciones, 0 errores JavaScript | `outputs/verification/evaluation-browser.json` |
| Captura del panel | generada desde el navegador real | `outputs/verification/evaluation-panel.png` |
| Pipeline automático | entrenamiento de 2048 pasos y 9 corridas de 300 s | `outputs/evaluations/pipeline_check_20261118/report.json` y `runs.csv` |

El pipeline de comprobación usa una sola semilla de validación (200) y episodios
cortos. Sus resultados están marcados como **COMPROBACIÓN PARCIAL**; no acreditan
el objetivo del 15 %, ni reproducen el accidente programado a partir del segundo
900. La aplicación y restauración del incidente sí se probaron por separado con
un evento corto en `tests/integration/test_training_event.py`.

La prueba omitida requiere una llamada real al proveedor LLM y no se ejecutó.
Las advertencias sobre modelos antiguos sin huella corresponden al
`models/current` existente antes de esta intervención.

## Corrida larga ya iniciada

Contenedor: `train_a0_s0_20261118_203145`.
Modelo esperado: `models/ppo_roosevelt4_a0_s0_20261119-0131/`.
Parámetros originales: 3 millones de pasos, alpha 0, semilla 0, dos entornos,
episodios de 3600 s y entrenamiento en hora pico.

Terminó con código 0: 3.000.320 pasos reales en 2481,9 s. El proceso de
`scripts/watch_training.sh` completó después la validación en valle/pico/evento
con semillas 200–204, frente a fijo y max-pressure: 45 simulaciones de 3600 s.
Log: `outputs/verification/current-validation.log`. Reporte original:
`outputs/evaluations/ppo_roosevelt4_a0_s0_20261119-0131/validation_20261119-021327/`.
Se exportaron los resultados para Git en
[docs/results/validation-20261118](results/validation-20261118/README.md).

Esta corrida precede al registro de huellas y se evalúa con `--allow-legacy`.
La red local se conservó durante esta intervención, pero no se inventa una
huella de entrenamiento retroactiva. Windows debe permanecer encendido, sin
suspensión, y WSL debe seguir activo para que estos procesos terminen.

## Pendientes que requieren más evidencia o datos

- Validación terminada: en pico PPO redujo la espera un 69,9 % frente a fijo y
  un 27,3 % frente a max-pressure; no implica mejora de todas las métricas ni
  validación en campo. Revisar la exportación antes de promover el modelo.
- Ejecutar el experimento de seis entrenamientos para estudiar la variación entre
  semillas y alpha. El comando existe, pero no se lanzó ese presupuesto adicional.
- Reservar las semillas finales hasta congelar la elección del modelo.
- Recopilar aforos y programas semafóricos reales, calibrar y validar en días
  independientes. La plantilla preparada no contiene mediciones reales.
- Generar demanda peatonal y medir su espera antes de afirmar resultados sobre
  peatones. El sistema no garantiza un límite máximo de rojo por persona.
- Valorar censura de viajes al cortar la simulación y vehículos aún no insertados:
  la tasa de completitud actual se calcula sobre viajes presentes en tripinfo.

Comandos y límites: [guía de entrenamiento](training-and-evaluation.md).
Datos de campo: [calibración](calibration.md).
