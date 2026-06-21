"""Tests for :mod:`circuit_agent.validators.electrical_rules`.

The electrical-rules validator applies heuristic, domain-specific checks on top
of the structural graph rules. It is deterministic and *tolerant*: detection
heuristics that might mis-fire prefer WARNING over FATAL, except for the small
set of explicit FATALs in the contract (notably a USB-C sink missing a 5.1k Rd
pulldown on a CC pin, and a +5V/+3V3 short).

``electrical_rules.check`` takes ``(model, task)`` — the :class:`TaskSpec`
provides preferences/metadata the rules may consult.

Covered behaviours:

* USB-C without an Rd pulldown on CC2 -> FATAL whose message names ``CC2``.
* A resistor with an unparseable value -> WARNING (never FATAL).
* The reference ``usb_c_5v_led`` example (correct 5.1k Rd on CC1 and CC2)
  -> no electrical FATALs.
"""

from __future__ import annotations

import pytest

from circuit_agent.dsl.builder import Circuit
from circuit_agent.dsl.examples import EXAMPLE_BUILDERS, get_example_program, list_examples
from circuit_agent.dsl.sandbox import run_program
from circuit_agent.dsl.schema import CircuitModel
from circuit_agent.task import TaskSpec
from circuit_agent.validators import electrical_rules
from circuit_agent.validators.base import Severity, ValidatorResult


def _bare_task(name: str = "t") -> TaskSpec:
    """A minimal TaskSpec; the electrical rules read it but tolerate emptiness."""
    return TaskSpec(name=name)


def _fatal_text(result: ValidatorResult) -> str:
    """Concatenate all FATAL messages + refs for substring assertions."""
    chunks: list[str] = []
    for issue in result.fatals:
        chunks.append(issue.message)
        chunks.extend(issue.refs)
    return " ".join(chunks)


def _usb_c_builder_name() -> str:
    """Resolve the USB-C example builder key (be lenient about naming)."""
    if "usb_c_5v_led" in EXAMPLE_BUILDERS:
        return "usb_c_5v_led"
    for key in EXAMPLE_BUILDERS:
        if "usb" in key.lower():
            return key
    pytest.skip("no USB-C example builder available")


def _usb_c_model_correct() -> CircuitModel:
    """The reference USB-C circuit with correct Rd pulldowns on CC1 and CC2."""
    name = _usb_c_builder_name()
    circuit = EXAMPLE_BUILDERS[name]()
    assert isinstance(circuit, Circuit)
    return circuit.to_model()


# --------------------------------------------------------------------------- #
# USB-C sink rules
# --------------------------------------------------------------------------- #
def test_usb_c_reference_has_no_electrical_fatals() -> None:
    """The hand-written USB-C example must satisfy the CC Rd FATAL rules."""
    model = _usb_c_model_correct()
    result = electrical_rules.check(model, _bare_task("usb_c_5v_led"))

    assert isinstance(result, ValidatorResult)
    assert result.name == "electrical_rules"
    assert result.fatals == [], f"unexpected FATALs: {_fatal_text(result)}"
    assert result.passed is True


def test_usb_c_missing_cc2_pulldown_is_fatal_naming_cc2() -> None:
    """Drop the CC2 Rd pulldown -> a FATAL whose message references CC2.

    We construct a USB-C sink by hand with a proper 5.1k Rd on CC1 only, so the
    only thing wrong is the missing CC2 pulldown — isolating the rule.
    """
    c = Circuit("usb_c_missing_cc2", description="USB-C sink, CC2 Rd omitted")
    usb = c.add_part(
        "J1",
        symbol="Connector:USB_C_Receptacle_USB2.0",
        footprint="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
        value="USB-C",
    )
    # 5.1k Rd from CC1 -> GND (present, correct).
    r_cc1 = c.add_resistor("R1", "5.1k", role="usb_cc_rd")
    # Note: deliberately NO resistor on CC2.

    c.net("VBUS").connect(usb, "A4").connect(usb, "B4")
    c.net("GND").connect(usb, "A1").connect(usb, "A12").connect(r_cc1, "2")
    c.net("CC1").connect(usb, "A5").connect(r_cc1, "1")
    c.net("CC2").connect(usb, "B5")  # floating CC2, no Rd
    model = c.to_model()

    result = electrical_rules.check(model, _bare_task("usb_c_missing_cc2"))

    assert result.passed is False
    text = _fatal_text(result)
    assert "CC2" in text, f"expected a FATAL naming CC2, got: {text!r}"


