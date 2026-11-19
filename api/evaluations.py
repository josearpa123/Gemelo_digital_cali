"""Read-only evaluation reports; no simulation runs are triggered by the panel."""

import csv
import io
import json
import os
from itertools import islice
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from api.security import csv_cell

router = APIRouter(prefix="/api/evaluations")
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
MAX_CATALOG_SCAN = 1000


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
        with path.open("rb") as file:
            raw = file.read(MAX_ARTIFACT_BYTES + 1)
        if len(raw) > MAX_ARTIFACT_BYTES:
            raise ValueError("oversized report")
        report = json.loads(raw)
        if report.get("status") != "completed" or not isinstance(report.get("summary"), list):
            raise ValueError("incomplete evaluation")
        return report
    except (OSError, ValueError, AttributeError) as exc:
        raise HTTPException(409, "Reporte incompleto o inválido") from exc


@router.get("")
def list_evaluations() -> dict:
    base = root().resolve()
    paths = []
    for path in islice(base.rglob("report.json"), MAX_CATALOG_SCAN):
        if path.resolve().is_relative_to(base):
            try:
                paths.append((path.stat().st_mtime, path))
            except OSError:
                continue
    reports = []
    for _, path in sorted(paths, reverse=True)[:100]:
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
def evaluation_report(run: str = Query(min_length=1, max_length=200)) -> dict:
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
def evaluation_csv(run: str = Query(min_length=1, max_length=200)):
    path = report_path(run).with_name("runs.csv").resolve()
    if not path.is_relative_to(root().resolve()) or not path.is_file():
        raise HTTPException(404, "CSV no disponible")
    try:
        with path.open("rb") as file:
            content = file.read(MAX_ARTIFACT_BYTES + 1)
        if len(content) > MAX_ARTIFACT_BYTES:
            raise HTTPException(413, "CSV demasiado grande")
        out = io.StringIO(newline="")
        writer = csv.writer(out)
        for row in csv.reader(io.StringIO(content.decode("utf-8"), newline=""), strict=True):
            writer.writerow(csv_cell(cell) for cell in row)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise HTTPException(409, "CSV inválido") from exc
    return Response(
        out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="evaluacion.csv"'},
    )
