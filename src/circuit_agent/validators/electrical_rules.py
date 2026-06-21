"""Heuristic, domain-specific electrical checks on a :class:`CircuitModel`.

Deterministic and *tolerant*: detection heuristics that might mis-fire prefer
WARNING over FATAL, except the small set of explicit FATALs in the contract
(USB-C sink missing a 5.1k Rd pulldown on a CC pin; a +5V/+3V3 short).
``check`` reads the :class:`TaskSpec` for preferences/metadata but tolerates an
empty task.
"""

from __future__ import annotations

from typing import Optional

from circuit_agent.data import symbols as symbols_db
from circuit_agent.dsl.schema import CircuitModel, split_refpin
from circuit_agent.task import TaskSpec
from circuit_agent.validators import values
from circuit_agent.validators.base import Severity, ValidationIssue, ValidatorResult

# Acceptable Rd pulldown range for USB-C CC pins (5.1k nominal, tolerate +/-).
_RD_NOMINAL = 5100.0
_RD_LO = 4000.0
_RD_HI = 6200.0

_GROUND_NET_NAMES = {"GND", "GNDA", "AGND", "DGND", "GROUND"}

# Per-rule weights toward max_score.
_W_RES_VALUES = 1.0
_W_CAP_VALUES = 1.0
_W_USB_CC = 4.0
_W_I2C_PULLUP = 1.0
_W_LDO_CAPS = 1.0
_W_MCU_DECOUPLE = 1.0
_W_RAIL_SHORT = 4.0
_W_FLOATING_EN = 1.0


def _is_ground_net(name: str) -> bool:
    return name.upper() in _GROUND_NET_NAMES


def _nets_for_pin(model: CircuitModel, refpin: str) -> list[str]:
    """Return the names of nets that include ``refpin``."""
    out: list[str] = []
    for net in model.nets:
        if refpin in net.connections:
            out.append(net.name)
    return out


def _pin_etype_map(model: CircuitModel) -> dict[str, str]:
    """Map ``REF.PIN`` -> electrical type for every connected, known pin."""
    out: dict[str, str] = {}
    for comp in model.components:
        if not comp.symbol or not symbols_db.has_symbol(comp.symbol):
            continue
        for pindef in symbols_db.symbol_pins(comp.symbol):
            out[f"{comp.ref}.{pindef.number}"] = pindef.etype
    return out


def _net_of_refpin(model: CircuitModel, refpin: str) -> Optional[str]:
    nets = _nets_for_pin(model, refpin)
    return nets[0] if nets else None


