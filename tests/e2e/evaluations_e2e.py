"""Browser check of real evaluation reports (no assistant/LLM requests)."""

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    run = sys.argv[2] if len(sys.argv) > 2 else "pipeline_check_20261118"
    output = Path("outputs/verification")
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        credentials = None
        if password := os.environ.get("DEMO_E2E_PASSWORD"):
            credentials = {"username": "operator", "password": password}
        page = browser.new_page(
            viewport={"width": 1600, "height": 1000}, http_credentials=credentials
        )
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url, wait_until="networkidle")
        page.wait_for_selector("#evaluation-results table")
        page.select_option("#evaluation-run", run)
        page.wait_for_selector("#evaluation-results table")
        if run == "pipeline_check_20261118":
            assert "Corrida corta" in page.inner_text("#evaluation-status")
        assert "Validación" in page.inner_text("#evaluation-status")
        report = page.request.get(f"{url}/api/evaluations/report?{urlencode({'run': run})}")
        assert report.ok
        has_unverified = "unverified" in report.json()["compatibility"].values()
        assert ("compatibilidad" in page.inner_text("#evaluation-status")) == has_unverified
        tables = page.locator("#evaluation-results table")
        assert tables.count() == 2
        assert tables.nth(0).locator("tbody tr").count() == 9
        assert tables.nth(1).locator("tbody tr").count() == 6
        csv_url = page.locator("#evaluation-csv").get_attribute("href")
        response = page.request.get(url + csv_url)
        assert response.ok and "wait_p95" in response.text()
        page.click("#evaluation-refresh")
        page.wait_for_selector("#evaluation-results table")
        assert page.locator("#evaluation-run").input_value() == run
        assert not errors, errors
        page.locator(".evaluation-panel").screenshot(path=str(output / "evaluation-panel.png"))
        result = {
            "status": "passed",
            "checks": 8,
            "javascript_errors": errors,
            "report": f"outputs/evaluations/{run}/report.json",
        }
        (output / "evaluation-browser.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
        browser.close()


if __name__ == "__main__":
    main()
