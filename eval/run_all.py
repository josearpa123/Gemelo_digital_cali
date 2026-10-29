"""Evaluate strategies on the evaluation split (seeds never seen in training).

Each (strategy, scenario, seed) runs one SUMO episode in its own process with
--tripinfo-output under outputs/eval/, samples approach queues every step and writes
runs.csv, summary.csv/.md and goal_check.md (RL vs fixed waiting time in peak, 15 % goal).

  python -m eval.run_all --models models/ppo_a --models models/ppo_b --seeds 0 1 2 3 4
"""

import argparse
import csv
import multiprocessing
import random
import statistics
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from sim.demand import route_path

NET = Path("scenarios/roosevelt4/roosevelt4.net.xml")
OUT = Path("outputs/eval")
GOAL = 0.15


def strategy_name(model: Path | None) -> str:
    return "rl" if model is None else f"rl:{model.name}"


def run_one(job: dict) -> dict:
    import libsumo

    from eval.metrics import approach_metrics, trip_metrics
    from sim.controllers.rl_policy import RLController
    from sim.events import active, load_event
    from sim.runner import SimRunner

    net, scenario, seed, strategy = Path(job["net"]), job["scenario"], job["seed"], job["strategy"]
    out_dir = Path(job["out"]) / "tripinfo"
    out_dir.mkdir(parents=True, exist_ok=True)
    tripinfo = out_dir / f"{strategy.replace(':', '_')}_{scenario}_s{seed}.xml"
    runner = SimRunner(
        net,
        route_path(net, scenario, seed),
        seed=seed,
        sumo_args=["--tripinfo-output", str(tripinfo), "--tripinfo-output.write-unfinished"],
    )
    if job.get("model"):
        model = Path(job["model"])
        runner.strategies[strategy] = lambda: RLController(str(net), model)
    event = load_event(net) if scenario == "event" else None

    runner.start(strategy)
    approaches: dict[str, list[str]] = {}
    for lanes in runner.tls_lanes.values():
        for lane in lanes:
            approaches.setdefault(libsumo.lane.getEdgeID(lane), []).append(lane)
    wait_s = dict.fromkeys(approaches, 0.0)
    vehicles: dict[str, set] = {a: set() for a in approaches}
    queue_sum = dict.fromkeys(approaches, 0)
    queue_max = dict.fromkeys(approaches, 0)
    for _ in range(job["seconds"]):
        t = libsumo.simulation.getTime()
        if event is not None:
            if active(event, t) and runner.accident_lane is None:
                runner.set_accident(True, event["lane"])
            elif not active(event, t) and runner.accident_lane is not None:
                runner.set_accident(False)
        runner.step()
        for edge, lanes in approaches.items():
            halting = sum(libsumo.lane.getLastStepHaltingNumber(lane) for lane in lanes)
            wait_s[edge] += halting
            queue_sum[edge] += halting
            queue_max[edge] = max(queue_max[edge], halting)
            for lane in lanes:
                vehicles[edge].update(libsumo.lane.getLastStepVehicleIDs(lane))
    teleports = runner.teleports
    runner.close()

    row = {"strategy": strategy, "scenario": scenario, "seed": seed, "teleports": teleports}
    row |= trip_metrics(tripinfo)
    row |= approach_metrics(wait_s, vehicles, queue_sum, queue_max, job["seconds"])
    row["tripinfo"] = str(tripinfo)
    print(
        f"{strategy:>28} {scenario:>6} s{seed}  wait {row['mean_wait']:6.1f} s  "
        f"travel {row['mean_travel_time']:6.1f} s  jain {row['jain_wait']:.3f}",
        flush=True,
    )
    return row


METRICS = ["mean_wait", "mean_travel_time", "queue_mean", "queue_max", "jain_wait", "teleports"]


