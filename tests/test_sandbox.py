"""Tests for the program sandbox (``circuit_agent.dsl.sandbox``).

Covers:
- A valid program defining build() -> Circuit produces a CircuitModel.
- ``import os`` (and friends) are rejected with SandboxError.
- A program that never defines build() raises SandboxError.
"""

from __future__ import annotations

import pytest

from circuit_agent.dsl.sandbox import (
    SandboxError,
    run_program,
    validate_program_ast,
)
from circuit_agent.dsl.schema import CircuitModel


VALID_PROGRAM = """
def build():
    c = Circuit("led_resistor", description="A current-limited LED")
    r1 = c.add_resistor("R1", "330")
    d1 = c.add_led("D1")
    c.net("VCC").connect(r1, "1")
    c.net("MID").connect(r1, "2").connect(d1, "A")
    c.net("GND").connect(d1, "K")
    return c
"""


def test_valid_program_runs_to_model() -> None:
    """A well-formed program returns a validated CircuitModel."""
    model = run_program(VALID_PROGRAM)
    assert isinstance(model, CircuitModel)
    assert model.name == "led_resistor"
    assert model.component_refs() == {"R1", "D1"}
    assert model.net_by_name("MID").connections == ["R1.2", "D1.A"]


def test_import_rejected_by_ast() -> None:
    """validate_program_ast rejects any import statement."""
    bad = "import os\n\ndef build():\n    return Circuit('x')\n"
    with pytest.raises(SandboxError):
        validate_program_ast(bad)


def test_import_rejected_by_run_program() -> None:
    """run_program rejects imports before ever executing the code."""
    bad = "import os\n\ndef build():\n    return Circuit('x')\n"
    with pytest.raises(SandboxError):
        run_program(bad)


def test_from_import_rejected() -> None:
    """from-imports are rejected as well."""
    bad = "from os import path\n\ndef build():\n    return Circuit('x')\n"
    with pytest.raises(SandboxError):
        validate_program_ast(bad)


def test_dunder_attribute_access_rejected() -> None:
    """Accessing dunder attributes is blocked by the AST validator."""
    bad = "def build():\n    Circuit.__class__\n    return Circuit('x')\n"
    with pytest.raises(SandboxError):
        validate_program_ast(bad)


def test_denied_builtin_name_rejected() -> None:
    """Names in DENIED_NAMES (e.g. eval) are blocked."""
    bad = "def build():\n    eval('1+1')\n    return Circuit('x')\n"
    with pytest.raises(SandboxError):
        validate_program_ast(bad)


def test_dangerous_module_name_rejected() -> None:
    """Bare references to dangerous module names are blocked."""
    bad = "def build():\n    subprocess\n    return Circuit('x')\n"
    with pytest.raises(SandboxError):
        validate_program_ast(bad)


def test_program_without_build_raises() -> None:
    """A program that never defines build() fails."""
    bad = "x = Circuit('x')\n"
    with pytest.raises(SandboxError):
        run_program(bad)


def test_validate_allows_control_flow() -> None:
    """Loops, conditionals, comprehensions, and assignment are allowed."""
    ok = """
def build():
    c = Circuit("grid")
    for i in range(3):
        ref = "R" + str(i + 1)
        c.add_resistor(ref, "1k")
    refs = [f"R{i+1}.1" for i in range(3)]
    if refs:
        c.connect("BUS", *refs)
    return c
"""
    # Should not raise.
    validate_program_ast(ok)
    model = run_program(ok)
    assert isinstance(model, CircuitModel)
    assert model.component_refs() == {"R1", "R2", "R3"}
