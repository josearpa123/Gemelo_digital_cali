import json
from pathlib import Path

import pytest

from eval.run_all import comparisons, goal_check, run_evaluation
from sim.artifacts import file_hash, verify_model_network
from sim.demand import EVAL_SEEDS, SPLIT_SEEDS, TRAIN_SEEDS, train_routes


def test_all_seed_partitions_are_disjoint():
    groups = [set(TRAIN_SEEDS), *(set(seeds) for seeds in SPLIT_SEEDS.values())]
    for i, left in enumerate(groups):
        for right in groups[i + 1 :]:
            assert left.isdisjoint(right)
    assert set(EVAL_SEEDS) == set(SPLIT_SEEDS["legacy"])


def test_mixed_training_never_includes_validation_or_test_seeds():
    paths = train_routes(Path("scenarios/z/z.net.xml"), ("peak", "valley", "event"))
    assert len(paths) == 60
    assert all(int(p.stem.split("_s")[1].split(".")[0]) in TRAIN_SEEDS for p in paths)


def test_xml_fingerprint_ignores_generated_comment_timestamp(tmp_path):
    route = tmp_path / "route.xml"
    route.write_text('<routes><!-- generated yesterday --><vehicle id="0"/></routes>')
    first = file_hash(route, xml=True)
    route.write_text('<routes><!-- generated today --><vehicle id="0"/></routes>')
    assert file_hash(route, xml=True) == first
    route.write_text('<routes><vehicle id="1"/></routes>')
    assert file_hash(route, xml=True) != first


def test_loading_model_rejects_a_changed_network(tmp_path):
    net = tmp_path / "net.xml"
    net.write_text('<net><tlLogic id="A"/></net>')
    config = {"provenance": {"network_sha256": file_hash(net, xml=True)}}
    (tmp_path / "config.json").write_text(json.dumps(config))
    model = tmp_path / "model.zip"
    assert verify_model_network(model, net) == "verified"
    net.write_text('<net><tlLogic id="B"/></net>')
    with pytest.raises(ValueError, match="reentrene"):
        verify_model_network(model, net)


def test_legacy_models_require_explicit_evaluation_override(tmp_path):
    with pytest.raises(ValueError, match="allow-legacy"):
        verify_model_network(tmp_path / "model.zip", tmp_path / "net.xml", allow_legacy=False)


def test_evaluation_refuses_test_seeds_in_validation():
    with pytest.raises(ValueError, match="belong to split"):
        run_evaluation(split="validation", seeds=[300])


def test_evaluation_rejects_duplicate_jobs_before_writing_files():
    with pytest.raises(ValueError, match="invalid scenarios"):
        run_evaluation(scenarios=["peak", "peak"])
    with pytest.raises(ValueError, match="baseline strategies"):
        run_evaluation(strategies=["fixed", "fixed"])


def test_partial_evaluation_cannot_claim_the_goal_is_met():
    rows = []
    for seed in range(200, 205):
        rows.extend(
            [
                {"scenario": "peak", "seed": seed, "strategy": "fixed", "mean_wait": 100},
                {"scenario": "peak", "seed": seed, "strategy": "rl:model", "mean_wait": 50},
            ]
        )
    assert "COMPROBACIÓN PARCIAL" in goal_check(rows, full_duration=False)
    assert "| CUMPLE |" in goal_check(rows)
    assert "COMPROBACIÓN PARCIAL" in goal_check(rows[:2])


def test_paired_comparisons_include_both_baselines_and_completion():
    rows = []
    for seed in (200, 201):
        for strategy, wait, completed in [
            ("fixed", 100, 90),
            ("maxpressure", 50, 95),
            ("rl:model", 60, 92),
        ]:
            rows.append(
                {
                    "seed": seed,
                    "strategy": strategy,
                    "scenario": "peak",
                    "mean_wait": wait,
                    "completed": completed,
                    "teleports": 0,
                }
            )
    result = {row["baseline"]: row for row in comparisons(rows)}
    assert result["fixed"]["wait_reduction"] == pytest.approx(0.4)
    assert result["maxpressure"]["wait_reduction"] == pytest.approx(-0.2)
    assert result["maxpressure"]["completed_delta"] == -3


def test_zero_baseline_does_not_crash_or_claim_improvement():
    rows = [
        {"scenario": "peak", "seed": 200, "strategy": "fixed", "mean_wait": 0},
        {"scenario": "peak", "seed": 200, "strategy": "rl:model", "mean_wait": 0},
    ]
    assert "CUMPLE" not in goal_check(rows)
