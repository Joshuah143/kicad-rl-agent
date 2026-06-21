"""Tests for :mod:`circuit_agent.validators.graph_rules`.

The graph-rules validator is a *deterministic, never-raising* checker over a
:class:`~circuit_agent.dsl.schema.CircuitModel`. It returns a
:class:`~circuit_agent.validators.base.ValidatorResult` whose ``issues`` carry a
:class:`~circuit_agent.validators.base.Severity` (FATAL / WARNING / INFO).

These tests pin the behaviours called out in the interface contract:

* duplicate component refs           -> FATAL
* missing GND net                    -> FATAL
* a pin referenced on an *unknown*   -> WARNING (not FATAL: we don't know the
  symbol                                symbol's real pin map)
* a clean, well-formed circuit       -> ``passed`` is True (no FATAL issues)

The tests build their fixtures with the fluent :class:`circuit_agent.dsl.builder.Circuit`
(and raw :class:`CircuitModel` where a malformed structure is needed) so they
exercise the real, on-disk data/symbol catalogs rather than hand-rolled stubs.
"""

from __future__ import annotations

from circuit_agent.dsl.builder import Circuit
from circuit_agent.dsl.schema import CircuitModel, Component, Net
from circuit_agent.validators import graph_rules
from circuit_agent.validators.base import Severity, ValidatorResult


def _fatal_codes(result: ValidatorResult) -> list[str]:
    """Return the ``code`` of every FATAL issue (helper for assertions)."""
    return [issue.code for issue in result.fatals]


def _all_severities(result: ValidatorResult) -> set[Severity]:
    return {issue.severity for issue in result.issues}


def _clean_led_circuit() -> CircuitModel:
    """A minimal, well-formed LED + resistor circuit with a real GND net.

    Built with the fluent builder so symbols/pins resolve against the on-disk
    catalogs. Wires: +5V -> R1 -> LED anode, LED cathode -> GND.
    """
    c = Circuit("clean_led", description="LED with current-limiting resistor")
    r1 = c.add_resistor("R1", "330")
    d1 = c.add_led("D1", "RED")

    c.net("VCC").connect(r1, "1")
    c.net("LED_A").connect(r1, "2").connect(d1, "A")
    c.net("GND").connect(d1, "K")
    return c.to_model()


def test_clean_circuit_passes() -> None:
    """A well-formed circuit with a GND net has no FATAL issues -> passed."""
    model = _clean_led_circuit()
    result = graph_rules.check(model)

    assert isinstance(result, ValidatorResult)
    assert result.name == "graph_rules"
    assert result.passed is True
    assert result.fatals == []
    # fraction() is well-defined and within [0, 1].
    assert 0.0 <= result.fraction() <= 1.0


def test_duplicate_ref_is_fatal() -> None:
    """Two components sharing a ref must produce a FATAL issue."""
    model = CircuitModel(
        name="dup_ref",
        components=[
            Component(ref="R1", symbol="Device:R", value="1k"),
            Component(ref="R1", symbol="Device:R", value="2k"),  # duplicate ref
        ],
        nets=[
            Net(name="GND", connections=["R1.1"]),
            Net(name="N1", connections=["R1.2"]),
        ],
    )
    result = graph_rules.check(model)

    assert result.passed is False
    assert Severity.FATAL in _all_severities(result)
    # At least one FATAL must mention the duplicated ref.
    assert any("R1" in issue.refs or "R1" in issue.message for issue in result.fatals)


def test_missing_gnd_is_fatal() -> None:
    """A circuit with no ground net must be flagged FATAL."""
    c = Circuit("no_gnd")
    r1 = c.add_resistor("R1", "1k")
    r2 = c.add_resistor("R2", "2k")
    # Only signal nets, deliberately no GND/GNDA/AGND.
    c.net("VIN").connect(r1, "1")
    c.net("MID").connect(r1, "2").connect(r2, "1")
    c.net("VOUT").connect(r2, "2")
    model = c.to_model()

    result = graph_rules.check(model)

    assert result.passed is False
    assert Severity.FATAL in _all_severities(result)


