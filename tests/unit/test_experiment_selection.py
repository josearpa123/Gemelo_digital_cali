import json

import pytest

from eval.selection import freeze_selection, select_candidate, verify_frozen_model


def validation_report(models):
    summary, comparisons = [], []
    for scenario in ("peak", "valley", "event"):
        for strategy in ["fixed", *(f"rl:{model.rsplit('/', 1)[-1]}" for model in models)]:
            summary.append(
                {
                    "strategy": strategy,
                    "scenario": scenario,
                    "n": 5,
                    "mean_wait_mean": 100 if strategy == "fixed" else 40,
                    "completed_mean": 100,
                    "teleports_mean": 0,
                    "jain_wait_mean": 0.7,
                }
            )
            if strategy != "fixed":
                comparisons.append(
                    {
                        "strategy": strategy,
                        "scenario": scenario,
                        "baseline": "fixed",
                        "n": 5,
                        "wait_reduction": 0.6,
                    }
                )
    return {
        "status": "completed",
        "split": "validation",
        "seconds": 3600,
        "seeds": list(range(200, 205)),
        "scenarios": ["peak", "valley", "event"],
        "models": models,
        "summary": summary,
        "comparisons": comparisons,
    }


def test_faster_policy_is_rejected_if_it_hides_unfinished_trips():
    report = validation_report(["models/a", "models/b"])
    for row in report["summary"]:
        if row["strategy"] == "rl:b":
            row.update(mean_wait_mean=1, completed_mean=90)
    result = select_candidate(report)
    assert result["selected_model"] == "models/a"
    rejected = next(row for row in result["candidates"] if row["model"] == "models/b")
    assert not rejected["eligible"]


def test_teleports_disqualify_a_candidate():
    report = validation_report(["models/a"])
    report["summary"][1]["teleports_mean"] = 0.2
    assert select_candidate(report)["status"] == "no_eligible_candidate"


def test_missing_peak_goal_keeps_final_test_unused():
    report = validation_report(["models/a"])
    report["comparisons"][0]["wait_reduction"] = 0.14
    assert select_candidate(report)["selected_model"] is None


def test_final_or_partial_reports_cannot_be_used_for_selection():
    report = validation_report(["models/a"])
    report["split"] = "test"
    with pytest.raises(ValueError, match="complete validation"):
        select_candidate(report)
    report.update(split="validation", seeds=[200])
    with pytest.raises(ValueError, match="complete validation"):
        select_candidate(report)


def test_freezing_detects_model_mutation_and_does_not_reselect(tmp_path):
    model = tmp_path / "model"
    model.mkdir()
    (model / "model.zip").write_bytes(b"original")
    (model / "config.json").write_text("{}")
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(validation_report([str(model)])))
    selection_path = tmp_path / "selection.json"
    frozen = freeze_selection(report_path, selection_path)
    assert freeze_selection(report_path, selection_path) == frozen
    verify_frozen_model(frozen)
    (model / "model.zip").write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed after freezing"):
        verify_frozen_model(frozen)
    report_path.write_text("{}")
    with pytest.raises(ValueError, match="report changed"):
        freeze_selection(report_path, selection_path)


def test_restart_skips_completed_runs_and_does_not_repeat_final_test(tmp_path, monkeypatch):
    from rl import experiment

    output = tmp_path / "experiment"
    train_calls, eval_calls = [], []

    def fake_train(net, timesteps, alpha, seed, *args, **kwargs):
        model = tmp_path / f"model_a{alpha}_s{seed}"
        model.mkdir()
        (model / "model.zip").write_bytes(b"trained")
        (model / "config.json").write_text('{"status":"completed"}')
        train_calls.append((alpha, seed))
        return model

    def fake_evaluation(*, models, split, out, **kwargs):
        if split == "test":
            assert (output / "selection.json").exists()
            assert len(models) == 1
        out.mkdir(parents=True)
        report = validation_report([str(model) for model in models])
        report["split"] = split
        (out / "report.json").write_text(json.dumps(report))
        eval_calls.append(split)
        return out

    monkeypatch.setattr(experiment, "train", fake_train)
    monkeypatch.setattr(experiment, "run_evaluation", fake_evaluation)
    monkeypatch.setattr(experiment, "capture_inputs", lambda *args: {"snapshot": "same"})
    monkeypatch.setattr(experiment, "train_routes", lambda *args: [])
    monkeypatch.setattr("sys.argv", ["experiment", "--out", str(output), "--final-test"])
    experiment.main()
    experiment.main()
    assert len(train_calls) == 6
    assert eval_calls == ["validation", "test"]
    state = json.loads((output / "experiment.json").read_text())
    assert state["status"] == "completed"
