import json

from fastapi.testclient import TestClient

from api.main import app


def test_evaluation_report_and_csv_are_readable(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path))
    folder = tmp_path / "evaluations" / "model" / "validation"
    folder.mkdir(parents=True)
    payload = {
        "status": "completed",
        "split": "validation",
        "seeds": [200],
        "seconds": 300,
        "summary": [],
        "comparisons": [],
        "compatibility": {},
    }
    (folder / "report.json").write_text(json.dumps(payload))
    (folder / "runs.csv").write_text("strategy,mean_wait\nfixed,12\n")
    client = TestClient(app, base_url="http://localhost")
    listing = client.get("/api/evaluations").json()["evaluations"]
    assert listing[0]["id"] == "model/validation"
    response = client.get("/api/evaluations/report", params={"run": listing[0]["id"]})
    assert response.status_code == 200 and response.json()["split"] == "validation"
    response = client.get("/api/evaluations/runs.csv", params={"run": listing[0]["id"]})
    assert response.status_code == 200 and "fixed,12" in response.text


def test_evaluation_paths_cannot_escape_outputs(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path))
    (tmp_path / "report.json").write_text('{"status":"completed","summary":[]}')
    response = TestClient(app, base_url="http://localhost").get(
        "/api/evaluations/report", params={"run": ".."}
    )
    assert response.status_code == 404


def test_invalid_reports_are_not_published(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path))
    folder = tmp_path / "evaluations" / "broken"
    folder.mkdir(parents=True)
    (folder / "report.json").write_text('{"status":"running","summary":[]}')
    client = TestClient(app, base_url="http://localhost")
    assert client.get("/api/evaluations").json() == {"evaluations": []}
    assert client.get("/api/evaluations/report", params={"run": "broken"}).status_code == 409
