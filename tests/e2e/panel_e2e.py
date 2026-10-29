"""End-to-end check of the web panel with Playwright (run with `make e2e`).

Loads the page, checks that vehicles move on the map, exercises the controls and
stores screenshots in outputs/e2e/."""

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
OUT = Path("outputs/e2e")


def api_state(page) -> dict:
    return json.loads(page.evaluate("fetch('/api/state').then(r => r.text())"))


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
        page.select_option("#speed", "5")
        checks.append(("sin errores de JavaScript", not errors))
        browser.close()
    for name, ok in checks:
        print(f"{'OK   ' if ok else 'FALLO'} {name}")
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
