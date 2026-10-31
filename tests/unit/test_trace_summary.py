"""Indicators of the "Trazas" panel computed from events with known values."""

from sim.trace_summary import summarize


def ev(component, type_, ts=1000.0, status="ok", **data):
    return {"component": component, "type": type_, "ts": ts, "status": status, "data": data}


def test_indicators_from_known_events():
    sim = [
        ev("sim", "sim_segundo", step_ms=2.0, rtf=10.0),
        ev("sim", "sim_segundo", step_ms=4.0, rtf=20.0),
    ]
    decisions = [
        ev("rl", "decision", ts=990.0, inference_ms=1.0),
        ev("rl", "decision", ts=999.0, inference_ms=3.0),
        ev("rl", "decision", ts=900.0, inference_ms=2.0),  # older than one minute
    ]
    llm = [
        ev(
            "llm",
            "respuesta_ok",
            tokens_in=100,
            tokens_out=50,
            cost_real_usd=0.0,
            cost_paid_usd=0.000045,
            latency_s=0.5,
        ),
        ev(
            "llm",
            "respuesta_ok",
            tokens_in=200,
            tokens_out=10,
            cost_real_usd=0.0,
            cost_paid_usd=0.000036,
            latency_s=1.5,
        ),
    ]
    counts = [
        ("llm", "llamada_enviada", "ok", 3),
        ("llm", "error_timeout", "error", 1),
        ("rl", "fallback_control", "fallback", 2),
        ("rl", "decision", "ok", 3),
    ]
    s = summarize(sim, decisions, llm, counts, now=1000.0, fallback_tls=["t2", "t1"])
    assert s["sim"] == {"real_time_factor": 15.0, "step_ms": 3.0, "window": 2}
    assert s["rl"]["decisions_per_min"] == 2
    assert s["rl"]["inference_ms"] == 2.0
    assert s["rl"]["fallback_tls"] == ["t1", "t2"]
    assert s["llm"]["calls"] == 3
    assert (s["llm"]["tokens_in"], s["llm"]["tokens_out"], s["llm"]["tokens"]) == (300, 60, 360)
    assert s["llm"]["cost_real_usd"] == 0.0
    assert s["llm"]["cost_paid_usd"] == 0.000081
    assert s["llm"]["latency_s"] == 1.0
    assert s["failures"] == 3
    assert s["total"] == 9
    assert s["by_component"] == {"llm": 4, "rl": 5}


def test_empty_summary_has_no_invented_numbers():
    s = summarize([], [], [], [], now=0.0)
    assert s["sim"]["real_time_factor"] is None and s["rl"]["inference_ms"] is None
    assert s["llm"]["latency_s"] is None and s["failures"] == 0 and s["total"] == 0
