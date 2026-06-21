"""Fluent builder for circuits.

The builder class is ``Circuit`` (the pydantic model is ``CircuitModel``). It is
the API the LLM-authored programs use inside the sandbox: parts are added,
convenience helpers pull sensible defaults from the parts database, and nets are
wired with a chainable ``net().connect(...)`` interface.
"""

from __future__ import annotations

from typing import Optional, Union

from circuit_agent.dsl.schema import (
    CircuitModel,
    Component,
    Constraint,
    Net,
    PackageType,
)


class _PartHandle:
    """A lightweight handle to a placed part, used for chaining connections."""

    def __init__(self, ref: str, builder: "Circuit") -> None:
        self.ref = ref
        self._builder = builder

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"_PartHandle({self.ref!r})"


def _ref_of(part_or_ref: Union["_PartHandle", str]) -> str:
    """Return the ref string for a handle or a bare ref."""
    if isinstance(part_or_ref, _PartHandle):
        return part_or_ref.ref
    return str(part_or_ref)


class _NetBuilder:
    """Chainable helper bound to a single :class:`Net`."""

    def __init__(self, net: Net) -> None:
        self._net = net

    def connect(self, part_or_ref: Union[_PartHandle, str], pin: str) -> "_NetBuilder":
        """Append ``"{ref}.{pin}"`` to this net's connections; chainable."""
        ref = _ref_of(part_or_ref)
        self._net.connections.append(f"{ref}.{pin}")
        return self


