"""Demand scenarios (the training/evaluation dataset) for a Cali network.

Each (scenario, seed) produces one reproducible .rou.xml with cars and motorcycles.
Trips enter and leave through the network border, weighted towards the Av. Roosevelt
corridor and its signalised cross streets, and are routed with duarouter.
Training and evaluation use disjoint seed ranges so the agent is never evaluated on
traffic it was trained on.
"""

import argparse
import csv
import random
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import sumolib

MOTO_SHARE = 0.35
# Vehicles per hour entering the network.
FLOWS = {"peak": 1300, "valley": 550, "event": 1300}
TRAIN_SEEDS = range(100, 120)
EVAL_SEEDS = range(0, 5)

CORRIDOR = "Calle 6"
CROSS_STREETS = {"Carrera 34", "Carrera 36", "Carrera 36A Bis", "Carrera 36C", "Carrera 39"}
WEIGHTS = {"corridor": 8.0, "cross": 2.0, "other": 0.25}

VTYPES = """<additional>
    <vType id="car" vClass="passenger" color="0,172,193"/>
    <vType id="moto" vClass="motorcycle" length="2.2" maxSpeed="22" color="251,140,0"/>
</additional>
"""


def demand_dir(net_file: Path) -> Path:
    return net_file.parent / "demand"


def route_path(net_file: Path, scenario: str, seed: int) -> Path:
    return demand_dir(net_file) / f"{scenario}_s{seed}.rou.xml"


def edge_weight(edge) -> float:
    name = edge.getName()
    if name == CORRIDOR:
        return WEIGHTS["corridor"]
    if name in CROSS_STREETS:
        return WEIGHTS["cross"]
    return WEIGHTS["other"]


def border_edges(net) -> tuple[list, list]:
    """Edges where vehicles can enter (no upstream road) and leave (no downstream road)."""
    usable = [e for e in net.getEdges() if e.allows("passenger") and e.getLength() > 20]
    sources = [e for e in usable if not any(i.allows("passenger") for i in e.getIncoming())]
    sinks = [e for e in usable if not any(o.allows("passenger") for o in e.getOutgoing())]
    return sources, sinks


def write_trips(net_file: Path, trips: Path, scenario: str, seed: int, end: int) -> int:
    net = sumolib.net.readNet(str(net_file))
    sources, sinks = border_edges(net)
    src_w = [edge_weight(e) for e in sources]
    dst_w = [edge_weight(e) for e in sinks]
    rng = random.Random(seed)
    total = round(FLOWS[scenario] * end / 3600)
    departs = sorted(rng.uniform(0, end) for _ in range(total))
    lines = ["<routes>"]
    for i, depart in enumerate(departs):
        src = rng.choices(sources, src_w)[0]
        dst = rng.choices(sinks, dst_w)[0]
        while dst.getFromNode() == src.getToNode() or dst.getToNode() == src.getFromNode():
            dst = rng.choices(sinks, dst_w)[0]
        vtype = "moto" if rng.random() < MOTO_SHARE else "car"
        lines.append(
            f'    <trip id="{i}" type="{vtype}" depart="{depart:.2f}" from="{src.getID()}" '
            f'to="{dst.getID()}" departLane="best" departSpeed="max"/>'
        )
    lines.append("</routes>")
    trips.write_text("\n".join(lines) + "\n")
    return total


def generate(net_file: Path, scenario: str, seed: int, end: int = 3600) -> Path:
    """Generate one routed demand file. Same arguments give the same file."""
    out_dir = demand_dir(net_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    vtypes = out_dir / "vtypes.add.xml"
    vtypes.write_text(VTYPES)
    routes = route_path(net_file, scenario, seed)
    trips = routes.with_name(routes.name.replace(".rou.xml", ".trips.xml"))
    write_trips(net_file, trips, scenario, seed, end)
    subprocess.run(
        [
            "duarouter",
            "-n",
            str(net_file),
            "--route-files",
            str(trips),
            "--additional-files",
            str(vtypes),
            "-o",
            str(routes),
            "--ignore-errors",
            "--repair",
            "--no-step-log",
            "--no-warnings",
            "--seed",
            str(seed),
        ],
        check=True,
        capture_output=True,
    )
    trips.unlink(missing_ok=True)
    for alt in routes.parent.glob(f"{routes.stem}*.alt.xml"):
        alt.unlink()
    return routes


def count_types(routes: Path) -> dict[str, int]:
    counts = {"vehicles": 0, "car": 0, "moto": 0}
    for vehicle in ET.parse(routes).getroot().iter("vehicle"):
        counts["vehicles"] += 1
        vtype = vehicle.get("type", "")
        if vtype in counts:
            counts[vtype] += 1
    return counts


def build_dataset(net_file: Path) -> Path:
    """Training split (peak, seeds 100-119) and evaluation split (all scenarios, seeds 0-4)."""
    rows = []
    jobs = [("train", "peak", s) for s in TRAIN_SEEDS]
    jobs += [("eval", sc, s) for sc in ("valley", "peak", "event") for s in EVAL_SEEDS]
    for split, scenario, seed in jobs:
        routes = generate(net_file, scenario, seed)
        row = {"split": split, "scenario": scenario, "seed": seed, "file": routes.name}
        rows.append(row | count_types(routes))
    manifest = demand_dir(net_file) / "manifest.csv"
    with manifest.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return manifest


def train_routes(net_file: Path) -> list[Path]:
    return [route_path(net_file, "peak", s) for s in TRAIN_SEEDS]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--net", type=Path, default=Path("scenarios/roosevelt4/roosevelt4.net.xml"))
    parser.add_argument("--scenario", choices=sorted(FLOWS))
    parser.add_argument("--seed", type=int)
    parser.add_argument("--dataset", action="store_true", help="generate the full train/eval split")
    args = parser.parse_args()
    if args.dataset:
        print(build_dataset(args.net))
    else:
        routes = generate(args.net, args.scenario, args.seed)
        print(routes, count_types(routes))


if __name__ == "__main__":
    main()
