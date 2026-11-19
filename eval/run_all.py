"""Compare strategies on validation, final-test or historical demand seeds.

Each (strategy, scenario, seed) runs one SUMO episode in its own process with
--tripinfo-output under outputs/evaluations/, samples approach queues every step and writes
CSV/Markdown/JSON reports and figures (RL vs fixed and max-pressure).

  python -m eval.run_all --models models/ppo_a --split validation --scenarios valley peak event
"""

import argparse
import csv
import json
import math
import multiprocessing
import random
import statistics
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from sim.artifacts import capture_inputs, verify_model_network
from sim.demand import FLOWS, SPLIT_SEEDS, route_path

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
    if scenario == "event" and event is None:
        raise ValueError("event evaluation requires a .event.json file")

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


METRICS = [
    "mean_wait",
    "wait_p95",
    "wait_max",
    "mean_travel_time",
    "queue_mean",
    "queue_max",
    "jain_wait",
    "approach_wait_max",
    "completed",
    "unfinished",
    "completion_rate",
    "teleports",
]


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
        "| Escenario | Estrategia | n | " + " | ".join(METRICS) + " |",
        "|" + "---|" * (3 + len(METRICS)),
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


def goal_check(rows: list[dict], scenario: str = "peak", *, full_duration: bool = True) -> str:
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
            if (strategy, s) in by and by[("fixed", s)] > 0
        ]
        if not reds:
            continue
        lo, hi = bootstrap_ci(reds)
        mean = statistics.fmean(reds)
        verdict = "CUMPLE" if mean >= GOAL else "NO CUMPLE"
        if len(reds) < 5 or not full_duration:
            verdict = "COMPROBACIÓN PARCIAL"
        lines.append(
            f"| {strategy} | {len(reds)} | {mean:+.1%} | [{lo:+.1%}, {hi:+.1%}] | {verdict} |"
        )
    return "\n".join(lines) + "\n"


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def comparisons(rows: list[dict]) -> list[dict]:
    """Paired reductions against both baselines; nonpositive baselines are undefined."""
    results = []
    for scenario in sorted({r["scenario"] for r in rows}):
        by = {(r["strategy"], r["seed"]): r for r in rows if r["scenario"] == scenario}
        for baseline in ("fixed", "maxpressure"):
            for strategy in sorted({st for st, _ in by if st.startswith("rl:")}):
                pairs = [
                    (base, by[(strategy, seed)])
                    for (st, seed), base in by.items()
                    if st == baseline and (strategy, seed) in by
                ]
                reductions = [
                    (a["mean_wait"] - b["mean_wait"]) / a["mean_wait"]
                    for a, b in pairs
                    if a["mean_wait"] > 0
                ]
                lo, hi = bootstrap_ci(reductions) if reductions else (None, None)
                results.append(
                    {
                        "scenario": scenario,
                        "strategy": strategy,
                        "baseline": baseline,
                        "n": len(reductions),
                        "wait_reduction": statistics.fmean(reductions) if reductions else None,
                        "ci95_low": lo,
                        "ci95_high": hi,
                        "completed_delta": statistics.fmean(
                            b["completed"] - a["completed"] for a, b in pairs
                        )
                        if pairs
                        else None,
                        "teleports_delta": statistics.fmean(
                            b["teleports"] - a["teleports"] for a, b in pairs
                        )
                        if pairs
                        else None,
                    }
                )
    return results


def json_safe(value):
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return None if isinstance(value, float) and not math.isfinite(value) else value


