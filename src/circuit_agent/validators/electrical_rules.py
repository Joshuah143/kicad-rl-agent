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
_W_LED_RESISTOR = 1.0
_W_MOSFET_GATE = 1.0
_W_FLYBACK = 1.0
# Switching-converter completeness (graded across MANY interacting parts).
# Weighted heavily so that an incomplete converter scores MUCH lower than a
# complete one. Each missing element below contributes a fraction of this.
# Large relative to the other rules so that dropping several converter elements
# materially moves the electrical_rules fraction (an incomplete converter must
# score notably lower than a complete one, even after a smaller part count makes
# the design marginally cheaper/smaller).
_W_CONVERTER = 14.0

# Symbols that behave like a 3-terminal regulator/LDO for the caps heuristic.
_REGULATOR_SYMBOL_TAGS = ("AP2112", "MCP1700", "XC6206", "AP1117", "LM7805")
# Motor-driver / inductive-load symbols for the flyback-diode heuristic.
_MOTOR_SYMBOL_TAGS = ("DRV8833", "DRV8871")
# Switching-converter controller symbols (buck = non-synchronous, needs a catch
# diode; boost). Detected by symbol tag so the converter completeness checks fire.
_BUCK_SYMBOL_TAGS = ("MP1584", "LM2596")
_BOOST_SYMBOL_TAGS = ("TPS61023",)


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
        + _W_LED_RESISTOR
        + _W_MOSFET_GATE
        + _W_FLYBACK
        + _W_CONVERTER
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
    # AP2112 keeps its specific pin map (VIN=1, VOUT=5); other regulators use
    # the symbol pin etypes (power_in VIN / power_out VOUT) so the heuristic
    # generalizes across the LDO family without hard-coding every pinout.
    ldos = [
        c
        for c in model.components
        if c.symbol and any(tag in c.symbol for tag in _REGULATOR_SYMBOL_TAGS)
    ]
    for ldo in ldos:
        vin_net, vout_net = _regulator_in_out_nets(model, ldo)
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
        # floating EN pin (WARNING) — only the AP2112 in our catalog exposes EN.
        if "AP2112" not in (ldo.symbol or ""):
            continue
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

    # --- LED series resistor (WARNING) ---
    # Every LED should have a series resistor on its anode (or be in a circuit
    # that limits current). Heuristic: a resistor must share a net with the LED
    # anode pin. LEDs explicitly marked as needing no resistor are skipped.
    leds = [c for c in model.components if c.symbol in ("Device:LED",)]
    for led in leds:
        if led.role in ("no_series_r", "addressable"):
            continue
        anode_net = _net_of_refpin(model, f"{led.ref}.A")
        if anode_net and not _has_series_resistor_on_net(model, anode_net):
            deductions += _W_LED_RESISTOR * (1.0 / max(1, len(leds)))
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="led_missing_series_resistor",
                    message=f"LED {led.ref} has no series current-limiting resistor on its anode",
                    refs=[led.ref],
                )
            )

    # --- MOSFET gate resistor / pulldown (WARNING) ---
    # A switching MOSFET's gate should not float: expect a resistor (gate series
    # or pulldown) sharing the gate net.
    mosfets = [c for c in model.components if c.symbol in ("Device:Q_NMOS_GSD", "Device:Q_PMOS_GSD")]
    for q in mosfets:
        gate_net = _net_of_refpin(model, f"{q.ref}.1")
        if gate_net is None:
            deductions += _W_MOSFET_GATE * (1.0 / max(1, len(mosfets)))
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="mosfet_gate_floating",
                    message=f"MOSFET {q.ref} gate is not connected to any net",
                    refs=[q.ref],
                )
            )
        elif not _has_resistor_on_net(model, gate_net):
            deductions += _W_MOSFET_GATE * (1.0 / max(1, len(mosfets)))
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="mosfet_gate_no_resistor",
                    message=(
                        f"MOSFET {q.ref} gate net {gate_net} has no gate/pulldown resistor"
                    ),
                    refs=[q.ref],
                )
            )

    # --- flyback / freewheel diode across an inductive load (WARNING) ---
    # When a motor driver (inductive load) is present, expect a diode in the
    # design to clamp inductive kickback. Coarse: any diode anywhere satisfies it.
    motor_loads = [
        c
        for c in model.components
        if c.symbol and any(tag in c.symbol for tag in _MOTOR_SYMBOL_TAGS)
    ]
    if motor_loads:
        has_diode = any(
            c.symbol in ("Device:D", "Device:D_Schottky", "Device:D_TVS") for c in model.components
        )
        if not has_diode:
            deductions += _W_FLYBACK * 0.5
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="missing_flyback_diode",
                    message=(
                        "Inductive load (motor driver) present but no flyback/freewheel "
                        "diode found to clamp kickback"
                    ),
                    refs=[c.ref for c in motor_loads],
                )
            )

    # --- switching converter completeness (buck / boost) (WARNING, graded) ---
    # A switching converter is correct only when MANY parts are present and
    # wired together: input cap on VIN, a power inductor on SW, output cap on
    # the regulated rail, a 2-resistor feedback divider (VOUT->FB and FB->GND),
    # EN connected, and -- for a non-synchronous buck -- a catch Schottky diode
    # on SW->GND (cathode to SW). Each missing element is a WARNING and a slice
    # of _W_CONVERTER, so an incomplete converter scores materially lower than a
    # complete one. Never FATAL: detection is heuristic.
    converters = [
        c
        for c in model.components
        if c.symbol
        and any(tag in c.symbol for tag in (_BUCK_SYMBOL_TAGS + _BOOST_SYMBOL_TAGS))
    ]
    for conv in converters:
        is_buck = any(tag in (conv.symbol or "") for tag in _BUCK_SYMBOL_TAGS)
        # Slices of the converter weight. Buck has 6 checks; boost 5 (no catch
        # diode). Distribute the weight evenly across the applicable checks so a
        # complete converter scores the full _W_CONVERTER and each miss hurts.
        n_checks = 6 if is_buck else 5
        slice_w = _W_CONVERTER / float(n_checks * max(1, len(converters)))

        pin_net = {
            pindef.name: _net_of_refpin(model, f"{conv.ref}.{pindef.number}")
            for pindef in symbols_db.symbol_pins(conv.symbol)
        }
        vin_net = pin_net.get("VIN")
        sw_net = pin_net.get("SW")
        fb_net = pin_net.get("FB")
        en_net = pin_net.get("EN")
        # The regulated output rail: a boost exposes VOUT directly; for a buck it
        # is the far end of the power inductor whose near end sits on SW.
        vout_net = pin_net.get("VOUT")
        if vout_net is None and sw_net is not None:
            vout_net = _inductor_far_net(model, sw_net)

        # (1) input cap on VIN -> GND
        if not (vin_net and _has_cap_to_ground(model, vin_net, ground_nets)):
            deductions += slice_w
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="converter_missing_input_cap",
                    message=f"Converter {conv.ref} has no input capacitor on VIN to GND",
                    refs=[conv.ref],
                )
            )
        # (2) power inductor on SW
        if not (sw_net and _has_inductor_on_net(model, sw_net)):
            deductions += slice_w
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="converter_missing_inductor",
                    message=f"Converter {conv.ref} has no power inductor on its SW node",
                    refs=[conv.ref],
                )
            )
        # (3) output cap on the regulated rail -> GND
        if not (vout_net and _has_cap_to_ground(model, vout_net, ground_nets)):
            deductions += slice_w
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="converter_missing_output_cap",
                    message=f"Converter {conv.ref} has no output capacitor on its output rail to GND",
                    refs=[conv.ref],
                )
            )
        # (4) feedback resistor divider: VOUT->FB and FB->GND (two resistors)
        if not (
            fb_net
            and _has_feedback_divider(model, fb_net, vout_net, ground_nets)
        ):
            deductions += slice_w
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="converter_missing_fb_divider",
                    message=(
                        f"Converter {conv.ref} has no feedback resistor divider "
                        "(need VOUT->FB and FB->GND)"
                    ),
                    refs=[conv.ref],
                )
            )
        # (5) EN connected (not floating)
        if en_net is None and not task.metadata.get("allow_floating_en"):
            deductions += slice_w
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="converter_floating_enable",
                    message=f"Converter {conv.ref} EN pin is not connected",
                    refs=[conv.ref],
                )
            )
        # (6) BUCK ONLY: catch/freewheel Schottky diode on SW->GND (cathode to SW)
        if is_buck and not (
            sw_net and _has_catch_diode(model, sw_net, ground_nets)
        ):
            deductions += slice_w
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="buck_missing_catch_diode",
                    message=(
                        f"Non-synchronous buck {conv.ref} has no catch/freewheel "
                        "Schottky diode on SW to GND (cathode to SW)"
                    ),
                    refs=[conv.ref],
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
        "led_count": len(leds),
        "mosfet_count": len(mosfets),
        "motor_load_count": len(motor_loads),
        "converter_count": len(converters),
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


