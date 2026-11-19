"""Predeclared validation-only selection; final-test results never influence ranking."""

import json
import math
import statistics
from datetime import UTC, datetime
from pathlib import Path

from sim.artifacts import file_hash
from sim.demand import VALIDATION_SEEDS

SCENARIOS = ("peak", "valley", "event")
RULE = (
    "Minimize the equal-weight mean of validation waiting/fixed waiting over peak, valley "
    "and event. Require paired peak waiting reduction >=15%, no more teleports than fixed, "
    "and at least 99% of fixed completed trips in each scenario. Ties: strategy name. "
    "Fairness is reported separately. Never rerank using final-test results."
)


def select_candidate(report: dict) -> dict:
    if (
        report.get("status") != "completed"
        or report.get("split") != "validation"
        or set(report.get("seeds", [])) != set(VALIDATION_SEEDS)
        or report.get("seconds", 0) < 3600
        or set(report.get("scenarios", [])) != set(SCENARIOS)
    ):
        raise ValueError("selection requires complete validation (200-204, three 1h scenarios)")
    rows = {(r["strategy"], r["scenario"]): r for r in report["summary"]}
    if len(rows) != len(report["summary"]):
        raise ValueError("duplicate evaluation summaries")
    candidates = []
    for model in report["models"]:
        strategy = f"rl:{Path(model).name}"
        reasons, ratios, fairness = [], [], {}
        for scenario in SCENARIOS:
            own, baseline = rows.get((strategy, scenario)), rows.get(("fixed", scenario))
            if own is None or baseline is None or own["n"] != 5 or baseline["n"] != 5:
                raise ValueError("selection requires five paired seeds per strategy and scenario")
            for row in (own, baseline):
                for metric in ("mean_wait_mean", "completed_mean", "teleports_mean"):
                    if not isinstance(row.get(metric), (int, float)) or not math.isfinite(
                        row[metric]
                    ):
                        raise ValueError(f"invalid selection metric: {metric}")
            if baseline["mean_wait_mean"] <= 0:
                raise ValueError("selection requires positive fixed waiting in every scenario")
            ratios.append(own["mean_wait_mean"] / baseline["mean_wait_mean"])
            if own["teleports_mean"] > baseline["teleports_mean"]:
                reasons.append(f"{scenario}: more teleports than fixed")
            if own["completed_mean"] < 0.99 * baseline["completed_mean"]:
                reasons.append(f"{scenario}: fewer than 99% of fixed completed trips")
            fairness[scenario] = {
                "rl": own.get("jain_wait_mean"),
                "fixed": baseline.get("jain_wait_mean"),
            }
        peak = next(
            (
                r
                for r in report["comparisons"]
                if r["strategy"] == strategy
                and r["scenario"] == "peak"
                and r["baseline"] == "fixed"
            ),
            None,
        )
        if (
            peak is None
            or peak["n"] != 5
            or peak["wait_reduction"] is None
            or not math.isfinite(peak["wait_reduction"])
        ):
            raise ValueError("missing paired peak comparison")
        if peak["wait_reduction"] < 0.15:
            reasons.append("peak: paired waiting reduction below 15%")
        candidates.append(
            {
                "model": model,
                "strategy": strategy,
                "score": statistics.fmean(ratios),
                "eligible": not reasons,
                "reasons": reasons,
                "fairness": fairness,
            }
        )
    ranked = sorted(candidates, key=lambda row: (row["score"], row["strategy"]))
    winner = next((row for row in ranked if row["eligible"]), None)
    return {
        "status": "selected" if winner else "no_eligible_candidate",
        "rule": RULE,
        "selected_model": winner["model"] if winner else None,
        "candidates": ranked,
    }


def freeze_selection(report_path: Path, output: Path) -> dict:
    """Write once before evaluating test seeds; retain the original decision on restart."""
    if output.exists():
        frozen = json.loads(output.read_text())
        if frozen["validation_sha256"] != file_hash(report_path):
            raise ValueError("validation report changed after model selection")
        return frozen
    selected = select_candidate(json.loads(report_path.read_text()))
    selected.update(
        selected_utc=datetime.now(UTC).isoformat(),
        validation_report=str(report_path),
        validation_sha256=file_hash(report_path),
    )
    if selected["selected_model"]:
        model = Path(selected["selected_model"])
        selected["model_sha256"] = file_hash(model / "model.zip")
        selected["config_sha256"] = file_hash(model / "config.json")
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(selected, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(output)
    return selected


def verify_frozen_model(selection: dict) -> None:
    model = Path(selection["selected_model"])
    if (
        file_hash(model / "model.zip") != selection["model_sha256"]
        or file_hash(model / "config.json") != selection["config_sha256"]
    ):
        raise ValueError("selected model changed after freezing; final test is not allowed")


def write_experiment_report(folder: Path, state: dict) -> None:
    """Regenerated from real artifacts; variation across training seeds stays explicit."""
    lines = [
        "# Experimento de cooperación PPO",
        "",
        f"Estado: {state['status']}",
        "",
        "## Modelos",
        "",
        "| Alpha | Semilla | Modelo |",
        "|---|---|---|",
    ]
    for run in state["models"]:
        lines.append(f"| {run['alpha']} | {run['seed']} | {run['path']} |")
    validation_path = state.get("validation")
    if validation_path and (Path(validation_path) / "report.json").exists():
        report = json.loads((Path(validation_path) / "report.json").read_text())
        scores = select_candidate(report)["candidates"]
        by_model = {Path(run["path"]).name: run for run in state["models"]}
        lines += [
            "",
            "## Variación entre semillas de entrenamiento",
            "",
            "Score: espera normalizada por fijo, media de tres escenarios; menor es mejor.",
            "Media y desviación entre modelos, distintas de la variación de demanda.",
            "",
            "| Alpha | Modelos | Score medio | Desviación | Elegibles |",
            "|---|---|---|---|---|",
        ]
        for alpha in state["protocol"]["alphas"]:
            group = [r for r in scores if by_model[Path(r["model"]).name]["alpha"] == alpha]
            values = [r["score"] for r in group]
            spread = statistics.stdev(values) if len(values) > 1 else 0.0
            lines.append(
                f"| {alpha} | {len(values)} | {statistics.fmean(values):.4f} | "
                f"{spread:.4f} | {sum(r['eligible'] for r in group)} |"
            )
        lines += ["", f"Validación: `{validation_path}`.", ""]
    selection_path = folder / "selection.json"
    if selection_path.exists():
        selection = json.loads(selection_path.read_text())
        lines += [
            "## Selección fijada antes de la prueba final",
            "",
            selection["rule"],
            "",
            f"Modelo: `{selection['selected_model']}`.",
            "",
        ]
        if not selection["selected_model"]:
            lines.append("Ningún candidato elegible; no se usaron las semillas finales.")
    if state.get("test"):
        lines += [
            "",
            f"Prueba final del único modelo fijado: `{state['test']}`.",
            "Los resultados finales no se usan para elegir otro candidato.",
        ]
    lines += [
        "",
        "El modelo del panel no se cambia automáticamente.",
        "Demanda sintética; no es una validación con aforos de campo.",
    ]
    (folder / "experiment.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