def run_evaluation(
    *,
    net=NET,
    models=(),
    scenarios=("peak",),
    split="validation",
    seeds=None,
    seconds=3600,
    workers=2,
    out=None,
    strategies=("fixed", "maxpressure"),
    allow_legacy=False,
) -> Path:
    if split not in SPLIT_SEEDS:
        raise ValueError("split must be validation, test or legacy")
    seeds = list(SPLIT_SEEDS[split]) if seeds is None else list(seeds)
    if not seeds or len(set(seeds)) != len(seeds) or not set(seeds) <= set(SPLIT_SEEDS[split]):
        raise ValueError(f"seeds must be unique and belong to split {split}")
    if (
        seconds <= 0
        or workers <= 0
        or not scenarios
        or len(set(scenarios)) != len(scenarios)
        or not set(scenarios) <= set(FLOWS)
    ):
        raise ValueError("invalid scenarios, seconds or workers")
    if (
        not strategies
        or len(set(strategies)) != len(strategies)
        or not set(strategies) <= {"fixed", "maxpressure"}
    ):
        raise ValueError("baseline strategies must be fixed and/or maxpressure")
    models = [Path(m) for m in models]
    if len({m.name for m in models}) != len(models):
        raise ValueError("model directories must have distinct names")
    routes = [route_path(net, sc, s) for sc in scenarios for s in seeds]
    for route in routes:
        if not route.exists():
            raise FileNotFoundError(f"{route}: generate the dataset first")
    compatibility = {}
    for model in models:
        if not (model / "model.zip").exists():
            raise FileNotFoundError(model / "model.zip")
        compatibility[model.name] = verify_model_network(
            model / "model.zip", net, allow_legacy=allow_legacy
        )
    stamp = datetime.now(UTC).strftime("eval_%Y%m%d-%H%M%S-%f")
    out = Path(out) if out is not None else Path("outputs/evaluations") / stamp
    out.mkdir(parents=True, exist_ok=True)
    if (out / "evaluation.json").exists():
        raise FileExistsError(f"{out}: use a new evaluation output directory")
    metadata = {
        "schema_version": 1,
        "status": "running",
        "split": split,
        "seeds": seeds,
        "scenarios": list(scenarios),
        "seconds": seconds,
        "started_utc": datetime.now(UTC).isoformat(),
        "models": [str(m) for m in models],
        "compatibility": compatibility,
        "provenance": capture_inputs(net, routes),
    }
    meta_path = out / "evaluation.json"
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    selected = [(s, None) for s in strategies]
    selected += [(strategy_name(m), m / "model.zip") for m in models]
    jobs = [
        {
            "net": str(net),
            "scenario": sc,
            "seed": seed,
            "strategy": st,
            "model": str(model) if model else None,
            "seconds": seconds,
            "out": str(out),
        }
        for sc in scenarios
        for seed in seeds
        for st, model in selected
    ]
    try:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(run_one, jobs))
        write_csv(out / "runs.csv", rows)
        summary = summarize(rows)
        write_csv(out / "summary.csv", summary)
        (out / "summary.md").write_text(summary_markdown(summary), encoding="utf-8")
        report = "\n".join(goal_check(rows, sc, full_duration=seconds >= 3600) for sc in scenarios)
        (out / "goal_check.md").write_text(report, encoding="utf-8")
        from eval.figures import plot_summary

        plot_summary(summary, out)
        metadata["status"] = "completed"
        payload = json_safe(metadata | {"summary": summary, "comparisons": comparisons(rows)})
        temporary = out / "report.json.tmp"
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
        temporary.replace(out / "report.json")
        print(summary_markdown(summary), flush=True)
        print(report, flush=True)
    except BaseException as exc:
        metadata.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return out


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
    parser.add_argument("--split", choices=list(SPLIT_SEEDS), default="validation")
    parser.add_argument("--final-test", action="store_true", help="confirm frozen-model final test")
    parser.add_argument("--allow-legacy", action="store_true")
    parser.add_argument("--seeds", nargs="+", type=int)
    parser.add_argument("--seconds", type=int, default=3600)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.split == "test" and not args.final_test:
        parser.error("final test requires --final-test; freeze model selection first")
    run_evaluation(
        net=args.net,
        models=args.models,
        scenarios=args.scenarios,
        split=args.split,
        seeds=args.seeds,
        seconds=args.seconds,
        workers=args.workers,
        out=args.out,
        strategies=args.strategies,
        allow_legacy=args.allow_legacy,
    )


if __name__ == "__main__":
    main()
