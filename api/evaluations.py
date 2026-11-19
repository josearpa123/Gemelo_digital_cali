"""Read-only evaluation reports; no simulation runs are triggered by the panel."""

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/evaluations")


def root() -> Path:
    return Path(os.environ.get("OUTPUTS_DIR", "outputs")) / "evaluations"


def report_path(run: str) -> Path:
    base = root().resolve()
    candidate = (base / run / "report.json").resolve()
    if not candidate.is_relative_to(base) or not candidate.is_file():
        raise HTTPException(404, "Evaluación no encontrada")
    return candidate


def read_report(path: Path) -> dict:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("status") != "completed" or not isinstance(report.get("summary"), list):
            raise ValueError("incomplete evaluation")
        return report
    except (OSError, ValueError, AttributeError) as exc:
        raise HTTPException(409, "Reporte incompleto o inválido") from exc


@router.get("")
def list_evaluations() -> dict:
    base = root().resolve()
    paths = sorted(base.rglob("report.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    reports = []
    for path in paths[:100]:
        if not path.resolve().is_relative_to(base):
            continue
        try:
            report = read_report(path)
        except HTTPException:
            continue
        reports.append(
            {
                "id": path.parent.relative_to(base).as_posix(),
                "started_utc": report.get("started_utc"),
                "split": report.get("split"),
                "scenarios": report.get("scenarios", []),
                "seeds": report.get("seeds", []),
                "seconds": report.get("seconds"),
                "models": report.get("models", []),
            }
        )
    return {"evaluations": reports}


@router.get("/report")
def evaluation_report(run: str) -> dict:
    report = read_report(report_path(run))
    # Source hashes and absolute paths remain in the downloadable local artifacts.
    return {
        k: report.get(k)
        for k in (
            "status",
            "split",
            "seeds",
            "scenarios",
            "seconds",
            "started_utc",
            "summary",
            "comparisons",
            "compatibility",
        )
    }


@router.get("/runs.csv")
def evaluation_csv(run: str):
    path = report_path(run).with_name("runs.csv").resolve()
    if not path.is_relative_to(root().resolve()) or not path.exists():
        raise HTTPException(404, "CSV no disponible")
    return FileResponse(path, media_type="text/csv", filename="evaluacion.csv")
