"""Structural (graph) validation of a :class:`CircuitModel`.

Deterministic and never-raising. Checks connectivity-level invariants: pin
existence, duplicate refs, dangling references, presence of a ground net, etc.
Hard structural breaks are FATAL; soft issues (missing footprint, unknown
symbol, duplicate/double connections) are WARNING/INFO.
"""

from __future__ import annotations

from circuit_agent.data import symbols as symbols_db
from circuit_agent.dsl.schema import CircuitModel, split_refpin
from circuit_agent.validators.base import Severity, ValidationIssue, ValidatorResult

_GROUND_NET_NAMES = {"GND", "GNDA", "AGND", "DGND", "GROUND"}

# Per-rule weights toward max_score and deductions.
_W_PIN_EXISTS = 1.0
_W_DUP_REF = 2.0
_W_DUP_CONN = 1.0
_W_HAS_SYMBOL = 2.0
_W_HAS_FOOTPRINT = 1.0
_W_HAS_GND = 2.0
_W_FLOATING_POWER = 1.0
_W_WELL_FORMED = 2.0


def check(model: CircuitModel) -> ValidatorResult:
    """Run the structural rules and return a :class:`ValidatorResult`."""
    issues: list[ValidationIssue] = []
    deductions = 0.0
    max_score = (
        _W_PIN_EXISTS
        + _W_DUP_REF
        + _W_DUP_CONN
        + _W_HAS_SYMBOL
        + _W_HAS_FOOTPRINT
        + _W_HAS_GND
        + _W_FLOATING_POWER
        + _W_WELL_FORMED
    )

    refs = [c.ref for c in model.components]
    ref_set = set(refs)

    # --- duplicate component refs (FATAL) ---
    seen: set[str] = set()
    dups: set[str] = set()
    for r in refs:
        if r in seen:
            dups.add(r)
        seen.add(r)
    if dups:
        deductions += _W_DUP_REF
        for r in sorted(dups):
            issues.append(
                ValidationIssue(
                    severity=Severity.FATAL,
                    code="duplicate_ref",
                    message=f"Duplicate component ref {r}",
                    refs=[r],
                )
            )

    # --- every component has a symbol (FATAL) and footprint (WARNING) ---
    missing_symbol = [c.ref for c in model.components if not (c.symbol and c.symbol.strip())]
    if missing_symbol:
        deductions += _W_HAS_SYMBOL
        for r in missing_symbol:
            issues.append(
                ValidationIssue(
                    severity=Severity.FATAL,
                    code="missing_symbol",
                    message=f"Component {r} has no symbol",
                    refs=[r],
                )
            )
    missing_fp = [c.ref for c in model.components if not c.footprint]
    if missing_fp:
        deductions += _W_HAS_FOOTPRINT * 0.5
        for r in missing_fp:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="missing_footprint",
                    message=f"Component {r} has no footprint",
                    refs=[r],
                )
            )

    # --- well-formed connections + dangling refs (FATAL) ---
    well_formed_broken = False
    pin_to_nets: dict[str, list[str]] = {}
    for net in model.nets:
        local_conns: list[str] = []
        for conn in net.connections:
            try:
                ref, _pin = split_refpin(conn)
            except ValueError:
                well_formed_broken = True
                issues.append(
                    ValidationIssue(
                        severity=Severity.FATAL,
                        code="malformed_connection",
                        message=f"Connection {conn!r} on net {net.name} is not REF.PIN",
                        refs=[conn],
                    )
                )
                continue
            if ref not in ref_set:
                well_formed_broken = True
                issues.append(
                    ValidationIssue(
                        severity=Severity.FATAL,
                        code="dangling_ref",
                        message=f"Net {net.name} references unknown component {ref} (in {conn})",
                        refs=[conn],
                    )
                )
            pin_to_nets.setdefault(conn, []).append(net.name)
            local_conns.append(conn)

        # duplicate connection within a single net (WARNING)
        dup_local = {c for c in local_conns if local_conns.count(c) > 1}
        for c in sorted(dup_local):
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="duplicate_connection",
                    message=f"Connection {c} appears more than once on net {net.name}",
                    refs=[c],
                )
            )
    if well_formed_broken:
        deductions += _W_WELL_FORMED

    # pin connected across multiple distinct nets (WARNING)
    multi_net = {pin: nets for pin, nets in pin_to_nets.items() if len(set(nets)) > 1}
    for pin in sorted(multi_net):
        issues.append(
            ValidationIssue(
                severity=Severity.WARNING,
                code="pin_in_multiple_nets",
                message=f"Pin {pin} is connected to multiple nets: {sorted(set(multi_net[pin]))}",
                refs=[pin],
            )
        )
    if multi_net:
        deductions += _W_DUP_CONN * 0.5

    # --- referenced pins exist on the symbol ---
    pin_issue_found = False
    for net in model.nets:
        for conn in net.connections:
            try:
                ref, pin = split_refpin(conn)
            except ValueError:
                continue
            comp = model.find_component(ref)
            if comp is None or not comp.symbol:
                continue
            if not symbols_db.has_symbol(comp.symbol):
                # Unknown symbol: cannot verify -> WARNING, not FATAL.
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        code="unknown_symbol",
                        message=f"Symbol {comp.symbol} for {ref} is not in the catalog; cannot verify pin {pin}",
                        refs=[ref],
                    )
                )
                pin_issue_found = True
                continue
            valid_pins = symbols_db.pin_numbers(comp.symbol)
            if pin not in valid_pins:
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        code="unknown_pin",
                        message=f"Pin {pin} not found on symbol {comp.symbol} for {ref}",
                        refs=[conn],
                    )
                )
                pin_issue_found = True
    if pin_issue_found:
        deductions += _W_PIN_EXISTS * 0.5

    # --- at least one ground net (FATAL) ---
    has_gnd = any(
        net.name.upper() in _GROUND_NET_NAMES
        or (net.net_class and "gnd" in net.net_class.lower())
        for net in model.nets
    )
    if not has_gnd:
        deductions += _W_HAS_GND
        issues.append(
            ValidationIssue(
                severity=Severity.FATAL,
                code="no_ground_net",
                message="Circuit has no ground (GND/GNDA/AGND) net",
                refs=[],
            )
        )

    # --- floating power_in pins (WARNING) ---
    connected_pins: set[str] = set(pin_to_nets.keys())
    floating_power = 0
    for comp in model.components:
        if not comp.symbol or not symbols_db.has_symbol(comp.symbol):
            continue
        for pindef in symbols_db.symbol_pins(comp.symbol):
            if pindef.etype == "power_in":
                key = f"{comp.ref}.{pindef.number}"
                if key not in connected_pins:
                    floating_power += 1
                    issues.append(
                        ValidationIssue(
                            severity=Severity.WARNING,
                            code="floating_power_pin",
                            message=f"Power pin {key} ({pindef.name}) is not connected",
                            refs=[key],
                        )
                    )
    if floating_power:
        deductions += _W_FLOATING_POWER * 0.5

    score = max(0.0, min(max_score, max_score - deductions))
    details = {
        "component_count": len(model.components),
        "net_count": len(model.nets),
        "has_ground": has_gnd,
        "duplicate_refs": sorted(dups),
        "missing_symbol_refs": missing_symbol,
        "missing_footprint_refs": missing_fp,
        "floating_power_pins": floating_power,
    }
    return ValidatorResult(
        name="graph_rules",
        score=round(score, 6),
        max_score=max_score,
        issues=issues,
        details=details,
    )
