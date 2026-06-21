"""Bill-of-materials cost computation.

Sums per-component unit costs, falling back to the parts/footprint catalogs when
a component carries no explicit cost. Components whose cost cannot be determined
are listed in ``missing_cost_refs`` and treated as 0 for the total (but flagged).
"""

from __future__ import annotations

from typing import Optional

from circuit_agent.dsl.schema import CircuitModel


def _lookup_cost(comp) -> Optional[float]:
    """Best-effort cost lookup for a component without an explicit cost."""
    try:
        from circuit_agent.data import parts_db

        for spec in parts_db.PARTS.values():
            if spec.symbol == comp.symbol and spec.footprint == comp.footprint:
                return spec.unit_cost_usd
        for spec in parts_db.PARTS.values():
            if spec.symbol == comp.symbol:
                return spec.unit_cost_usd
    except Exception:  # pragma: no cover - defensive
        return None
    return None


def compute(model: CircuitModel) -> dict:
    """Return BOM cost details for ``model`` (deterministic)."""
    line_items: list[dict] = []
    missing: list[str] = []
    total = 0.0

    for comp in model.components:
        cost = comp.unit_cost_usd
        if cost is None:
            cost = _lookup_cost(comp)
        if cost is None:
            missing.append(comp.ref)
            cost_for_total = 0.0
        else:
            cost_for_total = float(cost)
        total += cost_for_total
        line_items.append(
            {
                "ref": comp.ref,
                "value": comp.value,
                "unit_cost_usd": cost if cost is not None else None,
                "package_type": comp.package_type.value,
            }
        )

    return {
        "total_cost_usd": round(total, 6),
        "line_items": line_items,
        "missing_cost_refs": missing,
    }


__all__ = ["compute"]
