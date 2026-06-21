"""Tests for the Pydantic v2 DSL schema (``circuit_agent.dsl.schema``).

Covers:
- A well-formed circuit dict validates into a :class:`CircuitModel`.
- :class:`Constraint` folds flat extra keys into ``params``.
- ``extra="forbid"`` rejects unknown :class:`Component` fields.
- ``split_refpin`` parses ``"REF.PIN"`` strings.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from circuit_agent.dsl.schema import (
    CircuitModel,
    Component,
    Constraint,
    Net,
    PackageType,
    split_refpin,
)


def _good_circuit_dict() -> dict:
    """A minimal but well-formed circuit dict used across several tests."""
    return {
        "name": "led_resistor",
        "description": "A current-limited LED",
        "components": [
            {
                "ref": "R1",
                "symbol": "Device:R",
                "footprint": "Resistor_SMD:R_0603_1608Metric",
                "value": "330",
                "package_type": "SMD",
            },
            {
                "ref": "D1",
                "symbol": "Device:LED",
                "value": "LED",
            },
        ],
        "nets": [
            {"name": "VCC", "connections": ["R1.1"]},
            {"name": "GND", "connections": ["D1.K"]},
            {"name": "N1", "connections": ["R1.2", "D1.A"]},
        ],
        "constraints": [
            {"type": "max_current", "max_ma": 20},
        ],
    }


def test_circuit_model_validates_good_dict() -> None:
    """A complete, valid dict round-trips into a CircuitModel."""
    model = CircuitModel.model_validate(_good_circuit_dict())

    assert model.name == "led_resistor"
    assert len(model.components) == 2
    assert len(model.nets) == 3

    # Helpers behave as documented.
    assert model.component_refs() == {"R1", "D1"}
    assert model.find_component("R1") is not None
    assert model.find_component("R1").symbol == "Device:R"
    assert model.find_component("NOPE") is None
    assert model.net_by_name("GND") is not None
    assert model.net_by_name("GND").connections == ["D1.K"]
    assert model.net_by_name("missing") is None


def test_package_type_coerced_from_string() -> None:
    """A string package_type is coerced into the PackageType enum."""
    comp = Component(ref="R1", symbol="Device:R", package_type="SMD")
    assert comp.package_type is PackageType.SMD

    # The enum default applies when omitted.
    comp2 = Component(ref="R2", symbol="Device:R")
    assert comp2.package_type is PackageType.SMD


def test_component_ref_stripped_and_nonempty() -> None:
    """ref is stripped; blank/whitespace-only refs are rejected."""
    comp = Component(ref="  R1  ", symbol="Device:R")
    assert comp.ref == "R1"

    with pytest.raises(ValidationError):
        Component(ref="   ", symbol="Device:R")


def test_constraint_folds_flat_extras_into_params() -> None:
    """Flat keys other than type/params are merged into params."""
    c = Constraint.model_validate(
        {
            "type": "usb_c_sink_requires_rd",
            "cc_pins": ["A5", "B5"],
            "rd_value": "5.1k",
        }
    )
    assert c.type == "usb_c_sink_requires_rd"
    assert c.params == {"cc_pins": ["A5", "B5"], "rd_value": "5.1k"}


def test_constraint_merges_explicit_params_with_flat_extras() -> None:
    """Explicit params and flat extras both end up in params."""
    c = Constraint.model_validate(
        {
            "type": "pullups",
            "params": {"rail": "+3V3"},
            "nets": ["SDA", "SCL"],
        }
    )
    assert c.type == "pullups"
    assert c.params["rail"] == "+3V3"
    assert c.params["nets"] == ["SDA", "SCL"]


def test_component_forbids_unknown_fields() -> None:
    """Component uses extra='forbid' so unknown keys are rejected."""
    with pytest.raises(ValidationError):
        Component(ref="R1", symbol="Device:R", bogus_field="nope")


def test_circuit_model_forbids_unknown_fields() -> None:
    """CircuitModel uses extra='forbid' as well."""
    bad = _good_circuit_dict()
    bad["unexpected"] = 123
    with pytest.raises(ValidationError):
        CircuitModel.model_validate(bad)


def test_net_defaults() -> None:
    """Net connections default to an empty list."""
    net = Net(name="GND")
    assert net.connections == []
    assert net.net_class is None


def test_split_refpin_basic() -> None:
    """split_refpin parses on the first dot."""
    assert split_refpin("J1.A4") == ("J1", "A4")
    assert split_refpin("R1.2") == ("R1", "2")


def test_split_refpin_first_dot_only() -> None:
    """Only the first dot is the separator; later dots stay in the pin."""
    ref, pin = split_refpin("U1.PB1.alt")
    assert ref == "U1"
    assert pin == "PB1.alt"


def test_split_refpin_requires_dot() -> None:
    """A connection string without a dot raises ValueError."""
    with pytest.raises(ValueError):
        split_refpin("R1")
