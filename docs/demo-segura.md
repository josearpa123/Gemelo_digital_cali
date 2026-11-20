# Demo segura

## Levantar una instancia dedicada

Desde el árbol de trabajo de seguridad, crea `models/`, `outputs/` y `secrets/` con tu
usuario. Usa una salida nueva para evitar reutilizar trazas históricas. Para habilitar los
botones de fallos en modo local y usar un proveedor simulado, ejecuta:

```bash
DEMO_PORT=18083 DEMO_FAULTS=1 LLM_PROVIDER=fake GROQ_API_KEY= \
  docker compose -p gemelo-demo-seguridad up -d sim-api
```

Abre `http://127.0.0.1:18083`. Los modelos PPO son opcionales para iniciar. Para presentar
esa estrategia, prepara en el árbol de demo solamente un modelo del equipo cuya procedencia
conozcas. Para verificar fallback real por ausencia de credencial, inicia esta instancia con
`LLM_PROVIDER=groq`, clave vacía y un directorio de secretos de demo vacío.

## Dar acceso al profesor

Para acceso desde otro equipo, coloca un proxy TLS de confianza frente al backend, preserva
el encabezado Host público y habilita el reenvío de WebSocket. Conserva la publicación del
backend en loopback cuando proxy y backend estén en el mismo equipo. Configura en el entorno
privado `DEMO_ACCESS=auth`, `DEMO_ORIGIN=https://<dominio-de-demo>` y
`DEMO_OPERATOR_PASSWORD` con una contraseña aleatoria de al menos 16 caracteres.
Configura credenciales distintas para `viewer` o `admin` solo si se necesitan. Comparte
únicamente el acceso de `operator` con el profesor. La pantalla de inicio de sesión envía
las credenciales al mismo origen y el panel recibe una cookie de sesión firmada. Usa un perfil privado del navegador para
operar con otra cuenta. El origen HTTP en loopback sirve para ensayos en el anfitrión.

## Recorrido verificable

1. Abre el mapa y confirma que los vehículos y las gráficas cambian con el tiempo.
2. En **Comando**, escribe «pasa a hora valle». Verifica que la demanda cambia solamente
   después de pulsar **Confirmar acción**. Localiza la traza del asistente.
3. En la instancia aislada, arma **Timeout LLM** y envía una consulta de resumen. Observa
   los reintentos y el fallback en las trazas mientras la simulación sigue activa.
4. Revisa que la cuenta de operador carece de acceso a la gestión de claves. Descarga una
   exportación y verifica que el CSV contiene datos de la demo.

Para detener solo la instancia de demo, ejecuta
`docker compose -p gemelo-demo-seguridad down`. Los artefactos se conservan en su árbol de
trabajo. Para recuperar el entorno original, vuelve a usar su directorio y su proyecto
Compose. Mantén `DEMO_FAULTS=0` en cualquier instalación fuera de la demo dedicada.
