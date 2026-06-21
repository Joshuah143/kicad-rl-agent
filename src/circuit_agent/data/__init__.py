"""Data catalogs: symbols, footprints and curated parts."""

from __future__ import annotations

from circuit_agent.data.footprints import (
    FOOTPRINTS,
    FootprintDef,
    footprint_area,
    get_footprint,
    has_footprint,
)
from circuit_agent.data.parts_db import (
    PARTS,
    PartSpec,
    all_parts,
    get_part,
    resolve_part,
)
from circuit_agent.data.symbols import (
    SYMBOLS,
    PinDef,
    SymbolDef,
    get_symbol,
    has_symbol,
    pin_numbers,
    symbol_pins,
)

__all__ = [
    "FOOTPRINTS",
    "FootprintDef",
    "footprint_area",
    "get_footprint",
    "has_footprint",
    "PARTS",
    "PartSpec",
    "all_parts",
    "get_part",
    "resolve_part",
    "SYMBOLS",
    "PinDef",
    "SymbolDef",
    "get_symbol",
    "has_symbol",
    "pin_numbers",
    "symbol_pins",
]
