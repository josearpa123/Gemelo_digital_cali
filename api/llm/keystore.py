"""API key entered from the panel. Stored only on the server (secrets/, never in git, mode
600) and never returned by the API: the panel can only set, test or clear it."""

import os
import re
from pathlib import Path

KEY_FILE = Path(os.environ.get("LLM_KEY_FILE", "secrets/llm_api_key"))
KEY_FORMAT = re.compile(r"^[A-Za-z0-9_\-\.]{20,200}$")


def load(path: Path | None = None) -> str:
    path = path or KEY_FILE
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def save(key: str, path: Path | None = None) -> None:
    path = path or KEY_FILE
    if not KEY_FORMAT.match(key):
        raise ValueError("la clave tiene un formato inválido (20 a 200 caracteres, sin espacios)")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(key)


def clear(path: Path | None = None) -> None:
    path = path or KEY_FILE
    path.unlink(missing_ok=True)
