"""Pydantic v2 models — the validated representation of a circuit.

These models are the canonical data structures the rest of the system operates
on. ``CircuitModel`` is produced by the fluent builder, the sandbox and by
loading JSON; it is consumed by the validators, the reward and the KiCad
compiler.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PackageType(str, Enum):
    """Physical packaging family for a component."""

    SMD = "SMD"
    THT = "THT"
    MIXED = "MIXED"
    VIRTUAL = "VIRTUAL"  # test points, power flags, mounting holes, etc.


class Component(BaseModel):
    """A single placed component in the circuit."""

    model_config = ConfigDict(extra="forbid")

    ref: str  # e.g. "R1"
    symbol: str  # KiCad lib id, e.g. "Device:R"
    footprint: Optional[str] = None
    value: Optional[str] = None
    role: Optional[str] = None  # functional role, e.g. "usb_cc_rd"
    package_type: PackageType = PackageType.SMD
    unit_cost_usd: Optional[float] = None
    availability_score: Optional[float] = None  # 0..1
    package_dims_mm: Optional[tuple[float, float]] = None
    datasheet: Optional[str] = None
    source_ref: Optional[str] = None
    pins: Optional[list[str]] = None  # optional explicit pin numbers/names
    attributes: dict = Field(default_factory=dict)

    @field_validator("ref")
    @classmethod
    def _strip_ref(cls, v: str) -> str:
        """Strip whitespace and reject empty refs."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Component.ref must be non-empty")
        return stripped


class Net(BaseModel):
    """A named electrical net and the pins connected to it."""

    model_config = ConfigDict(extra="forbid")

    name: str
    connections: list[str] = Field(default_factory=list)  # each "REF.PIN", e.g. "J1.A4"
    net_class: Optional[str] = None


class Constraint(BaseModel):
    """A design constraint; flat extra keys are folded into ``params``."""

    model_config = ConfigDict(extra="allow")

    type: str
    params: dict = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _fold_flat_into_params(cls, data: object) -> object:
        """Move every key except ``type``/``params`` into ``params``."""
        if not isinstance(data, dict):
            return data
        out: dict = {}
        params: dict = {}
        given_params = data.get("params")
        if isinstance(given_params, dict):
            params.update(given_params)
        for key, value in data.items():
            if key == "type":
                out["type"] = value
            elif key == "params":
                continue
            else:
                params[key] = value
        out["params"] = params
        return out


class CircuitModel(BaseModel):
    """The complete validated circuit."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: Optional[str] = None
    components: list[Component] = Field(default_factory=list)
    nets: list[Net] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    design_intent: Optional[str] = None
    metadata: dict = Field(default_factory=dict)

    def component_refs(self) -> set[str]:
        """Return the set of all component refs."""
        return {c.ref for c in self.components}

    def find_component(self, ref: str) -> Optional[Component]:
        """Return the component with the given ref, or ``None``."""
        for c in self.components:
            if c.ref == ref:
                return c
        return None

    def net_by_name(self, name: str) -> Optional[Net]:
        """Return the net with the given name, or ``None``."""
        for n in self.nets:
            if n.name == name:
                return n
        return None


def split_refpin(conn: str) -> tuple[str, str]:
    """Split a ``"REF.PIN"`` connection string on the FIRST dot.

    ``"J1.A4"`` -> ``("J1", "A4")``; ``"U1.PB1.alt"`` -> ``("U1", "PB1.alt")``.
    Raises ``ValueError`` if there is no dot.
    """
    if "." not in conn:
        raise ValueError(f"connection {conn!r} is not a valid REF.PIN string")
    ref, pin = conn.split(".", 1)
    return ref, pin
