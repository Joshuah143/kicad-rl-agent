"""The deterministic reward.

Given identical inputs :func:`compute_reward` returns an identical dict (no
wall-clock, no randomness). It combines the schema check, ERC, the structural and
electrical validators, cost/size/availability metrics and an optional LLM critic
into a single scalar reward plus a fully itemised breakdown.

Scoring is documented inline; every component is weighted by the task's
:class:`~circuit_agent.task.Objectives`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from circuit_agent.dsl.schema import CircuitModel
from circuit_agent.task import TaskSpec
from circuit_agent.validators.base import CriticResult, ValidatorResult

if TYPE_CHECKING:  # pragma: no cover - typing only
    from circuit_agent.kicad.parse_erc import ERCResult

# Fixed weight for the schema-valid gate (independent of task objectives).
_SCHEMA_WEIGHT = 1.0
# Reference area (mm^2) for the smooth size score when no max_area is set.
_SIZE_REFERENCE_MM2 = 100.0


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def compute_reward(
    model: CircuitModel,
    task: TaskSpec,
    *,
    schema_valid: bool = True,
    erc: "Optional[ERCResult]" = None,
    erc_ran: bool = False,
    graph: ValidatorResult,
    electrical: ValidatorResult,
    bom: dict,
    size: dict,
    avail: dict,
    critic: "Optional[CriticResult]" = None,
) -> dict:
    """Compute the deterministic reward dict for one scored design."""
    obj = task.objectives
    prefs = task.preferences

    fatal_errors: list[str] = []
    warnings: list[str] = []

    # --- schema_valid (fixed unit weight) -----------------------------------
    if schema_valid:
        schema_component = _SCHEMA_WEIGHT
    else:
        schema_component = 0.0
        fatal_errors.append("schema invalid: program did not produce a valid CircuitModel")

    # --- ERC -----------------------------------------------------------------
    if erc_ran and erc is not None:
        if erc.error_count == 0:
            erc_component = obj.erc_weight * 1.0
        else:
            erc_component = 0.0
            for v in erc.violations:
                if str(v.severity).lower() == "error":
                    fatal_errors.append(f"ERC error: {v.type}: {v.description}".strip())
            if not any(str(v.severity).lower() == "error" for v in erc.violations):
                fatal_errors.append(f"ERC reported {erc.error_count} error(s)")
    else:
        erc_component = 0.0
        warnings.append("ERC skipped (KiCad unavailable)")

    # --- graph rules ---------------------------------------------------------
    graph_component = obj.graph_rule_weight * graph.fraction()
    for issue in graph.fatals:
        fatal_errors.append(issue.message)
    for issue in graph.warnings:
        warnings.append(issue.message)

    # --- electrical rules ----------------------------------------------------
    electrical_component = obj.electrical_rule_weight * electrical.fraction()
    for issue in electrical.fatals:
        fatal_errors.append(issue.message)
    for issue in electrical.warnings:
        warnings.append(issue.message)

    # --- cost ----------------------------------------------------------------
    total_cost = float(bom.get("total_cost_usd", 0.0) or 0.0)
    max_cost = prefs.max_bom_cost_usd
    if max_cost is None or total_cost <= max_cost:
        cost_score = 1.0
    else:
        cost_score = _clamp01(max_cost / total_cost) if total_cost > 0 else 1.0
        warnings.append(f"BOM cost ${total_cost:.4f} exceeds budget ${max_cost:.4f}")
    cost_component = obj.cost_weight * cost_score

    # --- size ----------------------------------------------------------------
    total_area = float(size.get("total_area_mm2", 0.0) or 0.0)
    tht_count = int(size.get("tht_count", 0) or 0)
    smt_count = int(size.get("smt_count", 0) or 0)
    if prefs.max_area_mm2 is not None:
        if total_area <= prefs.max_area_mm2:
            size_score = 1.0
        else:
            size_score = _clamp01(prefs.max_area_mm2 / total_area) if total_area > 0 else 1.0
            warnings.append(f"Total area {total_area:.2f} mm^2 exceeds max {prefs.max_area_mm2:.2f} mm^2")
    else:
        # Smooth decreasing function; reference == _SIZE_REFERENCE_MM2.
        size_score = 1.0 / (1.0 + total_area / _SIZE_REFERENCE_MM2)

    # Package-type preference penalties (multiplicative on the size score).
    pref_pkg = (prefs.package_type or "").upper()
    if pref_pkg == "SMD" and tht_count > 0:
        penalty = _clamp01(1.0 - 0.1 * tht_count)
        size_score *= penalty
        warnings.append(f"SMD preferred but design has {tht_count} THT part(s)")
    elif pref_pkg == "THT" and smt_count > 0:
        penalty = _clamp01(1.0 - 0.1 * smt_count)
        size_score *= penalty
        warnings.append(f"THT preferred but design has {smt_count} SMD part(s)")
    size_component = obj.size_weight * _clamp01(size_score)

    # --- availability --------------------------------------------------------
    avg_av = avail.get("avg_availability")
    avg_av = float(avg_av) if avg_av is not None else 0.0
    availability_component = obj.availability_weight * avg_av
    min_av = avail.get("min_availability")
    if prefs.min_availability is not None and min_av is not None and float(min_av) < prefs.min_availability:
        warnings.append(
            f"Min availability {float(min_av):.2f} below required {prefs.min_availability:.2f}"
        )

    # --- LLM critic ----------------------------------------------------------
    if critic is not None:
        critic_component = obj.llm_critic_weight * float(critic.score)
        for issue in critic.fatal_issues:
            fatal_errors.append(f"critic: {issue}")
        for w in critic.warnings:
            warnings.append(f"critic: {w}")
    else:
        critic_component = 0.0

    breakdown = {
        "schema_valid": round(schema_component, 4),
        "erc": round(erc_component, 4),
        "graph_rules": round(graph_component, 4),
        "electrical_rules": round(electrical_component, 4),
        "cost": round(cost_component, 4),
        "size": round(size_component, 4),
        "availability": round(availability_component, 4),
        "llm_critic": round(critic_component, 4),
    }

    total = sum(breakdown.values())
    reward = round(max(0.0, total), 4)

    passed = (
        schema_valid
        and not fatal_errors
        and (not erc_ran or (erc is not None and erc.error_count == 0))
    )

    metrics = {
        "total_cost_usd": total_cost,
        "total_area_mm2": total_area,
        "min_availability": float(min_av) if min_av is not None else None,
        "smt_count": smt_count,
        "tht_count": tht_count,
    }

    return {
        "reward": reward,
        "passed": passed,
        "breakdown": breakdown,
        "fatal_errors": fatal_errors,
        "warnings": warnings,
        "metrics": metrics,
    }


__all__ = ["compute_reward"]
