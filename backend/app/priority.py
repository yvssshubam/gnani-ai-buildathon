"""Fixed priority rules. The LLM never decides priority: these rules do.

P0  life in danger now          -> also alert a human
P1  serious / not yet known     -> rescue soon
P2  needs rescue, stable        -> rescue in turn
P3  relief or information only  -> send to relief teams
"""
from __future__ import annotations

from .models import WATER_LEVELS, Ticket

LEVEL = {name: i for i, name in enumerate(WATER_LEVELS)}


def _level(name):
    return LEVEL.get(name) if name else None


def assess(t: Ticket) -> tuple[str, list[str], bool]:
    """Return (priority, reasons, alert_human)."""
    d = t.danger
    wl = _level(d.water_level)
    has_vulnerable = bool(t.vulnerable)

    # ---- P0: life in danger right now ----
    p0 = []
    if wl is not None and wl >= LEVEL["chest"]:
        p0.append(f"water at {d.water_level} level")
    if d.medical_emergency:
        p0.append("medical emergency")
    if d.injured:
        p0.append("someone injured")
    if d.structure_unsafe:
        p0.append("building unsafe")
    if d.water_rising and has_vulnerable and wl is not None and wl >= LEVEL["knee"]:
        p0.append("water rising with vulnerable people")
    if p0:
        return "P0", p0, True

    # ---- P1: serious, or we don't know enough yet ----
    p1 = []
    if wl is not None and wl >= LEVEL["waist"]:
        p1.append(f"water at {d.water_level} level")
    if has_vulnerable:
        p1.append("vulnerable: " + ", ".join(t.vulnerable))
    if d.trapped:
        p1.append("trapped")
    if d.water_rising:
        p1.append("water rising")
    if t.medical_need:
        p1.append(f"medical need: {t.medical_need}")
    relief_only = bool(t.needs) and "rescue" not in t.needs
    if wl is None and not relief_only:
        p1.append("danger level not known yet")
    if p1:
        return "P1", p1, False

    # ---- P2: needs rescue but stable ----
    if "rescue" in t.needs or (wl is not None and wl >= LEVEL["ankle"]):
        return "P2", [f"water at {d.water_level or 'unknown'} level, no vulnerable people reported"], False

    # ---- P3: relief or info only ----
    return "P3", ["relief or information only: " + (", ".join(t.needs) or "none stated")], False