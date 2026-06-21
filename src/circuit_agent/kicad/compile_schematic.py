"""CircuitModel -> KiCad project emitter (generic symbols, real connectivity).

This emitter writes a ``.kicad_pro`` project and a ``.kicad_sch`` s-expression
that *loads in KiCad 10* and is checkable by ``kicad-cli sch erc``. It does so
without shipping the real KiCad symbol libraries: a GENERIC rectangular symbol is
synthesised for every distinct ``lib_id`` (pins down the left/right edges, using
the real pin numbers/names/electrical types from :mod:`circuit_agent.data.symbols`
when known, otherwise synthesised from the pins the nets reference).

Connectivity is REAL, not cosmetic: each net becomes a set of same-named
``global_label`` s placed at the exact world coordinates of the pin endpoints of
the placed symbols. Two identical label texts mean the pins are electrically
connected — and because the labels sit on the pins, KiCad's connectivity engine
(and ERC) actually sees the connection.

Power nets (those carrying a ``power_in`` pin) get a generic ``PWR_FLAG`` symbol
(a ``power_out`` pin) dropped on them so ERC does not report a spurious
"Input Power pin not driven" error for every power rail.

Geometry note (KiCad symbol frame is Y-up, schematic is Y-down): a pin whose
local connection point is ``(lx, ly)`` on an unrotated instance placed at
``(ix, iy)`` has its world endpoint at ``(ix + lx, iy - ly)``.

The reliable visual for a design is still the hand-rolled SVG graph
(:mod:`circuit_agent.kicad.export_visuals`); this KiCad output is the
ERC-checkable seam.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from typing import Optional

from circuit_agent.data import symbols as symbols_db
from circuit_agent.dsl.schema import CircuitModel, split_refpin

# KiCad schematic file-format version this emitter targets. 20250114 is the
# native version for the KiCad 9/10 era; KiCad 10 loads it directly.
KICAD_SCH_VERSION = "20250114"
GENERATOR = "circuit_agent"
GENERATOR_VERSION = "9.0"

# Electrical pin types KiCad accepts in a (pin <type> ...) token.
_VALID_ETYPES = {
    "input",
    "output",
    "bidirectional",
    "tri_state",
    "passive",
    "free",
    "unspecified",
    "power_in",
    "power_out",
    "open_collector",
    "open_emitter",
    "no_connect",
}

# Layout constants (millimetres).
_PIN_LEN = 5.08          # length of each generated pin stub
_PIN_PITCH = 2.54        # vertical spacing between pins on an edge
_GRID_X = 50.8           # horizontal spacing between placed components
_GRID_Y = 50.8           # vertical spacing between placed components
_ORIGIN_X = 50.8
_ORIGIN_Y = 50.8
_COLS = 6                # components per row in the placement grid
_FONT = "(effects (font (size 1.27 1.27)))"


@dataclass
class CompileResult:
    """The outcome of compiling a model into a KiCad project."""

    ok: bool
    project_path: Optional[str]
    schematic_path: Optional[str]
    notes: list[str]


def _uuid() -> str:
    return str(uuid.uuid4())


def _sym_name(lib_id: str) -> str:
    """Return the bare symbol name from a ``LIB:NAME`` id (KiCad child-unit name).

    KiCad names the child unit symbols by the *bare* name only (e.g. ``R_1_1``
    for ``Device:R``); using the fully-qualified id there breaks loading.
    """
    return lib_id.split(":", 1)[1] if ":" in lib_id else lib_id


def _project_json(basename: str) -> str:
    """A minimal-but-valid ``.kicad_pro`` project JSON."""
    return json.dumps(
        {
            "board": {"design_settings": {}},
            "meta": {"filename": f"{basename}.kicad_pro", "version": 1},
            "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
            "sheets": [],
            "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        },
        indent=2,
    )


# --------------------------------------------------------------------------- #
# Pin model: resolve the pins for each lib_id, slot them onto left/right edges.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _PinSlot:
    """A pin placed on the generic body, with its local connection point."""

    number: str
    name: str
    etype: str
    side: str          # "L" or "R"
    local_x: float
    local_y: float


def _safe_etype(etype: str) -> str:
    return etype if etype in _VALID_ETYPES else "passive"


def _resolve_pins(lib_id: str, referenced: list[str]) -> list[symbols_db.PinDef]:
    """Return the pin definitions to emit for ``lib_id``.

    Only pins actually *referenced by a net* are emitted: this keeps the symbol
    honest (every pin attaches to a label) and avoids gratuitous
    "pin not connected" ERC errors for catalog pins the design never uses. Each
    referenced pin's name/etype is pulled from the static catalog when known,
    otherwise synthesised as a passive pin.
    """
    catalog = {p.number: p for p in symbols_db.symbol_pins(lib_id)}
    pins: list[symbols_db.PinDef] = []
    for number in referenced:
        pins.append(
            catalog.get(number, symbols_db.PinDef(number=number, name=number, etype="passive"))
        )
    if not pins:
        # No net references this component at all: still emit a valid one-pin
        # symbol (prefer the catalog's first pin) so the symbol is well-formed.
        first = symbols_db.symbol_pins(lib_id)
        pins.append(first[0] if first else symbols_db.PinDef(number="1", name="~", etype="passive"))
    return pins


def _slot_pins(pins: list[symbols_db.PinDef]) -> tuple[list[_PinSlot], float, float]:
    """Lay pins onto the left/right edges of a rectangle.

    Returns ``(slots, half_width, half_height)`` where the rectangle spans
    ``[-half_width, half_width] x [-half_height, half_height]`` in local
    coordinates. Pins alternate left/right and are stacked top-down.
    """
    left = [p for i, p in enumerate(pins) if i % 2 == 0]
    right = [p for i, p in enumerate(pins) if i % 2 == 1]
    rows = max(len(left), len(right), 1)
    half_h = max(_PIN_PITCH, ((rows - 1) * _PIN_PITCH) / 2.0 + _PIN_PITCH)
    half_w = 7.62

    slots: list[_PinSlot] = []
    for i, p in enumerate(left):
        ly = half_h - _PIN_PITCH - i * _PIN_PITCH
        slots.append(
            _PinSlot(p.number, p.name, _safe_etype(p.etype), "L", -(half_w + _PIN_LEN), ly)
        )
    for i, p in enumerate(right):
        ly = half_h - _PIN_PITCH - i * _PIN_PITCH
        slots.append(
            _PinSlot(p.number, p.name, _safe_etype(p.etype), "R", half_w + _PIN_LEN, ly)
        )
    return slots, half_w, half_h


def _generic_symbol_sexpr(lib_id: str, slots: list[_PinSlot], half_w: float, half_h: float) -> list[str]:
    """Emit a generic rectangular ``lib_symbols`` entry for ``lib_id``."""
    name = _sym_name(lib_id)
    lines = [
        f'    (symbol "{lib_id}"',
        "      (pin_numbers (hide yes))",
        "      (pin_names (offset 1.016))",
        "      (exclude_from_sim no) (in_bom yes) (on_board yes)",
        f'      (property "Reference" "U" (at 0 {round(half_h + 2.54, 3)} 0) {_FONT})',
        f'      (property "Value" "{name}" (at 0 {round(-half_h - 2.54, 3)} 0) {_FONT})',
        f'      (symbol "{name}_0_1"',
        f"        (rectangle (start {-half_w} {half_h}) (end {half_w} {-half_h})",
        "          (stroke (width 0.254) (type default)) (fill (type background)))",
        "      )",
        f'      (symbol "{name}_1_1"',
    ]
    for s in slots:
        # Pin points inward toward the body: left pins angle 0, right pins 180.
        angle = 0 if s.side == "L" else 180
        lines.append(
            f"        (pin {s.etype} line (at {round(s.local_x, 3)} {round(s.local_y, 3)} {angle}) "
            f"(length {_PIN_LEN})"
        )
        lines.append(f'          (name "{s.name}" {_FONT})')
        lines.append(f'          (number "{s.number}" {_FONT}))')
    lines.append("      )")
    lines.append("    )")
    return lines


def _pwr_flag_symbol_sexpr() -> list[str]:
    """Emit a generic ``power:PWR_FLAG`` lib symbol (single ``power_out`` pin)."""
    return [
        '    (symbol "power:PWR_FLAG"',
        "      (power)",
        "      (pin_numbers (hide yes))",
        "      (pin_names (offset 0) (hide yes))",
        "      (exclude_from_sim no) (in_bom yes) (on_board yes)",
        f'      (property "Reference" "#FLG" (at 0 1.905 0) (hide yes) {_FONT})',
        f'      (property "Value" "PWR_FLAG" (at 0 3.81 0) {_FONT})',
        '      (symbol "PWR_FLAG_0_0"',
        "        (pin power_out line (at 0 0 90) (length 0)",
        f'          (name "~" {_FONT})',
        f'          (number "1" {_FONT}))',
        "      )",
        '      (symbol "PWR_FLAG_0_1"',
        "        (polyline (pts (xy 0 0) (xy 0 1.27) (xy -1.016 1.905) (xy 0 2.54) (xy 1.016 1.905) (xy 0 1.27))",
        "          (stroke (width 0) (type default)) (fill (type none)))",
        "      )",
        "    )",
    ]


def _global_label(name: str, x: float, y: float, justify: str) -> str:
    return (
        f'  (global_label "{name}" (shape input) (at {round(x, 3)} {round(y, 3)} 0) '
        f"(fields_autoplaced yes) "
        f"(effects (font (size 1.27 1.27)) (justify {justify})) (uuid {_uuid()}))"
    )


def compile_schematic(model: CircuitModel, out_dir: str, *, basename: str = "design") -> CompileResult:
    """Compile ``model`` into ``{basename}.kicad_pro`` + ``{basename}.kicad_sch``.

    The output loads in KiCad 10 and is ERC-checkable via ``kicad-cli``. Never
    raises: any failure is reported via ``CompileResult.ok == False`` and notes.
    """
    notes: list[str] = [
        "Generic-symbol emitter (ERC-checkable); the SVG graph is the human visual."
    ]
    try:
        os.makedirs(out_dir, exist_ok=True)
        project_path = os.path.join(out_dir, f"{basename}.kicad_pro")
        sch_path = os.path.join(out_dir, f"{basename}.kicad_sch")

        with open(project_path, "w", encoding="utf-8") as fh:
            fh.write(_project_json(basename))

        root_uuid = _uuid()

        # --- 1. Which pins does each ref actually reference in the nets? ------
        #        (used to synthesise pins for unknown symbols.)
        referenced_pins: dict[str, list[str]] = {}
        for net in model.nets:
            for conn in net.connections:
                try:
                    ref, pin = split_refpin(conn)
                except ValueError:
                    continue
                referenced_pins.setdefault(ref, [])
                if pin not in referenced_pins[ref]:
                    referenced_pins[ref].append(pin)

        # --- 2. Build the generic pin model per distinct lib_id --------------
        distinct_libs = sorted({c.symbol for c in model.components if c.symbol})
        unknown = [lib for lib in distinct_libs if not symbols_db.has_symbol(lib)]
        if unknown:
            notes.append(f"unknown symbols emitted as synthesised generics: {unknown}")

        # Per lib_id: slots + body extents, plus a per-(lib_id) lookup by number.
        lib_slots: dict[str, list[_PinSlot]] = {}
        lib_extent: dict[str, tuple[float, float]] = {}
        for lib in distinct_libs:
            # Union of every pin referenced by any component using this lib_id.
            ref_union: list[str] = []
            for comp in model.components:
                if comp.symbol == lib:
                    for p in referenced_pins.get(comp.ref, []):
                        if p not in ref_union:
                            ref_union.append(p)
            pins = _resolve_pins(lib, ref_union)
            slots, half_w, half_h = _slot_pins(pins)
            lib_slots[lib] = slots
            lib_extent[lib] = (half_w, half_h)

        # --- 3. Header + lib_symbols ----------------------------------------
        sexpr: list[str] = []
        sexpr.append("(kicad_sch")
        sexpr.append(f"  (version {KICAD_SCH_VERSION})")
        sexpr.append(f'  (generator "{GENERATOR}")')
        sexpr.append(f'  (generator_version "{GENERATOR_VERSION}")')
        sexpr.append(f'  (uuid "{root_uuid}")')
        sexpr.append('  (paper "A4")')
        sexpr.append("  (lib_symbols")
        for lib in distinct_libs:
            slots = lib_slots[lib]
            half_w, half_h = lib_extent[lib]
            sexpr.extend(_generic_symbol_sexpr(lib, slots, half_w, half_h))
        # The PWR_FLAG library symbol is always available (used for power nets).
        sexpr.extend(_pwr_flag_symbol_sexpr())
        sexpr.append("  )")

        # --- 4. Place component instances; record pin world coordinates ------
        # pin_world[(ref, pin_number)] = (x, y, side)
        pin_world: dict[tuple[str, str], tuple[float, float, str]] = {}
        for i, comp in enumerate(model.components):
            col, row = i % _COLS, i // _COLS
            ix = round(_ORIGIN_X + col * _GRID_X, 3)
            iy = round(_ORIGIN_Y + row * _GRID_Y, 3)
            slots = lib_slots.get(comp.symbol, [])
            half_w, half_h = lib_extent.get(comp.symbol, (7.62, 7.62))

            inst_uuid = _uuid()
            sexpr.append("  (symbol")
            sexpr.append(f'    (lib_id "{comp.symbol}")')
            sexpr.append(f"    (at {ix} {iy} 0) (unit 1)")
            sexpr.append("    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)")
            sexpr.append(f'    (uuid "{inst_uuid}")')
            ref_y = round(iy - half_h - 2.54, 3)
            val_y = round(iy + half_h + 2.54, 3)
            sexpr.append(
                f'    (property "Reference" "{comp.ref}" (at {ix} {ref_y} 0) '
                f"(effects (font (size 1.27 1.27)) (justify left)))"
            )
            sexpr.append(
                f'    (property "Value" "{(comp.value or "").replace(chr(34), "")}" '
                f"(at {ix} {val_y} 0) (effects (font (size 1.27 1.27)) (justify left)))"
            )
            for s in slots:
                sexpr.append(f'    (pin "{s.number}" (uuid "{_uuid()}"))')
                wx = round(ix + s.local_x, 3)
                wy = round(iy - s.local_y, 3)
                pin_world[(comp.ref, s.number)] = (wx, wy, s.side)
            sexpr.append("    (instances")
            sexpr.append(f'      (project "{basename}"')
            sexpr.append(
                f'        (path "/{root_uuid}" (reference "{comp.ref}") (unit 1))))'
            )
            sexpr.append("  )")

        # --- 5. Merge nets that physically share a pin ----------------------
        # A single pin has exactly one world coordinate, so if a pin appears in
        # more than one net those nets are electrically the *same* node (the
        # source design shorted them). Merge such nets with union-find so each
        # electrical group gets ONE canonical label name and ONE PWR_FLAG —
        # stacking two differently-named labels (or two flags) on one pin is what
        # produces spurious multiple_net_names / power-output-conflict errors.
        def _pin_etype(ref: str, pin: str) -> str:
            comp = model.find_component(ref)
            if comp is None:
                return "passive"
            for pd in symbols_db.symbol_pins(comp.symbol):
                if pd.number == pin:
                    return pd.etype
            return "passive"

        parent: dict[int, int] = {i: i for i in range(len(model.nets))}

        def _find(a: int) -> int:
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def _union(a: int, b: int) -> None:
            ra, rb = _find(a), _find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)

        pin_to_nets: dict[tuple[str, str], list[int]] = {}
        for ni, net in enumerate(model.nets):
            for conn in net.connections:
                try:
                    ref, pin = split_refpin(conn)
                except ValueError:
                    continue
                pin_to_nets.setdefault((ref, pin), []).append(ni)
        for nets_on_pin in pin_to_nets.values():
            for other in nets_on_pin[1:]:
                _union(nets_on_pin[0], other)

        # Canonical name per group = the name of the lowest-index net in it.
        group_name: dict[int, str] = {}
        for ni, net in enumerate(model.nets):
            root = _find(ni)
            if root not in group_name:
                group_name[root] = model.nets[root].name

        # --- 6. Emit one global_label per pin endpoint, plus PWR_FLAGs ------
        # PWR_FLAG symbols are placed on a deterministic row below the grid.
        flag_index = 0
        n_rows = (len(model.components) - 1) // _COLS + 1 if model.components else 1
        flag_row_y = round(_ORIGIN_Y + (n_rows + 1) * _GRID_Y, 3)

        # Per electrical group: collect its pins (dedup'd by coordinate) and
        # whether it carries power_in / power_out pins.
        group_pins: dict[int, dict[tuple[float, float], str]] = {}
        group_has_power_in: dict[int, bool] = {}
        group_has_power_out: dict[int, bool] = {}
        for ni, net in enumerate(model.nets):
            root = _find(ni)
            pins = group_pins.setdefault(root, {})
            for conn in net.connections:
                try:
                    ref, pin = split_refpin(conn)
                except ValueError:
                    continue
                et = _pin_etype(ref, pin)
                if et == "power_in":
                    group_has_power_in[root] = True
                elif et == "power_out":
                    group_has_power_out[root] = True
                world = pin_world.get((ref, pin))
                if world is None:
                    continue
                wx, wy, side = world
                pins[(wx, wy)] = side  # last writer wins; coordinate is unique per pin

        for root in sorted(group_pins):
            name = group_name[root]
            pins = group_pins[root]
            if not pins:
                continue
            for (wx, wy), side in pins.items():
                justify = "right" if side == "L" else "left"
                sexpr.append(_global_label(name, wx, wy, justify))

            # Drive power groups (power_in present, no power_out source) with a
            # single generic PWR_FLAG so ERC does not flag "Input Power pin not
            # driven" on the rail.
            if group_has_power_in.get(root) and not group_has_power_out.get(root):
                flag_uuid = _uuid()
                fx = round(_ORIGIN_X + flag_index * 25.4, 3)
                fy = flag_row_y
                flag_ref = f"#FLG{flag_index + 1:03d}"
                flag_index += 1
                sexpr.append("  (symbol")
                sexpr.append('    (lib_id "power:PWR_FLAG")')
                sexpr.append(f"    (at {fx} {fy} 0) (unit 1)")
                sexpr.append(
                    "    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)"
                )
                sexpr.append(f'    (uuid "{flag_uuid}")')
                sexpr.append(
                    f'    (property "Reference" "{flag_ref}" (at {fx} {round(fy - 3.81, 3)} 0) '
                    f"(effects (font (size 1.27 1.27)) (hide yes)))"
                )
                sexpr.append(
                    f'    (property "Value" "PWR_FLAG" (at {fx} {round(fy + 3.81, 3)} 0) '
                    f"(effects (font (size 1.27 1.27))))"
                )
                sexpr.append(f'    (pin "1" (uuid "{_uuid()}"))')
                sexpr.append("    (instances")
                sexpr.append(f'      (project "{basename}"')
                sexpr.append(
                    f'        (path "/{root_uuid}" (reference "{flag_ref}") (unit 1))))'
                )
                sexpr.append("  )")
                # PWR_FLAG pin endpoint: local (0,0) -> world (fx, fy).
                sexpr.append(_global_label(name, fx, fy, "left"))

        # --- 7. Footer ------------------------------------------------------
        sexpr.append('  (sheet_instances (path "/" (page "1")))')
        sexpr.append("  (embedded_fonts no)")
        sexpr.append(")")

        with open(sch_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(sexpr) + "\n")

        return CompileResult(ok=True, project_path=project_path, schematic_path=sch_path, notes=notes)
    except Exception as exc:  # noqa: BLE001 - emitter must never raise
        notes.append(f"compile failed: {exc}")
        return CompileResult(ok=False, project_path=None, schematic_path=None, notes=notes)