def _regulator_in_out_nets(model: CircuitModel, comp) -> tuple[Optional[str], Optional[str]]:
    """Return (VIN net, VOUT net) for a regulator component.

    AP2112 uses its explicit pin numbers (1=VIN, 5=VOUT). For every other
    regulator the symbol pin etypes/names are used: the power_in pin named VIN
    and the power_out pin named VOUT.
    """
    if "AP2112" in (comp.symbol or ""):
        return _net_of_refpin(model, f"{comp.ref}.1"), _net_of_refpin(model, f"{comp.ref}.5")
    vin_net: Optional[str] = None
    vout_net: Optional[str] = None
    for pindef in symbols_db.symbol_pins(comp.symbol):
        if pindef.name == "VIN":
            vin_net = vin_net or _net_of_refpin(model, f"{comp.ref}.{pindef.number}")
        elif pindef.name == "VOUT":
            vout_net = vout_net or _net_of_refpin(model, f"{comp.ref}.{pindef.number}")
    return vin_net, vout_net


def _has_resistor_on_net(model: CircuitModel, net_name: str) -> bool:
    """True if any resistor has a pin on ``net_name``."""
    for comp in model.components:
        if comp.symbol not in ("Device:R", "Device:R_Small"):
            continue
        nets1 = set(_nets_for_pin(model, f"{comp.ref}.1"))
        nets2 = set(_nets_for_pin(model, f"{comp.ref}.2"))
        if net_name in nets1 or net_name in nets2:
            return True
    return False


