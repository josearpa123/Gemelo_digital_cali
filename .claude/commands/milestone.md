---
description: Estado del hito actual y siguiente paso concreto
---

Lee `PLAN.md` (línea `**Hito actual:**` y la sección del hito), `git log --oneline -10`, `git branch --show-current` y `docker compose ps`.

Responde en español, en este formato y sin relleno:

1. **Hito actual** y fecha límite (días que faltan respecto a hoy).
2. **Criterios de "terminado"**: tabla con criterio, estado (hecho / en curso / pendiente) y evidencia (test o archivo). Marca "hecho" solo si hay un test o salida real que lo pruebe.
3. **Bloqueos o riesgos** activos y su plan B de `PLAN.md`.
4. **Siguiente paso**: una sola acción concreta, con el comando o archivo a tocar.

Si $ARGUMENTS menciona otro hito (p. ej. `H2`), reporta ese en lugar del actual.
