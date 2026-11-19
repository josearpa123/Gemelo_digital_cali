"""Fingerprints for training inputs and safe model loading (no secrets collected)."""

import hashlib
import json
import os
import platform
import warnings
import xml.etree.ElementTree as ET
from importlib import metadata
from pathlib import Path


def file_hash(path: Path, *, xml: bool = False) -> str:
    data = ET.tostring(ET.parse(path).getroot()) if xml else Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest()


def capture_inputs(net: Path, routes: list[Path]) -> dict:
    code = {}
    for folder in ("rl", "sim", "eval"):
        for path in sorted(Path(folder).rglob("*.py")):
            code[str(path)] = file_hash(path)
    versions = {"python": platform.python_version()}
    for package in (
        "torch",
        "stable-baselines3",
        "sumo-rl",
        "libsumo",
        "supersuit",
        "gymnasium",
        "pettingzoo",
        "numpy",
    ):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = "missing"
    additional = net.parent / "demand" / "vtypes.add.xml"
    event = net.with_name(net.name.replace(".net.xml", ".event.json"))
    return {
        "network_sha256": file_hash(net, xml=True),
        "routes": {str(p): file_hash(p, xml=True) for p in routes},
        "additional": {str(p): file_hash(p) for p in (additional, event) if p.exists()},
        "source_sha256": code,
        "versions": versions,
        "git_commit": os.environ.get("GIT_COMMIT", "unknown"),
        "git_dirty": os.environ.get("GIT_DIRTY", "unknown"),
    }


def verify_model_network(model: Path, net: Path, *, allow_legacy: bool = True) -> str:
    config_path = Path(model).parent / "config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    expected = config.get("provenance", {}).get("network_sha256")
    if expected is None:
        message = f"{model}: modelo sin huella de red; compatibilidad no verificada"
        if not allow_legacy:
            raise ValueError(message + "; use --allow-legacy solo para modelos auditados")
        warnings.warn(message, UserWarning, stacklevel=2)
        return "unverified"
    if expected != file_hash(net, xml=True):
        raise ValueError(f"{model}: la red o sus programas cambiaron; reentrene el modelo")
    return "verified"
