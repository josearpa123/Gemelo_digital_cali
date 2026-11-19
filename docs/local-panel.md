# Panel local: modelo seleccionado y acceso directo

## Modelo activado el 19 de noviembre de 2026

En la copia de WSL `/home/milton/Gemelo_digital_cali`, `models/current` apunta a
`ppo_roosevelt4_a0_s0_20261119-0131`. Se comprobó que el artefacto carga con SB3
y contiene **3.000.320 pasos reales**, alpha 0 y control de señal cíclico.
El modelo anterior `ppo_roosevelt4_a0_s0_20261029-1805` permanece disponible.

El panel muestra el identificador real, pasos guardados, alpha y tipo de señal
debajo del selector de estrategias. “Modelo en uso” aparece cuando la estrategia
es RL; con otra estrategia indica “Modelo listo para agentes RL”. La información
proviene de `GET /api/strategies`, campo `strategies[].model`.

Los pasos se leen del metadato JSON del ZIP de SB3, sin deserializar la política
para dibujar la tarjeta. Así se muestra el total real aunque PPO haya completado
un rollout adicional respecto de los pasos solicitados.

La activación no reentrena ni cambia los resultados de evaluación. Véanse las
[métricas y límites de validación](results/validation-20261118/README.md), incluida
la ausencia de huella de entrenamiento en esta corrida anterior al nuevo registro.
El modelo binario y el enlace `current` son artefactos locales, excluidos de Git.

## Acceso directo de Windows

Se instaló **Gemelo digital Cali** en el escritorio del usuario. Un doble clic:

1. Inicia la distribución WSL Ubuntu.
2. Espera que Docker responda y levanta `sim-api` sin reconstruir la imagen.
3. Espera que `/health` responda desde **Windows**, no solo desde Linux.
4. Abre el navegador predeterminado en el puerto publicado por Docker.
5. Mantiene abierta la sesión WSL siguiendo los logs del panel.

**Deje la ventana de inicio abierta mientras usa el panel.** Cerrar el navegador
no la cierra. Ctrl+C termina el seguimiento, sin borrar modelos ni resultados;
si no quedan sesiones activas, WSL puede apagarse. Después de reiniciar Windows,
vuelva a abrir el acceso directo.

El acceso no configura arranque automático de Windows, no modifica el firewall
ni instala servicios. Usa la configuración local existente. Si el API tuvo que
arrancar de cero, conserva el comportamiento inicial de tiempo fijo: pulse
“Agentes RL (PPO)” para utilizar el modelo seleccionado.

## Reinstalar o cambiar la ruta

Ejecutar en Windows PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu\home\milton\Gemelo_digital_cali\scripts\install_panel_shortcut.ps1"
```

Los parámetros `-Distribution` y `-ProjectPath` permiten cambiar Ubuntu o la ruta
Linux. Esta versión del instalador acepta nombres y rutas sin espacios ni
caracteres especiales. La política de ejecución solo se ajusta para ese proceso;
no se cambia la configuración global de PowerShell.

Archivos involucrados:

- `scripts/install_panel_shortcut.ps1`: crea el `.lnk` en el escritorio real del usuario.
- `scripts/start_panel.sh`: arranca Docker Compose y mantiene WSL activo.
- `scripts/open_panel.ps1`: comprueba la conexión desde Windows y abre el navegador.

Comprobación sin abrir navegador ni mantener una sesión adicional:

```bash
cd /home/milton/Gemelo_digital_cali
bash scripts/start_panel.sh --check
```

Si Docker no responde o el panel no está accesible desde Windows, el lanzador
informa el error; no abre prematuramente una pestaña con conexión rechazada.
En una instalación nueva, construya antes la imagen y genere la demanda según
la [guía de entrenamiento](training-and-evaluation.md).

## Verificación de esta entrega

- Suite rápida: 184 passed, 1 skipped (llamada real al LLM), 2 deselected;
  evidencia en `outputs/verification/panel-20261119-tests.log`.
- Modelo cargado con SB3 y selección real comprobada en Chromium, con cero errores
  JavaScript: `outputs/verification/model-selected-20261119.json` y captura PNG.
- `start_panel.sh --check` comprobó el acceso desde Windows; después se abrió
  el acceso directo real y se verificó que su proceso WSL permanecía activo.
- Sintaxis Bash y PowerShell verificadas; Ruff aprobado para los archivos Python nuevos.

## Recuperar el modelo anterior

Solo si necesita revertir la selección local:

```bash
cd /home/milton/Gemelo_digital_cali
ln -sfn ppo_roosevelt4_a0_s0_20261029-1805 models/current
docker compose restart sim-api
```

El modelo anterior se entrenó con otra versión de la red; este comando permite
revertir el enlace, pero no lo convierte en una política adecuada para la red actual.
