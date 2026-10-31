"""End-to-end check of the web panel with Playwright (run with `make e2e`).

Loads the page, checks that vehicles move on the map, exercises the controls and the
"Trazas" section (filters, intersection selected on the map, armed fault with its fallback
live) and stores screenshots in outputs/e2e/."""

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = Path("outputs/e2e")


def api_state(page) -> dict:
    return json.loads(page.evaluate("fetch('/api/state').then(r => r.text())"))


ANY_ROW = "[...document.querySelectorAll('#trace-list li')].some(li => li.dataset.type"


def rows(page, selector="#trace-list li") -> list[dict]:
    return page.eval_on_selector_all(
        selector,
        "els => els.map(e => ({c: e.dataset.component, t: e.dataset.type, txt: e.textContent}))",
    )


def traces_checks(page, checks) -> None:
    """Trazas: section, indicators, filters, intersection filter from the map, armed fault."""
    page.wait_for_selector("#traces #trace-list li")
    checks.append(("sección Trazas con eventos", len(rows(page)) > 0))
    page.wait_for_function("document.querySelector('#tk-rtf').textContent.includes('×')")
    checks.append(("indicador de factor de tiempo real", "×" in page.inner_text("#tk-rtf")))

    page.click("#trace-filters button[data-filter='sim']")
    page.wait_for_function(f"{ANY_ROW} === 'sim_segundo')")
    checks.append(("filtro Simulación", {r["c"] for r in rows(page)} == {"sim"}))

    rl = page.locator("#strategies button[data-id='rl']")
    if not rl.is_enabled():
        checks.append(("filtros RL (sin modelo: omitido)", True))
        return
    rl.click()
    page.click("#trace-filters button[data-filter='rl']")
    page.wait_for_function(f"{ANY_ROW} === 'decision')")
    checks.append(("filtro Agentes RL", {r["c"] for r in rows(page)} == {"rl"}))

    # real mouse click on the ring of the first intersection drawn on the map
    point = page.evaluate("window.hubScreenPoint(0)")
    page.mouse.click(point["x"], point["y"])
    page.wait_for_selector("#tls-filter:not([hidden])")
    name = page.inner_text("#tls-filter span")
    time.sleep(2)
    decisions = [r for r in rows(page) if r["t"] == "decision"]
    label = name.replace("INTERSECCIÓN: ", "")
    checks.append(
        (
            "clic en intersección filtra sus decisiones",
            bool(decisions) and all(label in r["txt"] for r in decisions),
        )
    )

    page.select_option("#fault-select", "rl_no_response")
    page.click("#fault-arm")
    page.wait_for_function(
        f"{ANY_ROW} === 'fallback_control')",
        timeout=20000,
    )
    fallback = [r for r in rows(page) if r["t"] == "fallback_control"]
    checks.append(
        ("fallo «Agente RL sin respuesta» → fallback en vivo", "TIEMPO FIJO" in fallback[0]["txt"])
    )
    page.wait_for_function(
        "Number(document.querySelector('#tk-fb').textContent) >= 1", timeout=10000
    )
    checks.append(("indicador semáforos en fallback", int(page.inner_text("#tk-fb")) >= 1))
    page.locator("#trace-list li[data-type='fallback_control']").first.click()
    checks.append(("detalle del evento", "fallback_control" in page.inner_text("#trace-detail")))
    page.screenshot(path=str(OUT / "panel_traces_fallback.png"))
    page.click("#tls-clear")
    page.click("#trace-filters button[data-filter='all']")

    page.click("#assistant-modes button[data-mode='resumen']")
    page.fill("#assistant-input", "")
    calls = int(page.inner_text("#tk-calls") or 0) if page.inner_text("#tk-calls").isdigit() else 0
    page.click("#assistant-send")
    page.wait_for_function(
        "document.querySelector('#assistant-answer').textContent.includes('fuente')", timeout=30000
    )
    page.wait_for_function(
        f"Number(document.querySelector('#tk-calls').textContent) > {calls}", timeout=10000
    )
    checks.append(("asistente responde y suben las llamadas LLM", True))
    page.locator("#strategies button[data-id='fixed']").click()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    checks = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 950})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(URL, wait_until="networkidle")
        page.wait_for_selector("#strategies button")
        page.select_option("#speed", "20")
        page.wait_for_function("document.querySelector('#conn').classList.contains('on')")
        time.sleep(4)
        first = api_state(page)["snapshot"]
        time.sleep(3)
        second = api_state(page)["snapshot"]
        moved = {v["id"]: (v["lon"], v["lat"]) for v in first["vehicles"]}
        moved_count = sum(
            1
            for v in second["vehicles"]
            if moved.get(v["id"], (v["lon"], v["lat"])) != (v["lon"], v["lat"])
        )
        checks.append(("la simulación avanza", second["t"] > first["t"]))
        checks.append(("vehículos se mueven en el mapa", moved_count > 0))
        points = page.evaluate(
            "Chart.getChart('chart-wait').data.datasets.reduce((n, d) => n + d.data.length, 0)"
        )
        checks.append(("gráficas con datos", points > 3))
        page.screenshot(path=str(OUT / "panel_fixed.png"))

        page.click("#accident")
        page.wait_for_function("document.querySelector('#accident').classList.contains('active')")
        checks.append(("accidente activo", bool(api_state(page)["snapshot"]["accident_lane"])))
        time.sleep(4)
        page.screenshot(path=str(OUT / "panel_accident.png"))
        page.click("#accident")

        page.locator("#strategies button[data-id='maxpressure']").click()
        page.wait_for_selector("#strategies button[data-id='maxpressure'].active")
        page.click("#restart")
        time.sleep(6)
        snap = api_state(page)["snapshot"]
        checks.append(("max-pressure activa", snap["strategy"] == "maxpressure" and snap["t"] > 0))
        page.screenshot(path=str(OUT / "panel_maxpressure.png"))

        rl = page.locator("#strategies button[data-id='rl']")
        if rl.is_enabled():
            rl.click()
            page.wait_for_selector("#strategies button[data-id='rl'].active")
            page.click("#restart")
            time.sleep(6)
            checks.append(("estrategia RL activa", api_state(page)["snapshot"]["strategy"] == "rl"))
            page.screenshot(path=str(OUT / "panel_rl.png"))
            page.locator("#strategies button[data-id='fixed']").click()
        page.click("#pause")
        t1 = api_state(page)["snapshot"]["t"]
        time.sleep(1.5)
        checks.append(("pausa detiene el tiempo", api_state(page)["snapshot"]["t"] == t1))
        page.click("#pause")
        traces_checks(page, checks)
        page.select_option("#speed", "5")
        checks.append(("sin errores de JavaScript", not errors))
        browser.close()
    for name, ok in checks:
        print(f"{'OK   ' if ok else 'FALLO'} {name}")
    passed = sum(ok for _, ok in checks)
    (OUT / "result.json").write_text(
        json.dumps(
            {
                "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "url": URL,
                "passed": passed,
                "total": len(checks),
                "checks": [{"check": n, "ok": ok} for n, ok in checks],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"{passed}/{len(checks)} → {OUT / 'result.json'}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
