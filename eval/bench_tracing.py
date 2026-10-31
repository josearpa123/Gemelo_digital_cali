"""Tracing overhead: real-time factor of the same scenario with and without traces.

Same network, routes, seed and strategy; runs go in pairs (off/on, then on/off, ...) so
machine noise hits both alike. Reported: median of the per-pair overheads and best-of-N.
Result: outputs/bench/tracing.json (python -m eval.bench_tracing)."""

import argparse
import json
import platform
import statistics
import tempfile
import time
from datetime import datetime
from pathlib import Path

import libsumo

from sim.runner import SimRunner
from sim.tracing import NullTracer, Tracer

NET = Path("scenarios/roosevelt4/roosevelt4.net.xml")
ROUTES = Path("scenarios/roosevelt4/demand/peak_s0.rou.xml")
OUT = Path("outputs/bench/tracing.json")


def run_once(strategy: str, steps: int, traced: bool, workdir: Path) -> dict:
    tracer = (
        Tracer(workdir / f"t{time.time_ns()}.db", log_path=workdir / "events.jsonl")
        if traced
        else NullTracer()
    )
    runner = SimRunner(NET, ROUTES, tracer=tracer)
    runner.start(strategy)
    started = time.perf_counter()
    for _ in range(steps):
        runner.step()
    wall = time.perf_counter() - started
    sim_seconds = libsumo.simulation.getTime()
    runner.close()
    tracer.close()
    events = len(tracer.all_events()) if traced else 0
    return {
        "traced": traced,
        "wall_s": round(wall, 3),
        "rtf": round(sim_seconds / wall, 1),
        "events": events,
    }


def bench(strategy: str, steps: int, reps: int) -> dict:
    runs, pairs = [], []
    with tempfile.TemporaryDirectory() as tmp:
        run_once(strategy, min(steps, 200), False, Path(tmp))  # warm-up (imports, caches)
        for i in range(reps):
            # alternate which side goes first so slow drift of the machine cancels out
            order = (False, True) if i % 2 == 0 else (True, False)
            pair = {traced: run_once(strategy, steps, traced, Path(tmp)) for traced in order}
            runs += pair.values()
            pairs.append((pair[False]["rtf"] - pair[True]["rtf"]) / pair[False]["rtf"] * 100)
    off = [r["rtf"] for r in runs if not r["traced"]]
    on = [r["rtf"] for r in runs if r["traced"]]
    return {
        "date": datetime.now().isoformat(timespec="seconds"),
        "host": platform.node(),
        "strategy": strategy,
        "steps": steps,
        "reps": reps,
        "routes": str(ROUTES),
        "rtf_without_traces": statistics.median(off),
        "rtf_with_traces": statistics.median(on),
        # primary figure: median of the per-pair overheads (robust to machine noise)
        "overhead_pct": round(statistics.median(pairs), 2),
        "overhead_best_of_pct": round((max(off) - max(on)) / max(off) * 100, 2),
        "pair_overheads_pct": [round(x, 2) for x in pairs],
        "runs": runs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", default="rl")
    parser.add_argument("--steps", type=int, default=1800)
    parser.add_argument("--reps", type=int, default=7)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    result = bench(args.strategy, args.steps, args.reps)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "runs"}, indent=2))
    print(f"→ {args.out}")


if __name__ == "__main__":
    main()