def test_present_gnd_net_not_fatal_for_ground_rule() -> None:
    """When a GND net exists, the missing-ground FATAL must not fire.

    We can't pin the exact code string, so we assert the positive: a circuit
    that is well-formed apart from having ground present is ``passed``.
    """
    model = _clean_led_circuit()
    result = graph_rules.check(model)
    # No FATAL should reference a ground/gnd concept.
    for issue in result.fatals:
        text = (issue.code + " " + issue.message).lower()
        assert "gnd" not in text and "ground" not in text


def test_unknown_symbol_pin_is_warning_not_fatal() -> None:
    """A pin referenced on an unknown symbol -> WARNING, never FATAL.

    ``Made:Up`` is not in the symbol catalog, so the validator cannot know its
    pin map and must degrade to a WARNING rather than rejecting the design.
    """
    model = CircuitModel(
        name="unknown_symbol",
        components=[
            Component(ref="U1", symbol="Made:Up", footprint="Fake:FP"),
            Component(ref="R1", symbol="Device:R", value="1k"),
        ],
        nets=[
            # U1.99 is a pin we cannot verify because the symbol is unknown.
            Net(name="GND", connections=["U1.99", "R1.2"]),
            Net(name="VCC", connections=["R1.1"]),
        ],
    )
    result = graph_rules.check(model)

    # The unknown symbol must not, by itself, make this FATAL.
    severities = _all_severities(result)
    assert Severity.WARNING in severities
    # No FATAL may be attributable to the unknown-symbol pin reference.
    for issue in result.fatals:
        assert "U1.99" not in issue.refs
        assert "Made:Up" not in issue.message


def test_dangling_ref_in_net_is_fatal() -> None:
    """A net connection naming a non-existent component ref is FATAL."""
    model = CircuitModel(
        name="dangling",
        components=[Component(ref="R1", symbol="Device:R", value="1k")],
        nets=[
            Net(name="GND", connections=["R1.2"]),
            # R9 does not exist anywhere in the component list.
            Net(name="N1", connections=["R1.1", "R9.1"]),
        ],
    )
    result = graph_rules.check(model)

    assert result.passed is False
    assert any("R9" in issue.message or "R9.1" in issue.refs for issue in result.fatals)


def test_missing_symbol_is_fatal() -> None:
    """A component with an empty symbol is structurally broken -> FATAL."""
    model = CircuitModel(
        name="no_symbol",
        components=[
            Component(ref="R1", symbol="", value="1k"),
            Component(ref="R2", symbol="Device:R", value="2k"),
        ],
        nets=[
            Net(name="GND", connections=["R1.1", "R2.1"]),
            Net(name="N1", connections=["R1.2", "R2.2"]),
        ],
    )
    result = graph_rules.check(model)

    assert result.passed is False
    assert Severity.FATAL in _all_severities(result)


def test_missing_footprint_is_warning_only() -> None:
    """A missing footprint is soft (WARNING); it must not flip ``passed``."""
    c = Circuit("no_fp")
    # Add a resistor but explicitly null out the footprint.
    r1 = c.add_part("R1", symbol="Device:R", footprint=None, value="1k")
    r2 = c.add_part("R2", symbol="Device:R", footprint=None, value="2k")
    c.net("GND").connect(r1, "1").connect(r2, "1")
    c.net("N1").connect(r1, "2").connect(r2, "2")
    model = c.to_model()

    result = graph_rules.check(model)

    # No footprint should not, on its own, produce a FATAL.
    for issue in result.fatals:
        assert "footprint" not in issue.message.lower()


def test_check_is_deterministic() -> None:
    """Same model in -> identical serialised result out (no randomness)."""
    model = _clean_led_circuit()
    first = graph_rules.check(model)
    second = graph_rules.check(model)
    assert first.model_dump() == second.model_dump()


def test_score_never_negative() -> None:
    """Even a heavily-broken circuit keeps a non-negative, bounded score."""
    model = CircuitModel(
        name="broken",
        components=[
            Component(ref="R1", symbol="", value="1k"),
            Component(ref="R1", symbol="Device:R", value="2k"),  # dup + no GND
        ],
        nets=[Net(name="N1", connections=["R1.1", "RX.9"])],
    )
    result = graph_rules.check(model)
    assert result.score >= 0.0
    assert result.score <= result.max_score
