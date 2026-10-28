---
name: run-demo
description: Levanta el sistema completo con docker compose y verifica la demo de punta a punta (salud de servicios, WebSocket con vehículos y semáforos, accidente, selector de estrategia, mapa en el navegador). Úsala antes de cada demo o al cerrar un hito.
---

# Demo de punta a punta

```bash
make demo        # = docker compose up -d --build sim-api web && make demo-check
```

## Checklist automática (`make demo-check`)
1. `docker compose ps`: `sim-api` y `web` en `running (healthy)`.
2. `curl -fsS localhost:8000/health` → `{"status":"ok", "sumo": "...", "scenario": ...}`.
3. `curl -fsS localhost:8080/` sirve el panel; `localhost:8080/api/network` devuelve GeoJSON dentro del bbox de Cali.
4. WebSocket `ws://localhost:8080/ws/state`: en 5 s llegan estados con `vehicles` no vacío y `tls` con 4+ semáforos.
5. `POST /api/control {"action":"accident"}` → el carril afectado aparece en `events` y su `allowed` cambia.
6. `POST /api/control {"action":"strategy","value":"maxpressure"}` → el estado refleja la nueva estrategia.
7. Playwright en contenedor (`make e2e`): la página carga, los marcadores se mueven entre dos capturas, las gráficas tienen datos. Capturas en `outputs/e2e/`.

## Acceso desde otros equipos
- LAN: `http://<IP-del-host>:8080` (en WSL2, la IP de Windows; puede requerir `netsh portproxy` o modo de red espejo).
- Internet: descomentar el servicio `tunnel` (cloudflared) en `docker-compose.yml` — confirmar antes con el equipo.

## Plan B
Si algo falla a menos de 2 h de la demo: `make figures` (gráficas generadas por el contenedor en `outputs/eval/`) + video grabado de respaldo.