def summarize(rows: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((r["strategy"], r["scenario"]), []).append(r)
    out = []
    for (strategy, scenario), rs in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        item = {"strategy": strategy, "scenario": scenario, "n": len(rs)}
        for m in METRICS:
            xs = [float(r[m]) for r in rs]
            item[f"{m}_mean"] = statistics.fmean(xs)
            item[f"{m}_std"] = statistics.stdev(xs) if len(xs) > 1 else 0.0
        out.append(item)
    return out


def summary_markdown(summary: list[dict]) -> str:
    lines = [
        "| Escenario | Estrategia | n | Espera media (s) | Tiempo de viaje (s) | Cola media | "
        "Cola máx | Jain (espera) | Teletransportes |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in summary:
        cells = [f"{s[f'{m}_mean']:.2f} ± {s[f'{m}_std']:.2f}" for m in METRICS]
        lines.append(
            f"| {s['scenario']} | {s['strategy']} | {s['n']} | " + " | ".join(cells) + " |"
        )
    return "\n".join(lines) + "\n"


def bootstrap_ci(xs: list[float], n: int = 10_000, seed: int = 0) -> tuple[float, float]:
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(xs, k=len(xs))) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def goal_check(rows: list[dict], scenario: str = "peak") -> str:
    by = {
        (r["strategy"], r["seed"]): float(r["mean_wait"]) for r in rows if r["scenario"] == scenario
    }
    seeds = sorted({s for (st, s) in by if st == "fixed"})
    lines = [
        f"# Objetivo: ≥ {GOAL:.0%} menos espera media que tiempo fijo ({scenario})",
        "",
        "Reducción por semilla = (fijo − estrategia) / fijo, sobre la espera media por viaje "
        "(`waitingTime` de tripinfo, incluye vehículos sin terminar). IC 95 % por bootstrap "
        "sobre semillas.",
        "",
        "| Estrategia | Semillas | Reducción media | IC 95 % | Resultado |",
        "|---|---|---|---|---|",
    ]
    for strategy in sorted({st for (st, _) in by if st != "fixed"}):
        reds = [
            (by[("fixed", s)] - by[(strategy, s)]) / by[("fixed", s)]
            for s in seeds
            if (strategy, s) in by
        ]
        if not reds:
            continue
        lo, hi = bootstrap_ci(reds)
        mean = statistics.fmean(reds)
        verdict = "CUMPLE" if mean >= GOAL else "NO CUMPLE"
        lines.append(
            f"| {strategy} | {len(reds)} | {mean:+.1%} | [{lo:+.1%}, {hi:+.1%}] | {verdict} |"
        )
    return "\n".join(lines) + "\n"


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    multiprocessing.set_start_method("spawn", force=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--net", type=Path, default=NET)
    parser.add_argument(
        "--models",
        type=Path,
        action="append",
        default=[],
        help="trained model dir (with model.zip); repeat for several",
    )
    parser.add_argument("--strategies", nargs="+", default=["fixed", "maxpressure"])
    parser.add_argument("--scenarios", nargs="+", default=["peak"])
    parser.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2, 3, 4])
    parser.add_argument("--seconds", type=int, default=3600)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    strategies = [(s, None) for s in args.strategies]
    strategies += [(strategy_name(m), m / "model.zip") for m in args.models]
    jobs = [
        {
            "net": str(args.net),
            "scenario": sc,
            "seed": seed,
            "strategy": st,
            "model": str(model) if model else None,
            "seconds": args.seconds,
            "out": str(args.out),
        }
        for sc in args.scenarios
        for seed in args.seeds
        for st, model in strategies
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run_one, jobs))

    write_csv(args.out / "runs.csv", rows)
    summary = summarize(rows)
    write_csv(args.out / "summary.csv", summary)
    (args.out / "summary.md").write_text(summary_markdown(summary))
    report = "\n".join(goal_check(rows, sc) for sc in args.scenarios)
    (args.out / "goal_check.md").write_text(report)
    print(summary_markdown(summary))
    print(report)


if __name__ == "__main__":
    main()