def _has_series_resistor_on_net(model: CircuitModel, net_name: str) -> bool:
    """True if a resistor sits on ``net_name`` (series current-limit heuristic)."""
    return _has_resistor_on_net(model, net_name)


# --------------------------------------------------------------------------- #
# Switching-converter detection helpers
# --------------------------------------------------------------------------- #
_INDUCTOR_SYMBOLS = ("Device:L", "Device:L_Small")
_DIODE_SYMBOLS = ("Device:D", "Device:D_Schottky")


def _has_inductor_on_net(model: CircuitModel, net_name: str) -> bool:
    """True if any inductor has a pin on ``net_name``."""
    for comp in model.components:
        if comp.symbol not in _INDUCTOR_SYMBOLS:
            continue
        nets1 = set(_nets_for_pin(model, f"{comp.ref}.1"))
        nets2 = set(_nets_for_pin(model, f"{comp.ref}.2"))
        if net_name in nets1 or net_name in nets2:
            return True
    return False


def _inductor_far_net(model: CircuitModel, near_net: str) -> Optional[str]:
    """Return the net on the *other* pin of an inductor whose one pin is ``near_net``.

    Used to find a buck's regulated output rail: the inductor bridges SW (near)
    and VOUT (far).
    """
    for comp in model.components:
        if comp.symbol not in _INDUCTOR_SYMBOLS:
            continue
        nets1 = set(_nets_for_pin(model, f"{comp.ref}.1"))
        nets2 = set(_nets_for_pin(model, f"{comp.ref}.2"))
        if near_net in nets1:
            for n in sorted(nets2):
                if n != near_net:
                    return n
        if near_net in nets2:
            for n in sorted(nets1):
                if n != near_net:
                    return n
    return None


def _has_feedback_divider(
    model: CircuitModel,
    fb_net: str,
    vout_net: Optional[str],
    ground_nets: set[str],
) -> bool:
    """True if a two-resistor divider sets FB: one R from VOUT->FB, one FB->GND.

    Presence-only (not value-checked). Requires a resistor bridging the FB net
    and the regulated output rail, AND a (different) resistor bridging FB and
    ground.
    """
    top_ok = False
    bottom_ok = False
    top_ref: Optional[str] = None
    for comp in model.components:
        if comp.symbol not in ("Device:R", "Device:R_Small"):
            continue
        nets1 = set(_nets_for_pin(model, f"{comp.ref}.1"))
        nets2 = set(_nets_for_pin(model, f"{comp.ref}.2"))
        touches_fb = fb_net in nets1 or fb_net in nets2
        if not touches_fb:
            continue
        touches_gnd = bool(nets1 & ground_nets) or bool(nets2 & ground_nets)
        touches_vout = bool(vout_net) and (vout_net in nets1 or vout_net in nets2)
        if touches_vout and not top_ok:
            top_ok = True
            top_ref = comp.ref
            continue
        if touches_gnd and comp.ref != top_ref:
            bottom_ok = True
    return top_ok and bottom_ok


def _has_catch_diode(model: CircuitModel, sw_net: str, ground_nets: set[str]) -> bool:
    """True if a (Schottky) catch diode bridges SW and GND with cathode (pin 1) to SW.

    The diode symbols are pin 1 = K (cathode), pin 2 = A (anode). A freewheel
    catch diode for a buck has its cathode on SW and anode on GND.
    """
    for comp in model.components:
        if comp.symbol not in _DIODE_SYMBOLS:
            continue
        k_nets = set(_nets_for_pin(model, f"{comp.ref}.1"))  # cathode
        a_nets = set(_nets_for_pin(model, f"{comp.ref}.2"))  # anode
        if sw_net in k_nets and bool(a_nets & ground_nets):
            return True
    return False


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