def test_usb_c_with_both_pulldowns_no_fatal() -> None:
    """Hand-built USB-C with 5.1k Rd on both CC1 and CC2 -> no FATALs."""
    c = Circuit("usb_c_ok", description="USB-C sink with both Rd pulldowns")
    usb = c.add_part(
        "J1",
        symbol="Connector:USB_C_Receptacle_USB2.0",
        footprint="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
        value="USB-C",
    )
    r_cc1 = c.add_resistor("R1", "5.1k", role="usb_cc_rd")
    r_cc2 = c.add_resistor("R2", "5.1k", role="usb_cc_rd")

    c.net("VBUS").connect(usb, "A4").connect(usb, "B4")
    c.net("GND").connect(usb, "A1").connect(r_cc1, "2").connect(r_cc2, "2")
    c.net("CC1").connect(usb, "A5").connect(r_cc1, "1")
    c.net("CC2").connect(usb, "B5").connect(r_cc2, "1")
    model = c.to_model()

    result = electrical_rules.check(model, _bare_task("usb_c_ok"))
    assert result.fatals == [], f"unexpected FATALs: {_fatal_text(result)}"


# --------------------------------------------------------------------------- #
# Value parsing
# --------------------------------------------------------------------------- #
def test_bad_resistor_value_is_warning_not_fatal() -> None:
    """An unparseable resistor value yields a WARNING, never a FATAL."""
    c = Circuit("bad_res")
    r1 = c.add_resistor("R1", "not-a-resistance")
    r2 = c.add_resistor("R2", "1k")
    c.net("GND").connect(r1, "1").connect(r2, "1")
    c.net("N1").connect(r1, "2").connect(r2, "2")
    model = c.to_model()

    result = electrical_rules.check(model, _bare_task("bad_res"))

    severities = {issue.severity for issue in result.issues}
    assert Severity.WARNING in severities
    # The bad value must not push the design to FATAL.
    assert "not-a-resistance" not in _fatal_text(result)
    for issue in result.fatals:
        assert "R1" not in issue.refs or Severity.FATAL != issue.severity


def test_good_resistor_value_no_value_warning() -> None:
    """A parseable resistor value should not raise a bad-value WARNING for it."""
    c = Circuit("good_res")
    r1 = c.add_resistor("R1", "4k7")  # 4.7k shorthand
    r2 = c.add_resistor("R2", "10R")
    c.net("GND").connect(r1, "1").connect(r2, "1")
    c.net("N1").connect(r1, "2").connect(r2, "2")
    model = c.to_model()

    result = electrical_rules.check(model, _bare_task("good_res"))
    for issue in result.warnings:
        # No warning should claim R1/R2 have an unparseable value.
        if "R1" in issue.refs or "R2" in issue.refs:
            assert "value" not in issue.message.lower() or "rd" in issue.message.lower()


# --------------------------------------------------------------------------- #
# 5V / 3V3 short
# --------------------------------------------------------------------------- #
def test_five_volt_to_three_volt_short_is_fatal() -> None:
    """A single net joining a +5V and a +3V3 power symbol is a FATAL short."""
    model = CircuitModel.model_validate(
        {
            "name": "rail_short",
            "components": [
                {"ref": "PW5", "symbol": "power:+5V", "package_type": "VIRTUAL"},
                {"ref": "PW3", "symbol": "power:+3V3", "package_type": "VIRTUAL"},
                {"ref": "PWG", "symbol": "power:GND", "package_type": "VIRTUAL"},
                {"ref": "R1", "symbol": "Device:R", "value": "1k"},
            ],
            "nets": [
                # Both rails tied to ONE net -> short.
                {"name": "RAIL", "connections": ["PW5.1", "PW3.1", "R1.1"]},
                {"name": "GND", "connections": ["PWG.1", "R1.2"]},
            ],
        }
    )
    result = electrical_rules.check(model, _bare_task("rail_short"))
    assert result.passed is False
    assert Severity.FATAL in {issue.severity for issue in result.issues}


# --------------------------------------------------------------------------- #
# Determinism + graceful degradation
# --------------------------------------------------------------------------- #
def test_check_is_deterministic() -> None:
    """Same (model, task) in -> identical serialised result out."""
    model = _usb_c_model_correct()
    task = _bare_task("usb_c_5v_led")
    first = electrical_rules.check(model, task)
    second = electrical_rules.check(model, task)
    assert first.model_dump() == second.model_dump()


def test_empty_circuit_does_not_raise() -> None:
    """An empty/irrelevant circuit must be handled without raising."""
    model = CircuitModel(name="empty")
    result = electrical_rules.check(model, _bare_task("empty"))
    assert isinstance(result, ValidatorResult)
    # No USB-C/I2C/LDO/MCU present -> those rules simply skip; no FATAL.
    assert result.fatals == []


def test_usb_c_example_program_runs_through_sandbox_clean() -> None:
    """The USB-C example *program string* also passes the electrical rules.

    This exercises the example as the model would actually emit it (a build()
    program run through the sandbox), not just the in-process builder.
    """
    examples = list_examples()
    name = next((n for n in examples if "usb" in n.lower()), None)
    if name is None:
        pytest.skip("no USB-C example program available")

    code = get_example_program(name)
    model = run_program(code)
    result = electrical_rules.check(model, _bare_task(name))
    assert result.fatals == [], f"unexpected FATALs: {_fatal_text(result)}"
