"""Catalog consistency tests for the expanded parts/symbols/footprints DB.

These pin the invariants that make component choice a meaningful lever:

* Every ``PARTS`` entry resolves to a known symbol AND a known footprint.
* ``parts_by_role`` returns multiple ALTERNATIVES for the staple roles
  (resistor / cap / led / ldo) so tasks can force a choice.
* Footprint solderability is consistent with the chip size class
  (0402 not hand-solderable; 0603/0805/1206/THT hand-solderable).
"""

from __future__ import annotations

from circuit_agent.data import footprints, parts_db, symbols


def test_every_part_has_known_symbol() -> None:
    """Each catalog part references a symbol that exists in the symbol DB."""
    for key, spec in parts_db.PARTS.items():
        assert symbols.has_symbol(spec.symbol), f"{key}: unknown symbol {spec.symbol!r}"


def test_every_part_has_known_footprint() -> None:
    """Each catalog part references a footprint that exists in the footprint DB."""
    for key, spec in parts_db.PARTS.items():
        if spec.footprint is None:
            continue
        assert footprints.has_footprint(spec.footprint), (
            f"{key}: unknown footprint {spec.footprint!r}"
        )


def test_existing_part_keys_still_present() -> None:
    """The original catalog keys must keep working."""
    for key in (
        "resistor_0402",
        "resistor_0603",
        "resistor_0805",
        "led_0603",
        "led_0805",
        "cap_0603_100n",
        "cap_0805_1u",
        "cap_0805_10u",
        "usb_c_receptacle_hro",
        "ldo_3v3_ap2112",
        "test_point_smd",
        "mcu_rp2040",
        "mcu_esp32",
        "mcu_stm32",
        "i2c_sensor_generic",
        "motor_driver_drv8833",
        "resistor_tht",
        "led_tht",
    ):
        assert key in parts_db.PARTS, f"existing key {key} disappeared"


def test_parts_by_role_has_alternatives() -> None:
    """The staple roles must offer more than one alternative."""
    for role in ("resistor", "cap", "led", "ldo"):
        alts = parts_db.parts_by_role(role)
        assert len(alts) > 1, f"role {role!r} has too few alternatives: {alts}"


def test_ldo_family_trades_off() -> None:
    """The 3.3V LDO family spans a real cost / availability spread."""
    ldos = parts_db.parts_by_role("ldo")
    costs = {k: parts_db.PARTS[k].unit_cost_usd for k in ldos}
    avails = {k: parts_db.PARTS[k].availability_score for k in ldos}
    # The cheapest is meaningfully cheaper than the priciest.
    assert max(costs.values()) > min(costs.values())
    assert max(avails.values()) > min(avails.values())
    # xc6206 is the cheapest, sot223 the priciest, by design.
    assert min(costs, key=costs.get) == "ldo_3v3_xc6206"
    assert max(costs, key=costs.get) == "ldo_3v3_sot223"


def test_parts_with_symbol() -> None:
    """parts_with_symbol groups alternatives sharing a KiCad symbol."""
    rs = parts_db.parts_with_symbol("Device:R")
    assert "resistor_0402" in rs and "resistor_0603" in rs


def test_footprint_solderability_matches_size_class() -> None:
    """0402 is not hand-solderable; 0603/0805/1206/THT are."""
    for fp in footprints.FOOTPRINTS.values():
        if fp.size_class == "0402":
            assert fp.hand_solderable is False, f"{fp.fp_id} 0402 must not be hand-solderable"
        elif fp.size_class in ("0603", "0805", "1206"):
            assert fp.hand_solderable is True, f"{fp.fp_id} {fp.size_class} must be hand-solderable"
        if fp.package_type.value == "THT":
            assert fp.hand_solderable is True, f"{fp.fp_id} THT must be hand-solderable"


def test_size_class_rank_ordering() -> None:
    """Finer chip classes rank lower than coarser ones; non-chip -> None."""
    rank = footprints.size_class_rank
    assert rank("0402") < rank("0603") < rank("0805") < rank("1206")
    assert rank("THT") is None
    assert rank(None) is None


def test_resolve_part_roundtrips_new_keys() -> None:
    """resolve_part returns usable kwargs for new keys (symbol present)."""
    for key in ("ldo_3v3_xc6206", "mosfet_p_ao3401_sot23", "qspi_flash_w25q", "barrel_jack_dc"):
        kw = parts_db.resolve_part(key)
        assert kw and kw.get("symbol") and symbols.has_symbol(kw["symbol"])
