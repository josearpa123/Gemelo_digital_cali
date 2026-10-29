"""Scripted incidents for the `event` scenario: <zone>.event.json next to the network.

{"lane": "<lane id>", "begin": 900, "duration": 1200, "description": "..."}
The lane is closed (only `authority` allowed, 1 m/s) from `begin` to `begin + duration`,
the same way the panel's accident button does it (`SimRunner.set_accident`)."""

import json
from pathlib import Path


def event_path(net_file: Path) -> Path:
    net_file = Path(net_file)
    return net_file.with_name(net_file.name.replace(".net.xml", ".event.json"))


def load_event(net_file: Path) -> dict | None:
    path = event_path(net_file)
    if not path.exists():
        return None
    event = json.loads(path.read_text())
    for key in ("lane", "begin", "duration"):
        if key not in event:
            raise ValueError(f"{path}: missing '{key}'")
    return event


def active(event: dict, t: float) -> bool:
    return event["begin"] <= t < event["begin"] + event["duration"]
