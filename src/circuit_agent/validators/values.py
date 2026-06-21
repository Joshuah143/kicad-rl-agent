"""Parsers for engineering component values (resistance, capacitance).

Deterministic, no dependencies. Return ``None`` on anything unparseable rather
than raising, so callers can degrade to a WARNING.
"""

from __future__ import annotations

import re
from typing import Optional

# Metric multiplier prefixes used in the "infix" notation (e.g. "4k7", "5R1").
_RES_PREFIX: dict[str, float] = {
    "r": 1.0,
    "k": 1e3,
    "m": 1e6,  # for resistance, M means mega
    "g": 1e9,
}

_CAP_PREFIX: dict[str, float] = {
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "µ": 1e-6,
    "m": 1e-3,
    "f": 1.0,  # base farads when written like "1f"? treat as farad
}


def _to_float(s: str) -> Optional[float]:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_resistance(s: str) -> Optional[float]:
    """Parse a resistance string into ohms, or ``None``.

    Handles ``"5.1k"``, ``"4k7"``, ``"10R"``, ``"1M"``, ``"100"``, ``"2.2k"``,
    ``"0R"``.
    """
    if not isinstance(s, str):
        return None
    text = s.strip().lower()
    if not text:
        return None
    text = text.replace("ohm", "").replace("Ω", "").replace("ω", "").strip()
    if not text:
        return None

    # Infix notation: digits PREFIX digits, e.g. "4k7" -> 4.7k, "0r" -> 0.
    m = re.fullmatch(r"(\d*)([rkmg])(\d*)", text)
    if m:
        whole, prefix, frac = m.group(1), m.group(2), m.group(3)
        mult = _RES_PREFIX[prefix]
        num_str = (whole or "0") + ("." + frac if frac else "")
        val = _to_float(num_str)
        return None if val is None else val * mult

    # Suffix notation: number then optional prefix, e.g. "5.1k", "1M", "100".
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([rkmg]?)", text)
    if m:
        num, prefix = m.group(1), m.group(2)
        val = _to_float(num)
        if val is None:
            return None
        mult = _RES_PREFIX.get(prefix, 1.0)
        return val * mult

    return None


def parse_capacitance(s: str) -> Optional[float]:
    """Parse a capacitance string into farads, or ``None``.

    Handles ``"100n"``, ``"1u"``, ``"10uF"``, ``"4.7uF"``, ``"22p"``,
    ``"0.1uF"``.
    """
    if not isinstance(s, str):
        return None
    text = s.strip().lower()
    if not text:
        return None
    text = text.replace("farad", "").replace("f", "f")  # keep an 'f' marker if present
    # Strip a trailing unit 'f' (as in 'uf'/'pf'/'nf'/'10uf') but keep prefix.
    # First handle explicit unit: drop a single trailing 'f'.
    if text.endswith("f"):
        text = text[:-1]
    text = text.strip()
    if not text:
        return None

    # Infix notation: e.g. "4u7" -> 4.7u.
    m = re.fullmatch(r"(\d*)([pnuµm])(\d*)", text)
    if m:
        whole, prefix, frac = m.group(1), m.group(2), m.group(3)
        mult = _CAP_PREFIX[prefix]
        num_str = (whole or "0") + ("." + frac if frac else "")
        val = _to_float(num_str)
        return None if val is None else val * mult

    # Suffix notation: number then optional prefix, e.g. "100n", "0.1u".
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([pnuµm]?)", text)
    if m:
        num, prefix = m.group(1), m.group(2)
        val = _to_float(num)
        if val is None:
            return None
        mult = _CAP_PREFIX.get(prefix, 1.0)
        return val * mult

    return None
