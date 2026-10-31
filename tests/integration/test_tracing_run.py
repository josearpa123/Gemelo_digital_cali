"""Traced runs on the real Cali network: RL decisions per intersection, event impact,
every "Armar fallo" option with its fallback, and the faster reward terms."""

import copy

import pytest

from sim.controllers.rl_policy import find_model
from sim.faults import FAULTS, FaultInjector
from sim.tracing import Tracer

NET = "scenarios/roosevelt4/roosevelt4.net.xml"
ROUTES = "scenarios/roosevelt4/demand/peak_s0.rou.xml"

pytestmark = pytest.mark.skipif(find_model() is None, reason="no trained model in models/")


@pytest.fixture
def traced(tmp_path):
    from pathlib import Path

    from sim.runner import SimRunner

    if not (Path(NET).exists() and Path(ROUTES).exists()):
        pytest.skip("run make dataset first")
    tracer = Tracer(tmp_path / "traces.db")
    faults = FaultInjector(tracer)
    runner = SimRunner(
        Path(NET), Path(ROUTES), tracer=tracer, faults=faults, state_dir=tmp_path / "state"
    )
    yield runner, tracer, faults
    runner.close()
    tracer.close()


def of(tracer, type_):
    tracer.flush()
    return [e for e in tracer.all_events() if e["type"] == type_]


def test_300_rl_steps_trace_decisions_for_every_intersection(traced):
    runner, tracer, _ = traced
    runner.start("rl")
    for _ in range(300):
        runner.step()
    decisions = of(tracer, "decision")
    assert {d["tls_id"] for d in decisions} == set(runner.tls_lanes)  # all 4 intersections
    d = decisions[-1]["data"]
    for field in (
        "interseccion",
        "fase_anterior",
        "fase_elegida",
        "motivo",
        "aproximaciones",
        "recompensa",
        "alpha",
        "usa_vecinas",
        "inference_ms",
        "modelo",
    ):
        assert field in d
    assert d["interseccion"].startswith("Av. Roosevelt ×")
    assert all(not a["via"].startswith(":") for a in d["aproximaciones"])
    seconds = of(tracer, "sim_segundo")
    assert len(seconds) == 300  # one aggregated event per simulated second
    assert set(seconds[-1]["data"]["vehiculos"]) == {"carro", "moto", "peaton"}
    assert seconds[-1]["data"]["step_ms"] > 0
    assert [e["type"] for e in of(tracer, "escenario_inicio")] == ["escenario_inicio"]
    assert of(tracer, "carga_modelo")[0]["data"]["modelo"]


def test_accident_event_measures_its_impact_after_two_minutes(traced):
    runner, tracer, _ = traced
    runner.start("fixed")
    for _ in range(60):
        runner.step()
    trace_id = runner.set_accident(True)
    (accident,) = of(tracer, "accidente")
    assert accident["data"]["calle"] == "Calle 6" and accident["data"]["carril"]
    for _ in range(119):
        runner.step()
    assert of(tracer, "impacto") == []
    runner.step()
    (impact,) = of(tracer, "impacto")
    assert impact["trace_id"] == trace_id and impact["sim_t"] == 180.0
    assert set(impact["data"]["antes"]) == {"espera_media_s", "cola", "vehiculos"}
    assert (
        impact["data"]["delta_cola"]
        == impact["data"]["despues"]["cola"] - impact["data"]["antes"]["cola"]
    )


def test_rl_no_response_sends_that_tls_to_fixed_time_once(traced):
    runner, tracer, faults = traced
    runner.start("rl")
    for _ in range(20):
        runner.step()
    faults.arm("rl_no_response")
    for _ in range(10):
        runner.step()
    (fb,) = of(tracer, "fallback_control")
    assert fb["status"] == "fallback" and fb["data"]["control"] == "tiempo fijo"
    assert runner.fallback_tls == [fb["tls_id"]]
    assert not faults.is_armed("rl_no_response")  # disarmed after one use
    for _ in range(130):  # FALLBACK_SECONDS later the agent takes over again
        runner.step()
    assert runner.fallback_tls == []
    assert of(tracer, "control_recuperado")[0]["tls_id"] == fb["tls_id"]
    assert len(of(tracer, "fallback_control")) == 1


def test_detector_loss_uses_the_last_valid_observation(traced):
    runner, tracer, faults = traced
    runner.start("rl")
    for _ in range(20):
        runner.step()
    faults.arm("detector_loss")
    for _ in range(10):
        runner.step()
    (obs,) = of(tracer, "observacion_incompleta")
    assert obs["data"]["respaldo"] == "último valor válido" and obs["data"]["valores_perdidos"] > 0
    assert not faults.is_armed("detector_loss")
    assert of(tracer, "fallback_control") == []  # the agent kept deciding


def test_traci_disconnect_reconnects_and_resumes_the_scenario(traced):
    runner, tracer, faults = traced
    runner.start("rl")
    for _ in range(50):
        runner.step()
    runner.set_accident(True)
    faults.arm("traci_disconnect")
    runner.step()
    (err,) = of(tracer, "error_traci")
    (rec,) = of(tracer, "reconexion")
    assert err["status"] == "error" and rec["trace_id"] == err["trace_id"]
    assert rec["data"]["reanuda_en_t"] == 50.0 and rec["data"]["desde"] == "estado actual"
    assert not faults.is_armed("traci_disconnect")
    for _ in range(20):
        runner.step()
    snap = runner.snapshot()
    assert snap["t"] == 70.0 and snap["vehicles"] and runner.accident_lane


def test_fault_catalogue_matches_the_panel_options():
    assert set(FAULTS) == {
        "rl_no_response",
        "detector_loss",
        "traci_disconnect",
        "llm_timeout",
        "llm_rate_limit",
        "llm_invalid",
    }


def test_fast_reward_terms_match_sumo_rl(traced):
    """The cached waiting time and the pressure without pedestrian lanes give the same values
    as sumo-rl's own TrafficSignal methods."""
    from sumo_rl.environment.traffic_signal import TrafficSignal

    runner, _, _ = traced
    runner.start("rl")
    for _ in range(240):
        runner.step()
    for ts in runner.controller.signals.values():
        env = ts.env
        saved = copy.deepcopy(env.vehicles)
        fast = sum(ts.get_accumulated_waiting_time_per_lane())
        env.vehicles = saved
        original = sum(TrafficSignal.get_accumulated_waiting_time_per_lane(ts))
        assert fast == pytest.approx(original)
        assert ts.get_pressure() == TrafficSignal.get_pressure(ts)
