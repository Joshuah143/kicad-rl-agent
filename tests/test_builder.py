"""Tests for the fluent circuit builder (``circuit_agent.dsl.builder``).

Covers:
- Building a circuit via Circuit + add_resistor/add_led + net().connect().
- to_model() yields the expected refs and nets.
- add_resistor pulls a default footprint from the parts database.
"""

from __future__ import annotations

from circuit_agent.dsl.builder import Circuit
from circuit_agent.dsl.schema import CircuitModel, PackageType
from circuit_agent.data import parts_db


def test_build_led_resistor_circuit() -> None:
    """A small LED + resistor circuit builds into the expected model."""
    c = Circuit("led_resistor", description="A current-limited LED")
    r1 = c.add_resistor("R1", "330")
    d1 = c.add_led("D1")

    # net().connect() is chainable and accepts part handles or string refs.
    c.net("VCC").connect(r1, "1")
    c.net("MID").connect(r1, "2").connect(d1, "A")
    c.net("GND").connect(d1, "K")

    model = c.to_model()
    assert isinstance(model, CircuitModel)
    assert model.name == "led_resistor"

    assert model.component_refs() == {"R1", "D1"}

    r = model.find_component("R1")
    assert r is not None
    assert r.symbol == "Device:R"
    assert r.value == "330"

    d = model.find_component("D1")
    assert d is not None
    assert d.symbol == "Device:LED"

    # Nets carry the expected REF.PIN connection strings.
    assert model.net_by_name("VCC").connections == ["R1.1"]
    assert model.net_by_name("MID").connections == ["R1.2", "D1.A"]
    assert model.net_by_name("GND").connections == ["D1.K"]


def test_add_resistor_pulls_default_footprint_from_parts_db() -> None:
    """When footprint is omitted, add_resistor uses the parts_db 0603 default."""
    expected = parts_db.resolve_part("resistor_0603")
    # The fixture catalog must know about the 0603 resistor for this test.
    assert expected, "parts_db.resolve_part('resistor_0603') returned no spec"

    c = Circuit("r")
    c.add_resistor("R1", "10k")
    model = c.to_model()

    r1 = model.find_component("R1")
    assert r1 is not None
    assert r1.footprint == expected["footprint"]


def test_add_capacitor_defaults() -> None:
    """add_capacitor uses Device:C and the cap_0603_100n defaults."""
    c = Circuit("cap")
    c.add_capacitor("C1", "100n")
    model = c.to_model()

    c1 = model.find_component("C1")
    assert c1 is not None
    assert c1.symbol == "Device:C"
    assert c1.value == "100n"


def test_net_get_or_create_is_idempotent() -> None:
    """Calling net() twice with the same name reuses the same Net."""
    c = Circuit("net")
    r1 = c.add_resistor("R1", "1k")
    c.net("SIG").connect(r1, "1")
    c.net("SIG").connect(r1, "2")

    model = c.to_model()
    sig_nets = [n for n in model.nets if n.name == "SIG"]
    assert len(sig_nets) == 1
    assert sig_nets[0].connections == ["R1.1", "R1.2"]


def test_connect_convenience_with_refpins() -> None:
    """Circuit.connect attaches pre-formed REF.PIN strings and is chainable."""
    c = Circuit("conn")
    c.add_resistor("R1", "1k")
    c.add_led("D1")
    returned = c.connect("OUT", "R1.2", "D1.A")
    assert returned is c

    model = c.to_model()
    assert model.net_by_name("OUT").connections == ["R1.2", "D1.A"]


def test_add_part_explicit_fields() -> None:
    """add_part records explicit fields and extra attributes."""
    c = Circuit("p")
    handle = c.add_part(
        "U1",
        symbol="Regulator_Linear:AP2112K-3.3",
        footprint="Package_TO_SOT_SMD:SOT-23-5",
        value="AP2112K-3.3",
        role="ldo",
        package_type="SMD",
        custom_attr="x",
    )
    assert handle.ref == "U1"

    model = c.to_model()
    u1 = model.find_component("U1")
    assert u1 is not None
    assert u1.symbol == "Regulator_Linear:AP2112K-3.3"
    assert u1.role == "ldo"
    assert u1.package_type is PackageType.SMD
    assert u1.attributes.get("custom_attr") == "x"


def test_to_dict_matches_model_dump() -> None:
    """to_dict() equals to_model().model_dump()."""
    c = Circuit("d")
    c.add_resistor("R1", "1k")
    assert c.to_dict() == c.to_model().model_dump()


def test_from_model_round_trip() -> None:
    """from_model reconstructs an equivalent builder/model."""
    c = Circuit("rt", description="round trip")
    c.add_resistor("R1", "1k")
    c.add_led("D1")
    c.net("OUT").connect("R1", "2").connect("D1", "A")

    model = c.to_model()
    rebuilt = Circuit.from_model(model)
    assert rebuilt.to_model().model_dump() == model.model_dump()
