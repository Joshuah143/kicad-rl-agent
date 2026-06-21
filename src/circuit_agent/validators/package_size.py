"""Package-size computation: total board area and per-part breakdown.

Uses a component's explicit ``package_dims_mm`` when present, otherwise the
footprint catalog area. VIRTUAL parts (test points, power flags) contribute no
area. Parts whose area cannot be determined are listed in ``missing_dims_refs``.
"""

from __future__ import annotations

from typing import Optional

from circuit_agent.dsl.schema import CircuitModel, PackageType


def _area_for(comp) -> Optional[float]:
    """Return the bounding-box area (mm^2) for a component, or ``None``."""
    if comp.package_dims_mm is not None:
        w, h = comp.package_dims_mm
        return float(w) * float(h)
    if comp.footprint:
        try:
            from circuit_agent.data import footprints

            area = footprints.footprint_area(comp.footprint)
            if area is not None:
                return float(area)
        except Exception:  # pragma: no cover - defensive
            return None
    return None


def compute(model: CircuitModel) -> dict:
    """Return package-size details for ``model`` (deterministic)."""
    by_ref: dict[str, float] = {}
    missing: list[str] = []
    total_area = 0.0
    smt_count = 0
    tht_count = 0
    virtual_count = 0
    largest_ref: Optional[str] = None
    largest_area = 0.0

    for comp in model.components:
        if comp.package_type is PackageType.VIRTUAL:
            virtual_count += 1
        elif comp.package_type is PackageType.THT:
            tht_count += 1
        else:
            # SMD and MIXED both count as surface-mount for this coarse metric.
            smt_count += 1

        area = _area_for(comp)
        if area is None:
            if comp.package_type is not PackageType.VIRTUAL:
                missing.append(comp.ref)
            continue
        if comp.package_type is PackageType.VIRTUAL:
            # Virtual parts occupy no board area.
            by_ref[comp.ref] = 0.0
            continue

        by_ref[comp.ref] = round(area, 4)
        total_area += area
        if area > largest_area:
            largest_area = area
            largest_ref = comp.ref

    return {
        "total_area_mm2": round(total_area, 4),
        "smt_count": smt_count,
        "tht_count": tht_count,
        "virtual_count": virtual_count,
        "by_ref": by_ref,
        "largest": {"ref": largest_ref, "area": round(largest_area, 4)},
        "missing_dims_refs": missing,
    }


__all__ = ["compute"]
