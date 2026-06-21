"""Tests for the switching-converter tasks (buck + boost).

These pin the HARDEST component-choice + assembly behaviour in the catalog: a
switching converter is only "correct" when MANY interacting parts are present
and wired together. The key proof is COMPLETENESS DISCRIMINATION — a complete
converter must score notably higher than one missing the inductor and feedback
divider.

We build circuits directly with the in-process builder and grade them through
the deterministic verifier with ``use_kicad=False`` (fast + deterministic).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from circuit_agent.data import parts_db
from circuit_agent.dsl.builder import Circuit
from circuit_agent.infra.verifier import verify_design
from circuit_agent.task import TaskSpec, load_task

_TASKS_DIR = Path(__file__).resolve().parent.parent / "tasks"


def _grade(circuit: Circuit, task_name: str) -> float:
    task = load_task(_TASKS_DIR / f"{task_name}.yaml")
    out_dir = tempfile.mkdtemp(prefix="converter-")
    res = verify_design(circuit.to_model(), task, out_dir, use_kicad=False)
    return float(res["reward"]["reward_normalized"])


# --------------------------------------------------------------------------- #
# Task-spec sanity
# --------------------------------------------------------------------------- #
def test_buck_and_boost_load_as_taskspec() -> None:
    """Both new tasks load as TaskSpec; allowed_parts is a subset of PARTS."""
    for name in ("buck_3v3", "boost_5v"):
        task = load_task(_TASKS_DIR / f"{name}.yaml")
        assert isinstance(task, TaskSpec)
        assert task.name == name
        assert task.allowed_parts, f"{name}: no allowed_parts"
        for key in task.allowed_parts:
            assert key in parts_db.PARTS, f"{name}: allowed part {key!r} not in PARTS"


# --------------------------------------------------------------------------- #
# Complete builders (controller + Cin + Cout + inductor + divider + diode)
# --------------------------------------------------------------------------- #
def _complete_buck() -> Circuit:
    c = Circuit("buck_complete", description="Complete 12V->3.3V buck")
    u1 = c.add_part_from_db("U1", "buck_mp1584")
    cin = c.add_part_from_db("C1", "cap_0805_10u", value="10u")
    cout = c.add_part_from_db("C2", "cap_0805_10u", value="10u")
    l1 = c.add_part_from_db("L1", "inductor_10uh_power", value="10uH")
    d1 = c.add_part_from_db("D1", "diode_schottky_sma", value="SS34")
    rtop = c.add_part_from_db("R1", "resistor_0603", value="68k")
    rbot = c.add_part_from_db("R2", "resistor_0603", value="10k")
    c.net("VIN").connect(u1, "1").connect(cin, "1").connect(u1, "5")
    c.net("SW").connect(u1, "2").connect(l1, "1").connect(d1, "1")
    c.net("+3V3").connect(l1, "2").connect(cout, "1").connect(rtop, "1")
    c.net("FB").connect(u1, "4").connect(rtop, "2").connect(rbot, "1")
    c.net("GND").connect(u1, "3").connect(cin, "2").connect(cout, "2").connect(d1, "2").connect(rbot, "2")
    return c


def _incomplete_buck() -> Circuit:
    """A buck MISSING the power inductor AND the feedback divider."""
    c = Circuit("buck_incomplete", description="Buck missing inductor + divider")
    u1 = c.add_part_from_db("U1", "buck_mp1584")
    cin = c.add_part_from_db("C1", "cap_0805_10u", value="10u")
    cout = c.add_part_from_db("C2", "cap_0805_10u", value="10u")
    d1 = c.add_part_from_db("D1", "diode_schottky_sma", value="SS34")
    # NOTE: no inductor, no feedback divider.
    c.net("VIN").connect(u1, "1").connect(cin, "1").connect(u1, "5")
    c.net("SW").connect(u1, "2").connect(d1, "1")
    c.net("+3V3").connect(cout, "1")
    c.net("FB").connect(u1, "4")
    c.net("GND").connect(u1, "3").connect(cin, "2").connect(cout, "2").connect(d1, "2")
    return c


def _complete_boost() -> Circuit:
    c = Circuit("boost_complete", description="Complete 3.3V->5V boost")
    u1 = c.add_part_from_db("U1", "boost_tps61023")
    cin = c.add_part_from_db("C1", "cap_0805_10u", value="10u")
    cout = c.add_part_from_db("C2", "cap_0805_10u", value="10u")
    l1 = c.add_part_from_db("L1", "inductor_4u7_power", value="4.7uH")
    d1 = c.add_part_from_db("D1", "diode_schottky_sma", value="SS34")
    rtop = c.add_part_from_db("R1", "resistor_0603", value="100k")
    rbot = c.add_part_from_db("R2", "resistor_0603", value="33k")
    c.net("VIN").connect(u1, "5").connect(cin, "1").connect(u1, "4").connect(l1, "1")
    c.net("SW").connect(u1, "1").connect(l1, "2").connect(d1, "2")
    c.net("+5V").connect(u1, "6").connect(d1, "1").connect(cout, "1").connect(rtop, "1")
    c.net("FB").connect(u1, "3").connect(rtop, "2").connect(rbot, "1")
    c.net("GND").connect(u1, "2").connect(cin, "2").connect(cout, "2").connect(rbot, "2")
    return c


def _incomplete_boost() -> Circuit:
    """A boost MISSING the power inductor AND the feedback divider."""
    c = Circuit("boost_incomplete", description="Boost missing inductor + divider")
    u1 = c.add_part_from_db("U1", "boost_tps61023")
    cin = c.add_part_from_db("C1", "cap_0805_10u", value="10u")
    cout = c.add_part_from_db("C2", "cap_0805_10u", value="10u")
    d1 = c.add_part_from_db("D1", "diode_schottky_sma", value="SS34")
    c.net("VIN").connect(u1, "5").connect(cin, "1").connect(u1, "4")
    c.net("SW").connect(u1, "1").connect(d1, "2")
    c.net("+5V").connect(u1, "6").connect(d1, "1").connect(cout, "1")
    c.net("FB").connect(u1, "3")
    c.net("GND").connect(u1, "2").connect(cin, "2").connect(cout, "2")
    return c


# --------------------------------------------------------------------------- #
# COMPLETENESS DISCRIMINATION (the key proof)
# --------------------------------------------------------------------------- #
def test_complete_buck_beats_incomplete_buck() -> None:
    """A complete buck must score notably higher than one missing inductor+divider."""
    complete = _grade(_complete_buck(), "buck_3v3")
    incomplete = _grade(_incomplete_buck(), "buck_3v3")
    assert complete > incomplete + 0.05, (
        f"complete buck ({complete}) should beat incomplete ({incomplete}) by a clear margin"
    )


def test_complete_boost_beats_incomplete_boost() -> None:
    """A complete boost must score notably higher than one missing inductor+divider."""
    complete = _grade(_complete_boost(), "boost_5v")
    incomplete = _grade(_incomplete_boost(), "boost_5v")
    assert complete > incomplete + 0.05, (
        f"complete boost ({complete}) should beat incomplete ({incomplete}) by a clear margin"
    )


def test_complete_converters_grade_well() -> None:
    """The hand-written complete builds should grade well (normalized > 0.5)."""
    assert _grade(_complete_buck(), "buck_3v3") > 0.5
    assert _grade(_complete_boost(), "boost_5v") > 0.5
