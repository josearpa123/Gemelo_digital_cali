"""Tracing must not slow the simulation down by more than 5 % (real-time factor)."""

import pytest

from sim.controllers.rl_policy import find_model

pytestmark = pytest.mark.slow


def test_tracing_overhead_is_at_most_5_percent():
    from eval.bench_tracing import NET, ROUTES, bench

    if not (NET.exists() and ROUTES.exists()):
        pytest.skip("run make dataset first")
    strategy = "rl" if find_model() else "fixed"
    result = bench(strategy, steps=1200, reps=7)
    print({k: v for k, v in result.items() if k != "runs"})
    assert result["overhead_pct"] <= 5.0, result["pair_overheads_pct"]
