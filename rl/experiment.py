"""Persistent sequential PPO comparison, validation selection and optional frozen final test."""

import argparse
import json
import math
import multiprocessing
from datetime import UTC, datetime
from pathlib import Path

from eval.run_all import run_evaluation
from eval.selection import freeze_selection, verify_frozen_model, write_experiment_report
from rl.train import train
from sim.artifacts import capture_inputs
from sim.demand import SPLIT_SEEDS, route_path, train_routes


def save_state(folder: Path, state: dict) -> None:
    temporary = folder / "experiment.json.tmp"
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(folder / "experiment.json")


def evaluate_stage(folder, state, stage, models, net, workers):
    previous = Path(state[stage]) if state.get(stage) else folder / stage
    if (previous / "report.json").exists():
        report = json.loads((previous / "report.json").read_text())
        if report.get("status") == "completed" and report.get("models") == [str(m) for m in models]:
            return previous
    if previous.exists():
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        previous = folder / f"{stage}_retry_{stamp}"
    state[stage] = str(previous)
    state["status"] = stage
    save_state(folder, state)
    return run_evaluation(
        net=net,
        models=models,
        scenarios=["peak", "valley", "event"],
        split=stage,
        workers=workers,
        out=previous,
    )


def main():
    multiprocessing.set_start_method("spawn", force=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--net", type=Path, default=Path("scenarios/roosevelt4/roosevelt4.net.xml"))
    parser.add_argument("--alphas", nargs="+", type=float, default=[0.0, 0.3])
    parser.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    parser.add_argument("--timesteps", type=int, default=3_000_000)
    parser.add_argument("--n-envs", type=int, default=2)
    parser.add_argument("--eval-workers", type=int, default=2)
    parser.add_argument(
        "--out", type=Path, help="stable experiment folder; reuse to skip completed runs"
    )
    parser.add_argument(
        "--final-test",
        action="store_true",
        help="test only the frozen validation winner; never deploy automatically",
    )
    parser.add_argument(
        "--scenarios",
        nargs="+",
        choices=["peak", "valley", "event"],
        default=["peak", "valley", "event"],
    )
    args = parser.parse_args()
    if (
        not args.alphas
        or len(set(args.alphas)) != len(args.alphas)
        or any(not math.isfinite(alpha) or alpha < 0 for alpha in args.alphas)
        or len(set(args.seeds)) != len(args.seeds)
        or any(seed < 0 for seed in args.seeds)
        or min(args.timesteps, args.n_envs, args.eval_workers) <= 0
    ):
        parser.error("invalid or duplicate alphas/seeds, or nonpositive resource budget")
    routes = train_routes(args.net, tuple(args.scenarios))
    routes += [
        route_path(args.net, scenario, seed)
        for scenario in ("peak", "valley", "event")
        for split in ("validation", "test")
        for seed in SPLIT_SEEDS[split]
    ]
    inputs = capture_inputs(args.net, routes)
    protocol = {
        "alphas": args.alphas,
        "seeds": args.seeds,
        "timesteps": args.timesteps,
        "n_envs": args.n_envs,
        "scenarios": args.scenarios,
        "episode_seconds": 3600,
    }
    stamp = datetime.now(UTC).strftime("experiment_%Y%m%d-%H%M%S-%f")
    folder = args.out or Path("outputs/evaluations") / stamp
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "experiment.json").exists():
        state = json.loads((folder / "experiment.json").read_text())
        if state["protocol"] != protocol or state["inputs"] != inputs:
            raise ValueError("experiment inputs changed; use the original snapshot")
    else:
        state = {
            "schema_version": 1,
            "protocol": protocol,
            "inputs": inputs,
            "started_utc": datetime.now(UTC).isoformat(),
            "status": "initializing",
            "models": [],
            "validation": None,
            "test": None,
        }
    state["final_test_requested"] = state.get("final_test_requested", False) or args.final_test
    save_state(folder, state)
    try:
        for alpha in args.alphas:
            for seed in args.seeds:
                done = next(
                    (r for r in state["models"] if r["alpha"] == alpha and r["seed"] == seed), None
                )
                if done:
                    config = json.loads((Path(done["path"]) / "config.json").read_text())
                    if (
                        config.get("status") != "completed"
                        or not (Path(done["path"]) / "model.zip").exists()
                    ):
                        raise ValueError("completed experiment model is missing or incomplete")
                    continue
                state.update(status="training", current={"alpha": alpha, "seed": seed})
                save_state(folder, state)
                print(
                    f"EXPERIMENT {len(state['models']) + 1}/{len(args.alphas) * len(args.seeds)} "
                    f"alpha={alpha} seed={seed}",
                    flush=True,
                )
                model = train(
                    args.net,
                    args.timesteps,
                    alpha,
                    seed,
                    args.n_envs,
                    3600,
                    scenarios=tuple(args.scenarios),
                )
                state["models"].append({"alpha": alpha, "seed": seed, "path": str(model)})
                save_state(folder, state)
        state["current"] = None
        models = [Path(run["path"]) for run in state["models"]]
        validation = evaluate_stage(
            folder, state, "validation", models, args.net, args.eval_workers
        )
        selection = freeze_selection(validation / "report.json", folder / "selection.json")
        if selection["selected_model"] is None:
            state["status"] = "no_eligible_candidate"
        elif state["final_test_requested"]:
            verify_frozen_model(selection)
            evaluate_stage(
                folder,
                state,
                "test",
                [Path(selection["selected_model"])],
                args.net,
                args.eval_workers,
            )
            verify_frozen_model(selection)
            state["status"] = "completed"
        else:
            state["status"] = "awaiting_final_test"
        state["finished_utc"] = datetime.now(UTC).isoformat()
        save_state(folder, state)
        write_experiment_report(folder, state)
        print(f"EXPERIMENT_REPORT={folder / 'experiment.md'}", flush=True)
    except BaseException as exc:
        state.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        save_state(folder, state)
        raise


if __name__ == "__main__":
    main()
