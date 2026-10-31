"""The key typed in the panel never comes back: not in API responses, traces, CSV or the
JSON log; it is stored with mode 600 in the test's temporary LLM_KEY_FILE (never secrets/)."""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main
from api.llm import keystore

pytestmark = pytest.mark.skipif(
    not (main.NET.exists() and main.ROUTES.exists()), reason="run make dataset first"
)

PANEL_KEY = "gsk_REVIEWER_FAKE_KEY_0123456789abcdefXYZ"


def test_conftest_isolates_the_key_file_from_the_real_secrets_dir():
    assert os.environ["LLM_KEY_FILE"] == str(keystore.KEY_FILE)
    assert Path("secrets").resolve() not in keystore.KEY_FILE.resolve().parents


def test_panel_key_never_leaves_the_server():
    with TestClient(main.app) as client:
        bodies = []
        res = client.post("/api/llm/key", json={"api_key": PANEL_KEY})
        assert res.status_code == 200 and res.json()["key_configured"]
        bodies.append(res.text)
        assert keystore.KEY_FILE.read_text() == PANEL_KEY
        assert keystore.KEY_FILE.stat().st_mode & 0o777 == 0o600
        bodies.append(client.get("/api/llm/info").text)
        bodies.append(client.post("/api/llm/test").text)  # fake provider: no network
        bodies.append(client.post("/api/assistant", json={"modo": "resumen"}).text)
        main.state.tracer.flush()
        bodies.append(client.get("/api/traces", params={"component": "llm"}).text)
        bodies.append(client.get("/api/traces/export.csv").text)
        bodies.append(client.get("/api/traces/summary").text)
        res = client.delete("/api/llm/key")
        assert not res.json()["key_configured"] and not keystore.KEY_FILE.exists()
        bodies.append(res.text)
        # a malformed key is rejected without echoing it
        bad = PANEL_KEY + " with spaces"
        res = client.post("/api/llm/key", json={"api_key": bad})
        assert res.status_code == 400 and bad not in res.text
    for body in bodies:
        assert PANEL_KEY not in body
    db = Path(os.environ["TRACES_DB"])
    raw = b"".join(p.read_bytes() for p in db.parent.glob(db.name + "*"))
    assert PANEL_KEY.encode() not in raw
