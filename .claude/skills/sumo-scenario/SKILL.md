---
name: sumo-scenario
description: Genera un escenario SUMO completo del proyecto (red de Cali desde OSM con andenes y cruces, o cuadrícula de respaldo con netgenerate; demanda valle/pico/evento con carros, motos y peatones; .sumocfg). Úsala cuando haya que crear o regenerar una red, rutas o configuración en scenarios/.
---

# Escenario SUMO

Todo se ejecuta en el contenedor: `docker compose run --rm sim-api ...`. Salida en `scenarios/<zona>/`.

## 1. Red
**Cali desde OSM (por defecto):**
```bash
make scenario ZONE=<zona> BBOX="<sur>,<oeste>,<norte>,<este>"
# equivale a: python -m sim.network.build_osm --zone <zona> --bbox ...
```
Pasos internos:
1. Descarga `scenarios/<zona>/osm.xml` (Overpass con reintentos y espejos; se versiona para reproducibilidad).
2. `netconvert --osm-files osm.xml -o <zona>.net.xml --geometry.remove --roundabouts.guess --ramps.guess --junctions.join --tls.guess-signals --tls.discard-simple --tls.join --tls.default-type static --sidewalks.guess --crossings.guess --output.street-names --output.original-names --keep-edges.by-vclass passenger,motorcycle,pedestrian`
3. Verifica: número de tls en [4, 9] (`sumolib`), `<location>` con `projParameter` (georreferencia), y un nodo convertido a lon/lat dentro del bbox.
4. Si salen tls de más o de menos: ajustar bbox o depurar en netedit (en el host, fuera de Docker) y guardar `<zona>.net.xml`.

**Respaldo sintético (solo tests o si OSM falla):**
`netgenerate --grid --grid.number 2 --grid.length 200 --default.lanenumber 2 --tls.guess --sidewalks.guess --crossings.guess -o scenarios/grid2x2/grid2x2.net.xml`

## 2. Demanda
`python -m sim.demand --zone <zona> --scenario {valley|peak|event} --seed <n>`
- Tipos en `scenarios/vtypes.add.xml`: `car` (passenger), `moto` (motorcycle, ~35 % del flujo en pico, acorde a Cali), `ped`.
- Base con `randomTrips.py --fringe-factor 5 --validate --seed <n>`; periodo `-p` según escenario (valle ≈ 0.4× pico).
- Peatones: `randomTrips.py --pedestrians --max-distance 600`.
- `event`: demanda pico + archivo `<zona>.event.json` con carril, inicio y duración del cierre (lo aplica el runner vía TraCI).

## 3. Config
`<zona>.<escenario>.sumocfg` con `--step-length 1`, `time-to-teleport 300`, salida `tripinfo` y `queue` hacia `outputs/`.

## 4. Verificación obligatoria
```bash
docker compose run --rm sim-api sumo -c scenarios/<zona>/<zona>.peak.sumocfg --end 300 --no-step-log
docker compose run --rm sim-api pytest tests/test_network.py tests/test_demand.py -q
```
