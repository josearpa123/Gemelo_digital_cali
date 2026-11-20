"""Defensive access and resource limits against an in-process server."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api import main
from api.security import csv_cell


@pytest.fixture
def auth_client(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS", "auth")
    monkeypatch.setenv("DEMO_ORIGIN", "https://demo.example")
    monkeypatch.setenv("DEMO_VIEWER_PASSWORD", "fake-viewer-password")
    monkeypatch.setenv("DEMO_OPERATOR_PASSWORD", "fake-operator-password")
    return TestClient(main.app, base_url="https://demo.example")


def test_anonymous_gets_login_but_no_dashboard_data(auth_client):
    assert auth_client.get("/health").status_code == 200
    page = auth_client.get("/", follow_redirects=False)
    assert page.status_code == 303 and page.headers["location"] == "/login"
    form = auth_client.get("/login")
    assert form.status_code == 200
    assert 'autocomplete="current-password"' in form.text
    assert "no-store" in form.headers["cache-control"]
    for endpoint in ("/api/network", "/api/traces/export.csv", "/api/evaluations"):
        assert auth_client.get(endpoint).status_code == 401
    with pytest.raises(WebSocketDisconnect) as exc:
        with auth_client.websocket_connect("wss://demo.example/ws/state"):
            pytest.fail("anonymous WebSocket was accepted")
    assert exc.value.code == 1008


def test_form_login_issues_session_only_for_valid_same_origin_credentials(auth_client):
    data = {"username": "viewer", "password": "fake-viewer-password"}
    rejected = auth_client.post("/login", data=data, headers={"Origin": "https://other.example"})
    assert rejected.status_code == 403 and "set-cookie" not in rejected.headers
    origin = {"Origin": "https://demo.example"}
    wrong = auth_client.post(
        "/login", data=data | {"password": "wrong"}, headers=origin, follow_redirects=False
    )
    assert wrong.headers["location"] == "/login?error=credentials"
    assert "set-cookie" not in wrong.headers
    accepted = auth_client.post("/login", data=data, headers=origin, follow_redirects=False)
    assert accepted.status_code == 303 and accepted.headers["location"] == "/"
    assert {"HttpOnly", "Secure", "SameSite=Strict"} <= set(
        part.strip() for part in accepted.headers["set-cookie"].split(";")
    )
    assert 'id="conn"' in auth_client.get("/").text
    assert auth_client.post("/api/control", json={}).status_code == 403


def test_roles_and_cross_origin_request(auth_client):
    viewer = ("viewer", "fake-viewer-password")
    operator = ("operator", "fake-operator-password")
    assert auth_client.get("/app.js", auth=viewer).status_code == 200
    for endpoint in ("/api/control", "/api/assistant/confirm", "/api/faults/arm"):
        assert auth_client.post(endpoint, json={}).status_code == 403
    auth_client.cookies.clear()
    assert auth_client.post("/api/llm/key", json={}, auth=operator).status_code == 403
    response = auth_client.post(
        "/api/control", json={}, auth=operator, headers={"Origin": "https://untrusted.example"}
    )
    assert response.status_code == 403
    assert auth_client.get("/app.js", auth=operator).status_code == 200
    with pytest.raises(WebSocketDisconnect) as exc:
        with auth_client.websocket_connect(
            "wss://demo.example/ws/state", headers={"Origin": "https://untrusted.example"}
        ):
            pytest.fail("cross-origin WebSocket was accepted")
    assert exc.value.code == 1008


def test_limits_and_redaction_before_endpoint(auth_client):
    operator = ("operator", "fake-operator-password")
    response = auth_client.post("/api/control", content=b"x" * 8193, auth=operator)
    assert response.status_code == 413
    response = auth_client.post(
        "/api/assistant", json={"modo": "resumen", "texto": "x" * 501}, auth=operator
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Solicitud inválida"}
    assert "x" * 501 not in response.text


def test_local_mode_rejects_non_loopback_host():
    client = TestClient(main.app, base_url="http://demo.example")
    assert client.get("/").status_code == 403


@pytest.mark.parametrize("text", ["=MARCADOR", " +MARCADOR", "-MARCADOR", "@MARCADOR", "\ttexto"])
def test_csv_cells_are_emitted_as_text(text):
    assert csv_cell(text) == "'" + text
