# Arquitectura y capacidad del gemelo

## 1. Ingesta y desacoplamiento

El panel recibe el estado del simulador por WebSocket y consulta artefactos precalculados por
HTTP. El entrenamiento está en un perfil de Docker aparte y entrega artefactos persistentes.
El asistente recibe texto de hasta 500 caracteres y usa contexto tipado. Las mutaciones se
serializan en la API y las llamadas externas no ocupan el trabajador de SUMO.

## 2. Dimensionamiento y concurrencia

Hipótesis para el ejercicio: 10 usuarios con una consulta cada 30 segundos producen
**0,33 solicitudes/s o 20 RPM**. Si cada llamada tarda 1,5 s, la ley de Little da **0,5
solicitudes activas en promedio**. Con 400 tokens de entrada y 200 de salida estimados se
consumirían 12.000 TPM, antes de contar reintentos. La configuración de referencia del
repositorio indica 30 RPM y 8.000 TPM para Groq. Si cada intento reserva 1.600 tokens,
el presupuesto admite hasta 5 intentos por minuto en ese ejemplo. La cuota de tokens y los
picos son el límite; aumentar la concurrencia no los elimina.

El demo permite hasta tres consultas externas en curso y no acumula una cola de espera del
proveedor. Cuando esa capacidad se agota, responde por reglas. Se admiten hasta 24 conexiones
WebSocket en este proceso. Los supuestos anteriores son proyecciones, no medidas de carga
ni garantías de servicio.

## 3. Estrategia de inferencia

Los controles directos, el estado en vivo y los cálculos de evaluación usan código
determinista. El modelo se reserva para explicaciones, resúmenes y propuestas estructuradas.
La demo puede usar un proveedor simulado o el fallback local. Se mantienen separados los
experimentos de entrenamiento por lotes y la inferencia interactiva.

## 4. Resiliencia e idempotencia

Cada intento externo reserva cuota. Se permiten dos reintentos dentro de un plazo total de
ocho segundos. Los fallos repetidos abren temporalmente el circuito. Los controles del
simulador siguen independientes del proveedor. La confirmación tiene identificador de
consumo único y valida sesión y revisión bajo un bloqueo. Ante reinicio se descartan las
propuestas pendientes. El entrenamiento genera sus propios reportes y la API publica
evaluaciones completadas con archivos acotados. Si se distribuye el servicio, habrá que
centralizar cuotas, confirmaciones y la coordinación del estado.

## 5. TCO del escenario

Estimación a precios de referencia registrados en `config/llm_pricing.yaml`. En dos días,
200 llamadas de 400 tokens de entrada y 200 de salida producirían 80.000 y 40.000 tokens
respectivamente. A USD 0,15 y USD 0,60 por millón, el costo equivalente sería **USD 0,036**.
La cifra excluye reintentos y es una proyección. En un host existente, el costo marginal de
CPU, memoria, disco, mapas y red requiere medir utilización y aplicar la tarifa institucional.
Para otro host, TCO = horas de cómputo × tarifa + almacenamiento + salida de red + inferencia.
Los precios de referencia documentados no equivalen a una cotización de facturación.

## Pitch de tres minutos

- 0–60 s. Mostrar el flujo del gemelo y explicar por qué el límite determinante es TPM.
- 60–120 s. Navegar el panel, la propuesta con confirmación y el manejo de estado compartido.
- 120–180 s. Demostrar el fallback con el proveedor simulado y presentar reservas, idempotencia y costo.

La [evaluación histórica de PPO](results/validation-20261118/goal_check.md) reporta 69,9 %
menos espera media en pico frente a tiempo fijo en cinco semillas. Para verificar la rama de
seguridad se entrenó un PPO corto de 2.048 pasos en Docker y se evaluaron las tres estrategias
en tres escenarios con cinco semillas. Ese modelo de verificación redujo la espera media en
pico en **43,1 %** frente a tiempo fijo, con IC 95 % de **39,0 % a 48,3 %**. El reporte local
queda en `outputs/evaluations/ppo_roosevelt4_a0_s0_20261119-040357-242472/validation/`.
