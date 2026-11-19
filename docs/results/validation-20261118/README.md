# Validación de PPO · 18 noviembre 2026

Modelo `ppo_roosevelt4_a0_s0_20261119-0131`: alpha 0, semilla de entrenamiento 0,
dos entornos, 3.000.320 pasos reales. Duración de entrenamiento: 2481,9 s
(aproximadamente 41 minutos). Terminó sin errores el 18 nov a las 21:13, hora de Colombia.

Validación en semillas 200–204; tres escenarios, tres estrategias, 3600 s por corrida:
45 simulaciones. Estos son datos de simulación con demanda sintética, no de campo.

| Escenario | Espera fijo (s) | Max-pressure (s) | PPO (s) | Reducción PPO vs fijo | PPO vs max-pressure |
|---|---|---|---|---|---|
| Pico | 63,80 | 26,39 | 19,00 | 69,9 % | 27,3 % |
| Valle | 38,65 | 16,07 | 14,94 | 61,2 % | 6,8 % |
| Evento | 62,46 | 26,82 | 19,33 | 68,9 % | 27,0 % |

Esperas: media entre las cinco semillas. Reducciones: media de reducciones
emparejadas por semilla, por eso no equivalen exactamente al cociente entre
las medias de la tabla. En pico, IC 95 % de la reducción vs fijo: [68,4 %, 72,1 %];
vs max-pressure: [20,2 %, 34,9 %]. No hubo teletransportes en estas 45 corridas.

## Archivos exportados

Se copiaron sin modificar desde
`outputs/evaluations/ppo_roosevelt4_a0_s0_20261119-0131/validation_20261119-021327/`:

- [runs.csv](runs.csv): las 45 corridas y sus métricas.
- [summary.csv](summary.csv): medias y desviaciones.
- [report.json](report.json): configuración, huellas de evaluación, comparaciones e intervalos.
- [goal_check.md](goal_check.md): objetivo del 15 % frente a fijo.
- Figuras: [espera media](fig_mean_wait.png), [P95](fig_wait_p95.png),
  [viajes completados](fig_completed.png).

## Límites de interpretación

Solo una semilla de entrenamiento y alpha 0: no demuestra ventaja de alpha 0,3
ni estabilidad entre entrenamientos. La prueba final 300–304 sigue reservada.
En valle PPO reduce la espera media, pero su Jain de espera (0,653) es menor
que max-pressure (0,771): no mejora todas las métricas.

La corrida comenzó antes de registrar huellas al entrenar. La evaluación conserva
`compatibility: unverified` y se ejecutó con `--allow-legacy`; no se atribuye al
modelo una huella de entrenamiento que no se guardó. Las huellas incluidas en
`report.json` describen la evaluación, no reconstruyen el código del entrenamiento.

El modelo binario y los XML originales de tripinfo permanecen en WSL bajo `models/`
y `outputs/`; esas carpetas están excluidas de Git. El modelo no se promovió
automáticamente a `models/current`.