def check(model: CircuitModel, task: TaskSpec) -> ValidatorResult:
    """Run the heuristic electrical rules and return a :class:`ValidatorResult`."""
    issues: list[ValidationIssue] = []
    deductions = 0.0
    max_score = (
        _W_RES_VALUES
        + _W_CAP_VALUES
        + _W_USB_CC
        + _W_I2C_PULLUP
        + _W_LDO_CAPS
        + _W_MCU_DECOUPLE
        + _W_RAIL_SHORT
        + _W_FLOATING_EN
    )

    # Build lookup of which (ref,pin) is on which net.
    ground_nets = {n.name for n in model.nets if _is_ground_net(n.name)}

    # --- resistor / capacitor value parsing (WARNING) ---
    bad_res = 0
    bad_cap = 0
    for comp in model.components:
        if comp.symbol in ("Device:R", "Device:R_Small") and comp.value:
            if values.parse_resistance(comp.value) is None:
                bad_res += 1
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        code="bad_resistor_value",
                        message=f"Resistor {comp.ref} has an unparseable value {comp.value!r}",
                        refs=[comp.ref],
                    )
                )
        if comp.symbol in ("Device:C", "Device:C_Small", "Device:C_Polarized") and comp.value:
            if values.parse_capacitance(comp.value) is None:
                bad_cap += 1
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        code="bad_capacitor_value",
                        message=f"Capacitor {comp.ref} has an unparseable value {comp.value!r}",
                        refs=[comp.ref],
                    )
                )
    if bad_res:
        deductions += _W_RES_VALUES * min(1.0, 0.5 * bad_res)
    if bad_cap:
        deductions += _W_CAP_VALUES * min(1.0, 0.5 * bad_cap)

    # --- USB-C sink: 5.1k Rd on BOTH CC1 and CC2 to GND (FATAL each if missing) ---
    usb_components = [
        c for c in model.components if c.symbol and "USB_C" in c.symbol
    ]
    if usb_components:
        for usb in usb_components:
            for cc_label, cc_pin in (("CC1", "A5"), ("CC2", "B5")):
                refpin = f"{usb.ref}.{cc_pin}"
                cc_nets = _nets_for_pin(model, refpin)
                if not _has_rd_pulldown(model, cc_nets, ground_nets):
                    deductions += _W_USB_CC / 2.0
                    issues.append(
                        ValidationIssue(
                            severity=Severity.FATAL,
                            code="usb_cc_missing_rd",
                            message=f"{cc_label} missing 5.1k Rd pulldown to GND",
                            refs=[usb.ref, refpin],
                        )
                    )

    # --- I2C pullups (WARNING) ---
    i2c_nets = _find_i2c_nets(model)
    if i2c_nets:
        pos_rails = _positive_rail_nets(model)
        for net_name in sorted(i2c_nets):
            if not _has_pullup(model, net_name, pos_rails):
                deductions += _W_I2C_PULLUP * 0.5
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        code="i2c_missing_pullup",
                        message=f"I2C net {net_name} has no pullup resistor to a positive rail",
                        refs=[net_name],
                    )
                )

    # --- LDO input/output caps (WARNING) ---
    ldos = [c for c in model.components if c.symbol and "AP2112" in c.symbol]
    for ldo in ldos:
        vin_net = _net_of_refpin(model, f"{ldo.ref}.1")
        vout_net = _net_of_refpin(model, f"{ldo.ref}.5")
        if vin_net and not _has_cap_to_ground(model, vin_net, ground_nets):
            deductions += _W_LDO_CAPS * 0.25
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="ldo_missing_input_cap",
                    message=f"LDO {ldo.ref} has no input capacitor on VIN ({vin_net})",
                    refs=[ldo.ref],
                )
            )
        if vout_net and not _has_cap_to_ground(model, vout_net, ground_nets):
            deductions += _W_LDO_CAPS * 0.25
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="ldo_missing_output_cap",
                    message=f"LDO {ldo.ref} has no output capacitor on VOUT ({vout_net})",
                    refs=[ldo.ref],
                )
            )
        # floating EN pin (WARNING)
        en_net = _net_of_refpin(model, f"{ldo.ref}.3")
        if en_net is None and not task.metadata.get("allow_floating_en"):
            deductions += _W_FLOATING_EN * 0.5
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="floating_enable",
                    message=f"LDO {ldo.ref} EN pin is not connected",
                    refs=[ldo.ref],
                )
            )

    # --- MCU decoupling (WARNING) ---
    mcus = [
        c
        for c in model.components
        if c.symbol and any(tag in c.symbol for tag in ("RP2040", "ESP32", "STM32"))
    ]
    for mcu in mcus:
        vdd_nets = _power_in_nets(model, mcu.ref)
        if vdd_nets and not any(
            _has_cap_to_ground(model, net, ground_nets) for net in vdd_nets
        ):
            deductions += _W_MCU_DECOUPLE * 0.5
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="mcu_missing_decoupling",
                    message=f"MCU {mcu.ref} has no decoupling capacitor on its VDD rail",
                    refs=[mcu.ref],
                )
            )

    # --- 5V/3V3 short (FATAL) ---
    if _has_rail_short(model):
        deductions += _W_RAIL_SHORT
        issues.append(
            ValidationIssue(
                severity=Severity.FATAL,
                code="rail_short",
                message="A single net joins a +5V and a +3V3 power symbol (short)",
                refs=[],
            )
        )

    score = max(0.0, min(max_score, max_score - deductions))
    details = {
        "usb_c_present": bool(usb_components),
        "i2c_nets": sorted(i2c_nets),
        "ldo_count": len(ldos),
        "mcu_count": len(mcus),
        "bad_resistor_values": bad_res,
        "bad_capacitor_values": bad_cap,
    }
    return ValidatorResult(
        name="electrical_rules",
        score=round(score, 6),
        max_score=max_score,
        issues=issues,
        details=details,
    )


# --------------------------------------------------------------------------- #
# Detection helpers
# --------------------------------------------------------------------------- #
def _resistor_value_ok_for_rd(comp_value: Optional[str]) -> bool:
    if not comp_value:
        return False
    ohms = values.parse_resistance(comp_value)
    return ohms is not None and _RD_LO <= ohms <= _RD_HI


