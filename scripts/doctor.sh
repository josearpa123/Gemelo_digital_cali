#!/usr/bin/env bash
# Host preflight: checks everything the project needs before `make build/up/test` on a new
# machine. Prints OK / AVISO / FALLO per check and exits 1 if any FALLO.
#   make doctor            (or: bash scripts/doctor.sh)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

fails=0
ok()   { printf 'OK     %s\n' "$1"; }
warn() { printf 'AVISO  %s\n' "$1"; }
fail() { printf 'FALLO  %s\n' "$1"; fails=$((fails + 1)); }

# --- tools ----------------------------------------------------------------------------
if command -v docker >/dev/null; then ok "docker: $(docker --version | cut -d, -f1)"; else fail "docker no instalado"; fi
if docker compose version >/dev/null 2>&1; then
  ok "docker compose v2: $(docker compose version --short)"
else
  fail "falta 'docker compose' (v2)"
fi
if docker info >/dev/null 2>&1; then ok "daemon de Docker activo"; else fail "el daemon de Docker no responde (¿Docker Desktop / servicio apagado? ¿usuario sin grupo docker?)"; fi
command -v make >/dev/null && ok "make" || fail "falta make (sudo apt install make)"
command -v git >/dev/null && ok "git" || fail "falta git"
command -v curl >/dev/null && ok "curl" || warn "falta curl (lo usa make demo-check)"

# --- resources ------------------------------------------------------------------------
if docker info >/dev/null 2>&1; then
  mem_gb=$(( $(docker info --format '{{.MemTotal}}') / 1024 / 1024 / 1024 ))
  if [ "$mem_gb" -ge 6 ]; then ok "memoria para Docker: ${mem_gb} GB"
  else fail "memoria para Docker: ${mem_gb} GB (mínimo 6 GB; entrenar con 2 procesos usa ~3 GB)"; fi
  cpus=$(docker info --format '{{.NCPU}}')
  [ "$cpus" -ge 4 ] && ok "CPUs para Docker: $cpus" || warn "CPUs para Docker: $cpus (usar ENVS=1 o 2 al entrenar)"
fi
free_gb=$(df -Pk . | awk 'NR==2 {print int($4/1024/1024)}')
[ "$free_gb" -ge 10 ] && ok "disco libre: ${free_gb} GB" || fail "disco libre: ${free_gb} GB (las imágenes ocupan ~6 GB)"

# --- repository -----------------------------------------------------------------------
if git rev-parse --git-dir >/dev/null 2>&1; then
  crlf=$(git ls-files --eol | awk '$2 ~ /crlf/ {print $NF}')
  [ -z "$crlf" ] && ok "sin finales de línea CRLF en el checkout" \
    || fail "archivos con CRLF (clonar de nuevo tras .gitattributes o: git add --renormalize .): $(echo $crlf | head -c 200)"
  noexec=$(git ls-files -s -- '*.sh' | awk '$1 != "100755" {print $4}')
  [ -z "$noexec" ] && ok "scripts .sh ejecutables en git" || fail "scripts sin bit de ejecución: $noexec"
fi
for f in docker-compose.yml docker/Dockerfile scenarios/roosevelt4/roosevelt4.net.xml scenarios/roosevelt4/demand/manifest.csv; do
  [ -f "$f" ] && ok "existe $f" || fail "falta $f"
done
case "$(pwd)" in
  /mnt/[a-z]/*) warn "el repo está en el disco de Windows ($(pwd)): Docker en WSL es muy lento ahí; clonar en ~/ dentro de WSL" ;;
esac

# --- permissions: the containers run as $UID:$GID --------------------------------------
uid=$(id -u); gid=$(id -g)
if [ "$uid" != 1000 ] && ! printenv UID >/dev/null; then
  warn "uid=$uid (no es 1000): usar siempre 'make ...' (exporta UID/GID); 'docker compose' a mano necesita UID=$uid GID=$gid"
else
  ok "uid/gid: $uid:$gid"
fi
for d in models outputs scenarios/roosevelt4/demand; do
  mkdir -p "$d" 2>/dev/null
  [ -w "$d" ] && ok "escribible: $d" || fail "sin permiso de escritura: $d (chown -R $uid:$gid $d)"
done

# --- ports ----------------------------------------------------------------------------
for port in 8000 8080; do
  owner=$(docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -E "[:.]$port->" | awk '{print $1}')
  if [ -n "$owner" ]; then
    case "$owner" in gemelo-cali-*) ok "puerto $port: ya lo usa este proyecto ($owner)" ;;
      *) fail "puerto $port ocupado por el contenedor $owner" ;; esac
  elif (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    fail "puerto $port ocupado por otro proceso del host"
  else
    ok "puerto $port libre"
  fi
done

# --- image ----------------------------------------------------------------------------
if docker image inspect gemelo-cali/trainer:dev >/dev/null 2>&1; then
  stale=""
  for req in docker/requirements-sim.txt docker/requirements-train.txt; do
    inside=$(docker run --rm --entrypoint cat gemelo-cali/trainer:dev "/tmp/$(basename "$req")" 2>/dev/null)
    [ "$inside" = "$(cat "$req")" ] || stale="$stale $req"
  done
  [ -z "$stale" ] && ok "imagen gemelo-cali/trainer:dev al día con requirements" \
    || fail "imagen desactualizada respecto a$stale: correr make build"
else
  warn "imagen gemelo-cali/trainer:dev no construida todavía: correr make build"
fi
if ls scenarios/roosevelt4/demand/*.rou.xml >/dev/null 2>&1; then ok "dataset de demanda generado"
else warn "dataset sin generar: correr make dataset"; fi

# --- WSL ------------------------------------------------------------------------------
if grep -qi microsoft /proc/version 2>/dev/null; then
  warn "WSL: la VM se apaga al cerrar todas las terminales y se congela si Windows se queda sin RAM; dejar una terminal abierta mientras entrena (los checkpoints quedan en models/<run>/checkpoints/)"
fi

echo
if [ "$fails" -eq 0 ]; then echo "doctor: todo listo"; else echo "doctor: $fails problema(s)"; fi
exit $(( fails > 0 ))
