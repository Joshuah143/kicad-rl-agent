"""Reward must DISCRIMINATE between part choices on tradeoff tasks.

Two electrically-valid designs that differ only in part choice should score
DIFFERENTLY, with the ordering matching the task's emphasis:

(a) size-emphasis task   -> all-0402 build scores HIGHER than all-1206 build.
(b) min_hand_solderable  -> 0402 build scores LOWER than the 0805 build.
(c) cost-emphasis task   -> cheaper LDO build scores HIGHER than pricier LDO.

We build circuits directly with the in-process builder and grade them through
the deterministic verifier with ``use_kicad=False`` (fast + deterministic).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from circuit_agent.data import symbols
from circuit_agent.dsl.builder import Circuit
from circuit_agent.infra.verifier import verify_design
from circuit_agent.task import load_task

_TASKS_DIR = Path(__file__).resolve().parent.parent / "tasks"


def _grade(circuit: Circuit, task_name: str) -> float:
    task = load_task(_TASKS_DIR / f"{task_name}.yaml")
    out_dir = tempfile.mkdtemp(prefix="disc-")
    res = verify_design(circuit.to_model(), task, out_dir, use_kicad=False)
    return float(res["reward"]["reward_normalized"])


def _led_circuit(res_key: str, led_key: str) -> Circuit:
    c = Circuit("led_choice", description="LED with a series resistor")
    r = c.add_part_from_db("R1", res_key, value="330")
    d = c.add_part_from_db("D1", led_key, value="RED")
    c.net("VCC").connect(r, "1")
    c.net("LED_A").connect(r, "2").connect(d, "A")
    c.net("GND").connect(d, "K")
    return c


def _ldo_circuit(ldo_key: str) -> Circuit:
    c = Circuit("ldo_choice", description="3.3V LDO with in/out caps")
    u = c.add_part_from_db("U1", ldo_key)
    cin = c.add_part_from_db("C1", "cap_0603_1u", value="1u")
    cout = c.add_part_from_db("C2", "cap_0603_1u", value="1u")
    pins = {p.name: p.number for p in symbols.symbol_pins(c._components[0].symbol)}
    gnd_pin = pins.get("GND", "2")
    c.net("+5V").connect(u, pins["VIN"]).connect(cin, "1")
    c.net("GND").connect(u, gnd_pin).connect(cin, "2").connect(cout, "2")
    c.net("+3V3").connect(u, pins["VOUT"]).connect(cout, "1")
    return c


def test_size_task_prefers_smaller_packages() -> None:
    """(a) On led_blinky_tiny, all-0402 beats all-1206."""
    small = _grade(_led_circuit("resistor_0402", "led_0402"), "led_blinky_tiny")
    big = _grade(_led_circuit("resistor_1206", "led_1206"), "led_blinky_tiny")
    assert small > big, f"expected 0402 ({small}) > 1206 ({big})"


def test_handsolder_task_penalizes_fine_pitch() -> None:
    """(b) On handsolder_led (min 0805), the 0402 build scores lower than 0805."""
    fine = _grade(_led_circuit("resistor_0402", "led_0402"), "handsolder_led")
    ok = _grade(_led_circuit("resistor_0805", "led_0805"), "handsolder_led")
    assert ok > fine, f"expected 0805 ({ok}) > 0402 ({fine})"


def test_cost_task_prefers_cheaper_ldo() -> None:
    """(c) On ldo_3v3_lowcost, the cheap xc6206 beats the pricey sot223."""
    cheap = _grade(_ldo_circuit("ldo_3v3_xc6206"), "ldo_3v3_lowcost")
    pricey = _grade(_ldo_circuit("ldo_3v3_sot223"), "ldo_3v3_lowcost")
    assert cheap > pricey, f"expected xc6206 ({cheap}) > sot223 ({pricey})"


def test_availability_task_prefers_high_availability_ldo() -> None:
    """On ldo_3v3_highavail, the high-availability xc6206 beats the low-avail sot223."""
    high = _grade(_ldo_circuit("ldo_3v3_xc6206"), "ldo_3v3_highavail")
    low = _grade(_ldo_circuit("ldo_3v3_sot223"), "ldo_3v3_highavail")
    assert high > low, f"expected xc6206 ({high}) > sot223 ({low})"
