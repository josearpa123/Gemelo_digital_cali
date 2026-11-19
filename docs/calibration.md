# Calibración con datos reales de Cali

Estado: pendiente de aforos y validación de campo. La geometría proviene de OSM;
la demanda sintética y los tiempos de diseño no se presentan como mediciones reales.

## Datos necesarios

Recolectar conteos en intervalos de 15 minutos, por intersección, acceso, giro
y modo (carro, moto, bus, bicicleta, peatón). Registrar fecha, horario local,
ubicación, método de conteo, responsable y observaciones de incidentes.
Se propone el encabezado [traffic-counts.csv](templates/traffic-counts.csv);
está vacío deliberadamente: no contiene aforos inventados.

Para cada controlador real se necesitan ciclo, verdes, amarillos, despejes,
desfase entre intersecciones y variación por horario. También hacen falta
mediciones independientes de tiempo de viaje, colas y espera por acceso.
No se requieren placas, rostros ni otros identificadores personales.

## Procedimiento propuesto

1. Auditar en netedit carriles, giros permitidos, prioridades, accesos y cruces.
   Asociar cada acceso y giro contado a identificadores de SUMO.
2. Verificar cobertura y consistencia de los conteos. No completar datos
   faltantes con ceros: registrar explícitamente los intervalos sin observación.
3. Ajustar flujos de entrada, reparto de giros y proporción de motos con parte
   de las mediciones. Sustituir los pesos de generación genéricos por valores
   documentados; no basta con modificar el volumen total de `FLOWS`.
4. Cargar programas semafóricos observados como referencia de tiempo fijo.
   Conservar la referencia de diseño anterior para auditar el cambio.
5. Contrastar tiempos de viaje y colas simuladas con otros días reservados para
   validación. Definir antes los errores aceptables y reportarlos por acceso.
6. Congelar una versión de red/demanda calibrada, con fuentes y fechas. Regenerar
   los splits, reentrenar y evaluar los controladores sobre esa misma versión.

## Peatones y equidad

El generador actual no crea demanda peatonal. Antes de afirmar resultados sobre
peatones, incorporar sus orígenes/destinos, velocidades y demanda observada, y
medir espera, número de cruces completados y conflictos de señalización.

La equidad vehicular actual se describe con Jain y la peor espera media por
acceso. No equivale a garantizar servicio a cada persona ni un límite máximo
de rojo. Una futura restricción de servicio debe implementarse en el controlador
y probarse también bajo saturación e incidentes.

## Criterio para cerrar esta mejora

Solo se considera calibrado cuando existan datos reales con procedencia,
parámetros ajustados, evaluación independiente y un informe reproducible de
errores. Esta entrega prepara el protocolo y el formato; no implementa un
importador automático ni reemplaza la revisión de campo.
