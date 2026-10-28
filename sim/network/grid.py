"""Synthetic 2x2 grid network. Fallback for tests only; real networks come from Cali OSM."""

import argparse
import subprocess
from pathlib import Path

NETGENERATE_ARGS = [
    "--grid",
    "--grid.number",
    "2",
    "--grid.length",
    "200",
    "--grid.attach-length",
    "200",
    "--default.lanenumber",
    "2",
    "--tls.guess",
    "--sidewalks.guess",
    "--crossings.guess",
    "--no-turnarounds",
]


def build_grid(out_dir: Path, seed: int = 0, end: int = 3600, period: float = 2.0) -> Path:
    """Generate grid2x2.net.xml, random trips and a .sumocfg. Returns the .sumocfg path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    net = out_dir / "grid2x2.net.xml"
    routes = out_dir / "grid2x2.rou.xml"
    cfg = out_dir / "grid2x2.sumocfg"
    subprocess.run(["netgenerate", *NETGENERATE_ARGS, "-o", str(net)], check=True)
    subprocess.run(
        [
            "python",
            "/usr/share/sumo/tools/randomTrips.py",
            "-n",
            str(net),
            "-r",
            str(routes),
            "-o",
            str(out_dir / "grid2x2.trips.xml"),
            "--seed",
            str(seed),
            "-e",
            str(end),
            "-p",
            str(period),
            "--fringe-factor",
            "10",
            "--validate",
        ],
        check=True,
        capture_output=True,
    )
    cfg.write_text(
        f"""<configuration>
    <input>
        <net-file value="{net.name}"/>
        <route-files value="{routes.name}"/>
    </input>
    <time><begin value="0"/><end value="{end}"/></time>
    <processing><time-to-teleport value="300"/></processing>
    <random_number><seed value="{seed}"/></random_number>
</configuration>
"""
    )
    return cfg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("scenarios/grid2x2"))
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    print(build_grid(args.out, seed=args.seed))


if __name__ == "__main__":
    main()
