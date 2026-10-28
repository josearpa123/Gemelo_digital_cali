"""Build a georeferenced SUMO network for a Cali zone from OpenStreetMap.

The raw OSM extract is stored next to the network (scenarios/<zone>/osm.xml) so the
network can be rebuilt without depending on Overpass availability.
"""

import argparse
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

import sumolib

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
USER_AGENT = "gemelo-digital-cali/0.1 (academic project)"

# Known zones: download bbox (south, west, north, east) and an optional lon/lat polygon
# passed to --keep-edges.in-geo-boundary to cut a corridor out of the extract.
ZONES = {
    # Av. Roosevelt (OSM "Calle 6", alt_name Avenida Roosevelt) from Cra 34 to Cra 39:
    # 4 signalised junctions (Cra 34, Cra 36, Cra 36A Bis, Cra 39).
    "roosevelt4": {
        "bbox": (3.4195, -76.5445, 3.4300, -76.5365),
        "keep": [
            (-76.538066, 3.429413),
            (-76.541897, 3.420555),
            (-76.544247, 3.421571),
            (-76.540416, 3.430429),
        ],
    },
}

NETCONVERT_ARGS = [
    "--geometry.remove",
    "--roundabouts.guess",
    "--ramps.guess",
    "--junctions.join",
    "--tls.guess-signals",
    "--tls.discard-simple",
    "--tls.join",
    "--tls.default-type",
    "static",
    "--tls.yellow.time",
    "3",
    "--sidewalks.guess",
    "--crossings.guess",
    "--keep-edges.by-vclass",
    "passenger,motorcycle,pedestrian",
    "--remove-edges.isolated",
    "--keep-edges.components",
    "1",
    "--output.street-names",
    "--output.original-names",
    "--no-turnarounds",
]


def download_osm(bbox: tuple[float, float, float, float], out: Path, retries: int = 3) -> Path:
    south, west, north, east = bbox
    query = (
        f"[timeout:90];(way[highway]({south},{west},{north},{east});"
        f"node[highway=traffic_signals]({south},{west},{north},{east}););(._;>;);out meta;"
    )
    data = urllib.parse.urlencode({"data": query}).encode()
    last_error: Exception | None = None
    for attempt in range(retries):
        for url in OVERPASS_URLS:
            request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    body = response.read()
                if body.lstrip().startswith(b"<?xml"):
                    out.write_bytes(body)
                    return out
            except OSError as error:
                last_error = error
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Overpass unavailable for bbox {bbox}: {last_error}")


def build_network(zone: str, out_root: Path) -> Path:
    spec = ZONES[zone]
    out_dir = out_root / zone
    out_dir.mkdir(parents=True, exist_ok=True)
    osm = out_dir / "osm.xml"
    if not osm.exists():
        download_osm(spec["bbox"], osm)
    net = out_dir / f"{zone}.net.xml"
    extra = []
    if "keep" in spec:
        polygon = ",".join(f"{lon},{lat}" for lon, lat in spec["keep"])
        extra = ["--keep-edges.in-geo-boundary", polygon]
    subprocess.run(
        ["netconvert", "--osm-files", str(osm), "-o", str(net), *NETCONVERT_ARGS, *extra],
        check=True,
    )
    return net


def describe(net_file: Path) -> dict:
    net = sumolib.net.readNet(str(net_file), withPedestrianConnections=True)
    tls = net.getTrafficLights()
    return {
        "tls": len(tls),
        "tls_lonlat": [net.convertXY2LonLat(*_tls_center(t)) for t in tls],
        "edges": len(net.getEdges()),
        "georeferenced": bool(net.getLocationOffset() is not None and net.hasGeoProj()),
    }


def _tls_center(tls) -> tuple[float, float]:
    nodes = {conn[0].getEdge().getToNode() for conn in tls.getConnections()}
    xs = [n.getCoord()[0] for n in nodes]
    ys = [n.getCoord()[1] for n in nodes]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zone", default="roosevelt4", choices=sorted(ZONES))
    parser.add_argument("--out", type=Path, default=Path("scenarios"))
    args = parser.parse_args()
    net = build_network(args.zone, args.out)
    print(net, describe(net))


if __name__ == "__main__":
    main()
