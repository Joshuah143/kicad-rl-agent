"""Component availability computation.

Aggregates per-component ``availability_score`` (0..1), falling back to the parts
catalog. Components with no determinable availability are listed in
``missing_refs`` and excluded from the aggregates.
"""

from __future__ import annotations

from typing import Optional

from circuit_agent.dsl.schema import CircuitModel

_LOW_THRESHOLD = 0.5


def _lookup_availability(comp) -> Optional[float]:
    try:
        from circuit_agent.data import parts_db

        for spec in parts_db.PARTS.values():
            if spec.symbol == comp.symbol and spec.footprint == comp.footprint:
                return spec.availability_score
        for spec in parts_db.PARTS.values():
            if spec.symbol == comp.symbol:
                return spec.availability_score
    except Exception:  # pragma: no cover - defensive
        return None
    return None


def compute(model: CircuitModel) -> dict:
    """Return availability details for ``model`` (deterministic)."""
    scores: list[float] = []
    low: list[str] = []
    missing: list[str] = []

    for comp in model.components:
        score = comp.availability_score
        if score is None:
            score = _lookup_availability(comp)
        if score is None:
            missing.append(comp.ref)
            continue
        score = float(score)
        scores.append(score)
        if score < _LOW_THRESHOLD:
            low.append(comp.ref)

    if scores:
        min_av = round(min(scores), 6)
        avg_av = round(sum(scores) / len(scores), 6)
    else:
        min_av = None
        avg_av = None

    return {
        "min_availability": min_av,
        "avg_availability": avg_av,
        "low_availability": low,
        "missing_refs": missing,
    }


__all__ = ["compute"]
