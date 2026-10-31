"""Human names of the signalised intersections (config/intersections.yaml)."""

import re
import unicodedata
from pathlib import Path

import yaml

CONFIG = Path("config/intersections.yaml")


def load_zone(zone: str, path: Path = CONFIG) -> dict:
    """{corridor, corridor_aliases, intersections: {tls_id: {name, aliases}}} or an empty zone."""
    empty = {"corridor": zone, "corridor_aliases": [], "intersections": {}}
    if not path.exists():
        return empty
    zones = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return empty | zones.get(zone, {})


def tls_names(zone: dict) -> dict[str, str]:
    return {tls: item["name"] for tls, item in zone["intersections"].items()}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def find_tls(zone: dict, text: str) -> str | None:
    """The intersection named in a free-text question (longest matching alias wins)."""
    words = f" {normalize(text)} "
    best, best_len = None, 0
    for tls, item in zone["intersections"].items():
        for alias in item.get("aliases", []):
            a = normalize(alias)
            if f" {a} " in words and len(a) > best_len:
                best, best_len = tls, len(a)
    return best


def mentions_corridor(zone: dict, text: str) -> bool:
    words = f" {normalize(text)} "
    return any(f" {normalize(a)} " in words for a in zone["corridor_aliases"])
