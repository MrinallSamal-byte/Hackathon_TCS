"""Live counter queues — static prep times lie during rush hour.

Three pickup counters; every menu category maps to one. Queue minutes are a
deterministic function of time-of-day (peaks) plus admin overrides, so the
engine can route around busy counters and ETAs stay honest.

Off-peak queues are zero, so plain prep times rule most of the day.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

COUNTERS: dict[str, dict] = {
    "main":      {"label": "Main Counter",     "categories": {"main_course", "breakfast", "combo"}},
    "snacks":    {"label": "Snacks Counter",   "categories": {"snack"}},
    "beverages": {"label": "Beverages Counter", "categories": {"beverage", "dessert"}},
}

# (start_h, end_h, {counter: extra_minutes}) — simulated rush-hour load.
PEAKS: list[tuple[float, float, dict[str, int]]] = [
    (9.0, 10.5, {"main": 4, "beverages": 2}),
    (12.5, 14.0, {"main": 10, "snacks": 5, "beverages": 3}),
    (19.0, 21.0, {"main": 8, "snacks": 4, "beverages": 2}),
]

_overrides: dict[str, int] = {}


def counter_of(category: str) -> str:
    for name, spec in COUNTERS.items():
        if category in spec["categories"]:
            return name
    return "main"


def queues_at(now: Optional[datetime] = None,
              overrides: Optional[dict[str, int]] = None) -> dict[str, int]:
    now = now or datetime.now()
    h = now.hour + now.minute / 60.0
    out = {name: 0 for name in COUNTERS}
    for start, end, extra in PEAKS:
        if start <= h < end:
            for name, mins in extra.items():
                out[name] += mins
    ov = overrides if overrides is not None else _overrides
    for name, mins in ov.items():
        if name in out:
            out[name] = max(0, int(mins))
    return out


def current_queues() -> dict[str, int]:
    return queues_at()


def effective_prep(prep_minutes: int, category: str,
                   queues: Optional[dict[str, int]] = None) -> int:
    q = queues or {}
    return int(prep_minutes) + int(q.get(counter_of(category), 0))


def set_override(counter: str, minutes: int) -> dict[str, int]:
    if counter not in COUNTERS:
        raise KeyError(f"Unknown counter '{counter}'")
    _overrides[counter] = max(0, int(minutes))
    return current_queues()


def clear_overrides() -> dict[str, int]:
    _overrides.clear()
    return current_queues()