class Circuit:
    """A fluent builder that produces a :class:`CircuitModel`."""

    def __init__(
        self,
        name: str,
        description: Optional[str] = None,
        design_intent: Optional[str] = None,
    ) -> None:
        self.name = name
        self.description = description
        self.design_intent = design_intent
        self._components: list[Component] = []
        self._nets: list[Net] = []
        self._constraints: list[Constraint] = []
        self._metadata: dict = {}

    # ------------------------------------------------------------------ #
    # Parts
    # ------------------------------------------------------------------ #
    def add_part(
        self,
        ref: str,
        symbol: str,
        footprint: Optional[str] = None,
        value: Optional[str] = None,
        role: Optional[str] = None,
        package_type: Union[str, PackageType] = "SMD",
        unit_cost_usd: Optional[float] = None,
        availability_score: Optional[float] = None,
        package_dims_mm: Optional[tuple[float, float]] = None,
        datasheet: Optional[str] = None,
        source_ref: Optional[str] = None,
        pins: Optional[list[str]] = None,
        **attributes: object,
    ) -> _PartHandle:
        """Add a component and return a handle to it."""
        comp = Component(
            ref=ref,
            symbol=symbol,
            footprint=footprint,
            value=value,
            role=role,
            package_type=package_type,  # type: ignore[arg-type]  (pydantic coerces str)
            unit_cost_usd=unit_cost_usd,
            availability_score=availability_score,
            package_dims_mm=package_dims_mm,
            datasheet=datasheet,
            source_ref=source_ref,
            pins=pins,
            attributes=dict(attributes),
        )
        self._components.append(comp)
        return _PartHandle(comp.ref, self)

    def _defaults_from_db(self, key: str) -> dict:
        """Return resolve_part(key) defaults, tolerating an unknown key."""
        from circuit_agent.data import parts_db

        return parts_db.resolve_part(key)

    def _add_with_defaults(
        self,
        ref: str,
        symbol: str,
        db_key: str,
        value: Optional[str],
        footprint: Optional[str],
        role: Optional[str],
        kw: dict,
    ) -> _PartHandle:
        """Shared helper for the typed convenience adders."""
        defaults = self._defaults_from_db(db_key)
        resolved_footprint = footprint if footprint is not None else defaults.get("footprint")
        merged: dict = {
            "unit_cost_usd": defaults.get("unit_cost_usd"),
            "availability_score": defaults.get("availability_score"),
            "package_dims_mm": defaults.get("package_dims_mm"),
            "package_type": defaults.get("package_type", "SMD"),
        }
        # Caller-supplied kwargs win over db defaults.
        merged.update(kw)
        return self.add_part(
            ref,
            symbol=symbol,
            footprint=resolved_footprint,
            value=value,
            role=role,
            **merged,
        )

    def add_resistor(
        self,
        ref: str,
        value: str,
        footprint: Optional[str] = None,
        role: Optional[str] = None,
        **kw: object,
    ) -> _PartHandle:
        """Add a ``Device:R`` resistor; defaults from ``resistor_0603``."""
        return self._add_with_defaults(ref, "Device:R", "resistor_0603", value, footprint, role, dict(kw))

    def add_capacitor(
        self,
        ref: str,
        value: str,
        footprint: Optional[str] = None,
        role: Optional[str] = None,
        **kw: object,
    ) -> _PartHandle:
        """Add a ``Device:C`` capacitor; defaults from ``cap_0603_100n``."""
        return self._add_with_defaults(ref, "Device:C", "cap_0603_100n", value, footprint, role, dict(kw))

    def add_led(
        self,
        ref: str,
        value: str = "LED",
        footprint: Optional[str] = None,
        role: Optional[str] = None,
        **kw: object,
    ) -> _PartHandle:
        """Add a ``Device:LED``; defaults from ``led_0603``."""
        return self._add_with_defaults(ref, "Device:LED", "led_0603", value, footprint, role, dict(kw))

    def add_part_from_db(self, ref: str, key: str, **overrides: object) -> _PartHandle:
        """Add a component fully specified by a parts_db key, with overrides."""
        spec = self._defaults_from_db(key)
        if not spec:
            # Unknown key: place a minimal placeholder rather than crashing.
            symbol = str(overrides.pop("symbol", "")) or ""
            return self.add_part(ref, symbol=symbol, **overrides)  # type: ignore[arg-type]
        merged = dict(spec)
        merged.update(overrides)
        symbol = merged.pop("symbol")
        return self.add_part(ref, symbol=symbol, **merged)  # type: ignore[arg-type]

    # ------------------------------------------------------------------ #
    # Constraints
    # ------------------------------------------------------------------ #
    def add_constraint(self, type: str, **params: object) -> None:
        """Add a design constraint of the given type with flat params."""
        self._constraints.append(Constraint(type=type, params=dict(params)))

    # ------------------------------------------------------------------ #
    # Nets
    # ------------------------------------------------------------------ #
    def _get_or_create_net(self, name: str) -> Net:
        for n in self._nets:
            if n.name == name:
                return n
        net = Net(name=name)
        self._nets.append(net)
        return net

    def net(self, name: str) -> _NetBuilder:
        """Get-or-create a net by name and return a chainable builder."""
        return _NetBuilder(self._get_or_create_net(name))

    def connect(self, net_name: str, *refpins: str) -> "Circuit":
        """Attach pre-formed ``"REF.PIN"`` strings to a net; chainable."""
        net = self._get_or_create_net(net_name)
        net.connections.extend(refpins)
        return self

    # ------------------------------------------------------------------ #
    # Output
    # ------------------------------------------------------------------ #
    def to_model(self) -> CircuitModel:
        """Build the validated :class:`CircuitModel`."""
        return CircuitModel(
            name=self.name,
            description=self.description,
            design_intent=self.design_intent,
            components=list(self._components),
            nets=list(self._nets),
            constraints=list(self._constraints),
            metadata=dict(self._metadata),
        )

    def to_dict(self) -> dict:
        """Return ``to_model().model_dump()``."""
        return self.to_model().model_dump()

    @staticmethod
    def from_model(model: CircuitModel) -> "Circuit":
        """Reconstruct a builder from a :class:`CircuitModel`."""
        c = Circuit(model.name, description=model.description, design_intent=model.design_intent)
        c._components = [comp.model_copy(deep=True) for comp in model.components]
        c._nets = [net.model_copy(deep=True) for net in model.nets]
        c._constraints = [con.model_copy(deep=True) for con in model.constraints]
        c._metadata = dict(model.metadata)
        return c
