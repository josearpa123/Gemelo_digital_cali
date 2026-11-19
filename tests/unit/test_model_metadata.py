import json
import zipfile

from sim.controllers.rl_policy import find_model, model_metadata


def test_current_reports_actual_run_and_saved_steps(tmp_path):
    run = tmp_path / "ppo_new"
    run.mkdir()
    (run / "config.json").write_text(
        json.dumps({"timesteps": 3000000, "alpha": 0, "signal": "cyclic"})
    )
    with zipfile.ZipFile(run / "model.zip", "w") as archive:
        archive.writestr("data", json.dumps({"num_timesteps": 3000320}))
    (tmp_path / "current").symlink_to(run.name, target_is_directory=True)
    selected = find_model(tmp_path)
    assert selected == tmp_path / "current" / "model.zip"
    info = model_metadata(selected)
    assert info == {"run_id": "ppo_new", "timesteps": 3000320, "alpha": 0, "signal": "cyclic"}


def test_model_metadata_without_config_or_data_is_explicit(tmp_path):
    with zipfile.ZipFile(tmp_path / "model.zip", "w"):
        pass
    info = model_metadata(tmp_path / "model.zip")
    assert info["run_id"] == tmp_path.name
    assert info["timesteps"] is None
    assert info["signal"] == "legacy"