def _has_rd_pulldown(model: CircuitModel, cc_nets: list[str], ground_nets: set[str]) -> bool:
    """A resistor (~5.1k, or role usb_cc_rd) bridging a CC net and GND."""
    if not cc_nets:
        return False
    cc_set = set(cc_nets)
    for comp in model.components:
        if comp.symbol not in ("Device:R", "Device:R_Small"):
            continue
        pin1 = f"{comp.ref}.1"
        pin2 = f"{comp.ref}.2"
        nets1 = set(_nets_for_pin(model, pin1))
        nets2 = set(_nets_for_pin(model, pin2))
        touches_cc = bool(nets1 & cc_set) or bool(nets2 & cc_set)
        touches_gnd = bool(nets1 & ground_nets) or bool(nets2 & ground_nets)
        if not (touches_cc and touches_gnd):
            continue
        if comp.role == "usb_cc_rd" or _resistor_value_ok_for_rd(comp.value):
            return True
    return False


def _find_i2c_nets(model: CircuitModel) -> set[str]:
    """Find nets that look like SDA/SCL by name or via an I2C sensor's pins."""
    out: set[str] = set()
    for net in model.nets:
        upper = net.name.upper()
        if upper in ("SDA", "SCL") or upper.endswith("_SDA") or upper.endswith("_SCL"):
            out.add(net.name)
    for comp in model.components:
        if not (comp.symbol and symbols_db.has_symbol(comp.symbol)):
            continue
        for pindef in symbols_db.symbol_pins(comp.symbol):
            if pindef.name in ("SDA", "SCL"):
                net = _net_of_refpin(model, f"{comp.ref}.{pindef.number}")
                if net:
                    out.add(net)
    return out


def _positive_rail_nets(model: CircuitModel) -> set[str]:
    """Nets that are positive supply rails (by name or power symbol)."""
    out: set[str] = set()
    pos_names = {"+5V", "+3V3", "+3.3V", "VCC", "VDD", "VBUS", "3V3", "5V"}
    for net in model.nets:
        if net.name.upper() in {n.upper() for n in pos_names}:
            out.add(net.name)
    for comp in model.components:
        if comp.symbol in ("power:+5V", "power:+3V3", "power:VBUS"):
            net = _net_of_refpin(model, f"{comp.ref}.1")
            if net:
                out.add(net)
    return out


def _has_pullup(model: CircuitModel, net_name: str, pos_rails: set[str]) -> bool:
    """A resistor bridging ``net_name`` and a positive rail."""
    for comp in model.components:
        if comp.symbol not in ("Device:R", "Device:R_Small"):
            continue
        nets1 = set(_nets_for_pin(model, f"{comp.ref}.1"))
        nets2 = set(_nets_for_pin(model, f"{comp.ref}.2"))
        touches_net = net_name in nets1 or net_name in nets2
        touches_rail = bool(nets1 & pos_rails) or bool(nets2 & pos_rails)
        if touches_net and touches_rail:
            return True
    return False


def _has_cap_to_ground(model: CircuitModel, net_name: str, ground_nets: set[str]) -> bool:
    """A capacitor bridging ``net_name`` and a ground net."""
    for comp in model.components:
        if comp.symbol not in ("Device:C", "Device:C_Small", "Device:C_Polarized"):
            continue
        nets1 = set(_nets_for_pin(model, f"{comp.ref}.1"))
        nets2 = set(_nets_for_pin(model, f"{comp.ref}.2"))
        touches_net = net_name in nets1 or net_name in nets2
        touches_gnd = bool(nets1 & ground_nets) or bool(nets2 & ground_nets)
        if touches_net and touches_gnd:
            return True
    return False


def _power_in_nets(model: CircuitModel, ref: str) -> list[str]:
    """Nets connected to ``ref``'s power_in pins (excluding ground)."""
    comp = model.find_component(ref)
    if comp is None or not symbols_db.has_symbol(comp.symbol):
        return []
    out: list[str] = []
    for pindef in symbols_db.symbol_pins(comp.symbol):
        if pindef.etype == "power_in" and pindef.name not in ("GND", "VSS"):
            net = _net_of_refpin(model, f"{ref}.{pindef.number}")
            if net and not _is_ground_net(net):
                out.append(net)
    return out


def _has_rail_short(model: CircuitModel) -> bool:
    """True if one net is connected to both a +5V and a +3V3 power symbol."""
    plus5_nets: set[str] = set()
    plus3_nets: set[str] = set()
    for comp in model.components:
        if comp.symbol == "power:+5V":
            net = _net_of_refpin(model, f"{comp.ref}.1")
            if net:
                plus5_nets.add(net)
        elif comp.symbol == "power:+3V3":
            net = _net_of_refpin(model, f"{comp.ref}.1")
            if net:
                plus3_nets.add(net)
    return bool(plus5_nets & plus3_nets)
