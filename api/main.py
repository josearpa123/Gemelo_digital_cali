"""sim-api: FastAPI entry point. H0 exposes only /health; the simulation loop arrives in H1."""

import shutil
import subprocess

import fastapi

app = fastapi.FastAPI(title="Gemelo digital Cali · sim-api")


def sumo_version() -> str:
    binary = shutil.which("sumo")
    if binary is None:
        return "missing"
    out = subprocess.run([binary, "--version"], capture_output=True, text=True, check=False)
    return out.stdout.splitlines()[0] if out.stdout else "unknown"


SUMO_VERSION = sumo_version()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "sumo": SUMO_VERSION, "scenario": None}
