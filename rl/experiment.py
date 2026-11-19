"""Sequential independent/coordinated PPO runs, evaluated on validation seeds only."""

import argparse
import multiprocessing
from datetime import UTC, datetime
from pathlib import Path

from eval.run_all import run_evaluation
from rl.train import train


def main():
    multiprocessing.set_start_method("spawn", force=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--net", type=Path, default=Path("scenarios/roosevelt4/roosevelt4.net.xml"))
    parser.add_argument("--alphas", nargs="+", type=float, default=[0.0, 0.3])
    parser.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    parser.add_argument("--timesteps", type=int, default=3_000_000)
    parser.add_argument("--n-envs", type=int, default=2)
    parser.add_argument(
        "--scenarios",
        nargs="+",
        choices=["peak", "valley", "event"],
        default=["peak", "valley", "event"],
    )
    args = parser.parse_args()
    models = []
    for alpha in args.alphas:
        for seed in args.seeds:
            models.append(
                train(
                    args.net,
                    args.timesteps,
                    alpha,
                    seed,
                    args.n_envs,
                    3600,
                    scenarios=tuple(args.scenarios),
                )
            )
    stamp = datetime.now(UTC).strftime("experiment_%Y%m%d-%H%M%S")
    run_evaluation(
        net=args.net,
        models=models,
        scenarios=["peak", "valley", "event"],
        split="validation",
        out=Path("outputs/evaluations") / stamp,
    )


if __name__ == "__main__":
    main()
