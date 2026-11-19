"""Metrics from SUMO tripinfo files plus Jain's fairness index."""

import math
import xml.etree.ElementTree as ET
from pathlib import Path


def jain(values: list[float]) -> float:
    """J = (sum x)^2 / (n * sum x^2); 1 when all equal, 1/n when one takes everything."""
    xs = [float(v) for v in values]
    if not xs:
        return float("nan")
    squares = sum(x * x for x in xs)
    if squares == 0:
        return 1.0
    return sum(xs) ** 2 / (len(xs) * squares)


def read_tripinfo(path: Path) -> list[dict]:
    trips = []
    for trip in ET.parse(path).getroot().iter("tripinfo"):
        trips.append(
            {
                "id": trip.get("id"),
                "type": trip.get("vType"),
                "duration": float(trip.get("duration")),
                "waiting": float(trip.get("waitingTime")),
                # --tripinfo-output.write-unfinished marks vehicles still driving with arrival -1
                "finished": float(trip.get("arrival", -1)) >= 0,
            }
        )
    return trips


def trip_metrics(path: Path) -> dict:
    trips = read_tripinfo(path)
    n = len(trips)
    mean = lambda key: sum(t[key] for t in trips) / n if n else float("nan")  # noqa: E731
    return {
        "trips": n,
        "completed": sum(t["finished"] for t in trips),
        "completion_rate": sum(t["finished"] for t in trips) / n if n else 0.0,
        "unfinished": sum(not t["finished"] for t in trips),
        "mean_travel_time": mean("duration"),
        "mean_wait": mean("waiting"),
        "wait_p95": percentile([t["waiting"] for t in trips], 0.95),
        "wait_max": max((t["waiting"] for t in trips), default=0.0),
    }


def percentile(values: list[float], q: float) -> float:
    """Linearly interpolated empirical quantile; all trips, including unfinished ones."""
    if not values:
        return float("nan")
    xs = sorted(values)
    position = (len(xs) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return xs[low] + (xs[high] - xs[low]) * (position - low)


def approach_metrics(wait_s: dict, vehicles: dict, queue_sum: dict, queue_max: dict, steps: int):
    """Per-approach aggregates sampled every step: mean wait per vehicle that used the approach,
    mean and max queue (halting vehicles)."""
    used = [a for a in wait_s if vehicles.get(a)]
    mean_wait = [wait_s[a] / len(vehicles[a]) for a in used]
    return {
        "jain_wait": jain(mean_wait),
        "queue_mean": sum(queue_sum.values()) / (len(queue_sum) * steps) if queue_sum else 0.0,
        "queue_max": max(queue_max.values(), default=0),
        "approaches": len(used),
        "approach_wait_max": max(mean_wait, default=0.0),
    }
