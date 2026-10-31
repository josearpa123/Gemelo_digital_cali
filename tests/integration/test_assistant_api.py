"""API end to end with the local fake LLM: natural-language command → accion_ejecutada and a
changed simulation, LLM faults with retries and fallback, summary = stored events,
WebSocket streaming of new events, panel served on the same port."""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from api import main

pytestmark = pytest.mark.skipif(
    not (main.NET.exists() and main.ROUTES.exists()), reason="run make dataset first"
)


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        c.post("/api/control", json={"action": "speed", "value": 50})
        main.state.assistant.backoff_s = 0
        yield c


def trace_types(client, trace_id):
    main.state.tracer.flush()
    return [e["type"] for e in client.get(f"/api/traces/{trace_id}").json()["events"]]


def test_panel_is_served_on_the_api_port(client):
    page = client.get("/")
    assert page.status_code == 200 and 'id="traces"' in page.text
    assert client.get("/traces.js").status_code == 200


def test_llm_info_uses_the_fake_provider_and_hides_keys(client):
    info = client.get("/api/llm/info").json()
    assert info["provider"] == "fake" and "api_key" not in info


def test_natural_language_command_changes_the_simulation(client):
    client.post("/api/control", json={"action": "demand", "value": "peak"})
    res = client.post(
        "/api/assistant", json={"modo": "comando", "texto": "pasa a hora valle"}
    ).json()
    assert res["executed"] and res["action"] == {"accion": "cambiar_demanda", "nivel": "valley"}
    assert main.state.runner.demand == "valley"
    assert trace_types(client, res["trace_id"])[-2:] == ["accion_validada", "accion_ejecutada"]
    client.post("/api/control", json={"action": "demand", "value": "peak"})


@pytest.mark.parametrize(
    "fault, expected",
    [
        ("llm_timeout", ["error_timeout", "reintento", "fallback_usado"]),
        ("llm_rate_limit", ["error_limite", "reintento", "fallback_usado"]),
        ("llm_invalid", ["respuesta_invalida", "accion_rechazada"]),
    ],
)
def test_llm_faults_fall_back_and_disarm(client, fault, expected):
    demand = main.state.runner.demand
    assert client.post("/api/faults/arm", json={"fault": fault}).status_code == 200
    res = client.post(
        "/api/assistant", json={"modo": "comando", "texto": "pasa a hora valle"}
    ).json()
    types = trace_types(client, res["trace_id"])
    assert set(expected) <= set(types)
    assert "accion_ejecutada" not in types and not res["executed"]
    assert main.state.runner.demand == demand  # nothing was executed
    if fault != "llm_invalid":
        assert types.count("llamada_enviada") == 3  # 1 + 2 retries
    assert client.get("/api/faults").json()["armed"] == []
    # the next call is healthy again
    ok = client.post("/api/assistant", json={"modo": "resumen", "texto": ""}).json()
    assert ok["source"] == "llm"


def test_unknown_fault_is_rejected(client):
    assert client.post("/api/faults/arm", json={"fault": "meteorito"}).status_code == 400


def test_summary_matches_stored_events(client):
    client.post("/api/assistant", json={"modo": "explicar", "texto": "¿por qué cambió la Cra 39?"})
    main.state.tracer.flush()
    summary = client.get("/api/traces/summary").json()
    stored = main.state.tracer.all_events()
    assert summary["total"] == len(stored)
    by_component = {}
    for e in stored:
        by_component[e["component"]] = by_component.get(e["component"], 0) + 1
    assert summary["by_component"] == by_component
    sent = sum(1 for e in stored if e["type"] == "llamada_enviada")
    assert summary["llm"]["calls"] == sent
    ok = [e for e in stored if e["type"] == "respuesta_ok"]
    assert summary["llm"]["tokens"] == sum(
        e["data"]["tokens_in"] + e["data"]["tokens_out"] for e in ok
    )
    assert summary["failures"] == sum(1 for e in stored if e["status"] in ("error", "fallback"))


def test_traces_endpoint_filters_and_csv_export(client):
    sims = client.get("/api/traces", params={"component": "sim", "limit": 5}).json()["events"]
    assert sims and all(e["component"] == "sim" for e in sims)
    assert client.get("/api/traces", params={"component": "nope"}).status_code == 400
    assert client.get("/api/traces/no-such-trace").status_code == 404
    csv = client.get("/api/traces/export.csv", params={"component": "llm"})
    assert csv.headers["content-type"].startswith("text/csv")
    header, *rows = csv.text.strip().splitlines()
    assert header.startswith("seq,trace_id,hora_real,tiempo_simulado,componente")
    assert rows and all(",llm," in r for r in rows)


def test_websocket_streams_new_trace_events(client):
    with client.websocket_connect("/ws/state") as ws:
        ws.receive_json()
        client.post("/api/control", json={"action": "pause", "value": True})
        deadline = time.time() + 10
        seen = []
        while time.time() < deadline and "pausa" not in seen:
            seen += [e["type"] for e in ws.receive_json().get("traces", [])]
        client.post("/api/control", json={"action": "pause", "value": False})
    assert "pausa" in seen


def test_explanation_context_uses_real_decisions(client):
    if "rl" not in main.state.runner.strategies:
        pytest.skip("no trained model")
    client.post("/api/control", json={"action": "restart", "value": "rl"})
    deadline = time.time() + 20
    while time.time() < deadline and not main.state.tracer.query(type="decision", limit=1):
        time.sleep(0.2)
    ctx = asyncio.run(main.Bridge().context("explicar", "¿por qué cambió la carrera 39?"))
    assert ctx["interseccion"] == "Av. Roosevelt × Cra 39"
    assert ctx["decisiones"] or ctx["estrategia"] != "rl"
    client.post("/api/control", json={"action": "restart", "value": "fixed"})
