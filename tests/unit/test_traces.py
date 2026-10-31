"""Trace events: format, storage in SQLite + JSON log, filters, secrets never stored."""

import json

import pytest

from sim.tracing import COMPONENTS, NullTracer, Tracer, scrub

FAKE_KEY = "gsk_FAKEKEYFORTESTS_1234567890abcdef"


@pytest.fixture
def tracer(tmp_path):
    t = Tracer(tmp_path / "traces.db", log_path=tmp_path / "events.jsonl")
    yield t
    t.close()


def test_event_has_the_required_fields(tracer):
    e = tracer.emit("rl", "decision", data={"fase_elegida": 2}, sim_t=12.0, tls_id="t1")
    assert set(e) == {
        "seq",
        "trace_id",
        "ts",
        "sim_t",
        "component",
        "type",
        "status",
        "tls_id",
        "data",
    }
    assert e["status"] == "ok" and e["sim_t"] == 12.0 and e["tls_id"] == "t1"
    assert len(e["trace_id"]) == 16


def test_unknown_component_or_status_is_rejected(tracer):
    with pytest.raises(ValueError):
        tracer.emit("weather", "x")
    with pytest.raises(ValueError):
        tracer.emit("sim", "x", status="meh")


def test_events_are_stored_in_sqlite_and_json_log(tracer, tmp_path):
    for i, component in enumerate(COMPONENTS):
        tracer.emit(
            component, f"tipo_{i}", data={"i": i}, tls_id="t1" if component == "rl" else None
        )
    tracer.flush()
    stored = tracer.all_events()
    assert [e["component"] for e in stored] == list(COMPONENTS)
    assert stored[1]["data"] == {"i": 1}
    lines = (tmp_path / "events.jsonl").read_text().splitlines()
    assert len(lines) == len(COMPONENTS)
    assert json.loads(lines[0])["component"] == "sim"


def test_query_filters_by_component_tls_type_and_time(tracer):
    a = tracer.emit("rl", "decision", tls_id="t1")
    tracer.emit("rl", "decision", tls_id="t2")
    tracer.emit("sim", "sim_segundo")
    tracer.flush()
    assert [e["tls_id"] for e in tracer.query(component="rl", tls_id="t1")] == ["t1"]
    assert len(tracer.query(type="decision")) == 2
    assert len(tracer.query(since=a["ts"])) == 3
    assert tracer.query(until=a["ts"] - 1) == []
    assert tracer.query(trace_id=a["trace_id"])[0]["seq"] == a["seq"]


def test_sequence_continues_after_restart(tmp_path):
    t = Tracer(tmp_path / "t.db")
    t.emit("sim", "a")
    t.close()
    t2 = Tracer(tmp_path / "t.db")
    assert t2.emit("sim", "b")["seq"] == 2
    t2.close()


def test_websocket_buffer_returns_only_new_events(tracer):
    first = tracer.emit("sim", "a")
    tracer.emit("sim", "b")
    assert [e["type"] for e in tracer.since(first["seq"])] == ["b"]
    assert tracer.since(tracer.last_seq) == []


def test_secret_keys_and_values_never_reach_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", FAKE_KEY)
    t = Tracer(tmp_path / "t.db", log_path=tmp_path / "log.jsonl")
    t.emit(
        "llm", "error_servidor", "error", data={"api_key": FAKE_KEY, "error": f"Bearer {FAKE_KEY}"}
    )
    t.add_secret("panelkey_ABCDEFGHIJ")
    t.emit("llm", "x", data={"texto": "uso panelkey_ABCDEFGHIJ"})
    t.close()
    raw = (tmp_path / "t.db").read_bytes() + (tmp_path / "log.jsonl").read_bytes()
    assert FAKE_KEY.encode() not in raw
    assert b"panelkey_ABCDEFGHIJ" not in raw
    assert t.all_events()[0]["data"] == {"error": "Bearer ***"}


def test_scrub_drops_secret_keys_without_secrets_configured():
    assert scrub({"token": "x", "ok": 1}, secrets=[]) == {"ok": 1}


def test_counts_group_by_component_type_status(tracer):
    tracer.emit("rl", "fallback_control", "fallback")
    tracer.emit("rl", "decision")
    tracer.emit("rl", "decision")
    tracer.flush()
    assert sorted(tracer.counts()) == [
        ("rl", "decision", "ok", 2),
        ("rl", "fallback_control", "fallback", 1),
    ]


def test_training_jsonl_is_ingested_once(tracer, tmp_path):
    folder = tmp_path / "training"
    folder.mkdir()
    line = {"type": "episodio", "run_id": "ppo_x", "episodio": 1, "recompensa_media": -3.2}
    (folder / "ppo_x.jsonl").write_text(json.dumps(line) + "\n" + '{"type": "episodio", "run')
    assert tracer.ingest_jsonl(folder) == 1  # the half-written last line waits
    assert tracer.ingest_jsonl(folder) == 0
    tracer.flush()
    (e,) = tracer.query(component="training")
    assert e["type"] == "episodio" and e["trace_id"] == "ppo_x" and e["data"]["episodio"] == 1


def test_null_tracer_is_inert():
    t = NullTracer()
    assert t.emit("sim", "x") == {} and t.since(0) == [] and not t.enabled
