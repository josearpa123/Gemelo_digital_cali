"""Check the selected PPO artifact and its visible version against the real API."""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    output = Path("outputs/verification")
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url, wait_until="networkidle")
        page.wait_for_selector("#rl-model")
        selected = page.request.get(url + "/api/strategies").json()
        model = next(item["model"] for item in selected["strategies"] if item["id"] == "rl")
        assert page.inner_text("#rl-model-name") == model["run_id"]
        assert model["run_id"] == "ppo_roosevelt4_a0_s0_20261119-0131"
        assert model["timesteps"] == 3000320
        assert "3.000.320" in page.inner_text("#rl-model-details")
        page.wait_for_function("document.querySelector('#conn').classList.contains('on')")
        button = page.locator("#strategies button[data-id='rl']")
        if "active" not in (button.get_attribute("class") or ""):
            button.click()
        page.wait_for_function(
            "document.querySelector('#rl-model-status').textContent === 'Modelo en uso'"
        )
        state = page.request.get(url + "/api/state").json()
        assert state["snapshot"]["strategy"] == "rl"
        assert state["error"] is None
        assert not errors, errors
        page.locator("aside.left section").first.screenshot(
            path=str(output / "model-selected-20261119.png")
        )
        result = {"status": "passed", "model": model, "strategy": "rl", "javascript_errors": errors}
        (output / "model-selected-20261119.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
        browser.close()


if __name__ == "__main__":
    main()
