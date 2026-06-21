"""CircuitModel -> KiCad 9 PCB emitter.

Produces a ``.kicad_pcb`` with embedded simplified footprints, copper tracks on
``F.Cu``, silkscreen/fab outlines, courtyards, and a board edge. This is
intentionally self-contained (no external footprint libraries required) so
``kicad-cli pcb export svg`` (trace) and ``pcb export glb`` (3D) can render the
board natively for the GUI.

Important KiCad 9 syntax notes (learned by bisecting real boards):
- A footprint pad with a net MUST be ``(net <num> "<name>")`` -- the net name
  string is mandatory; ``(net <num>)`` alone makes the board fail to load.
- Unconnected pads simply omit the ``(net ...)`` token entirely.
- Footprints require an ``(attr ...)`` token (``smd`` / ``through_hole``).
- Track ``(segment ...)`` uses ``(net <num>)`` (number only).
"""

from __future__ import annotations

import math
import os
import uuid
from dataclasses import dataclass, field
from typing import Optional

from circuit_agent.dsl.schema import CircuitModel, split_refpin

KICAD_PCB_VERSION = "20241229"
GENERATOR = "circuit_agent"
GENERATOR_VERSION = "9.0"

# Layout (mm)
_ORIGIN = (60.0, 50.0)
_COLS = 4
_PITCH_X = 16.0
_PITCH_Y = 14.0
_BOARD_MARGIN = 8.0
_TRACK_W = 0.25

# Solder-mask colour palette -> KiCad stackup colour string. KiCad's render and
# GLB export read the board colour from the stackup, so this drives both the 3D
# board colour and the ray-traced render (default green; no more bare-FR4 brown).
SOLDERMASK_COLORS: dict[str, str] = {
    "Green": "Green",
    "Blue": "Blue",
    "Red": "Red",
    "Black": "Black",
    "White": "White",
    "Purple": "Purple",
}
DEFAULT_SOLDERMASK = "Green"


@dataclass
class CompilePCBResult:
    ok: bool
    pcb_path: Optional[str]
    notes: list[str] = field(default_factory=list)


def _uid() -> str:
    return str(uuid.uuid4())


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _layers_block() -> str:
    return """  (layers
    (0 "F.Cu" signal)
    (2 "B.Cu" signal)
    (9 "F.Adhes" user "F.Adhesive")
    (11 "B.Adhes" user "B.Adhesive")
    (13 "F.Paste" user)
    (15 "B.Paste" user)
    (5 "F.SilkS" user "F.Silkscreen")
    (7 "B.SilkS" user "B.Silkscreen")
    (1 "F.Mask" user)
    (3 "B.Mask" user)
    (17 "Dwgs.User" user "User.Drawings")
    (19 "Cmts.User" user "User.Comments")
    (21 "Eco1.User" user "User.Eco1")
    (23 "Eco2.User" user "User.Eco2")
    (25 "Edge.Cuts" user)
    (27 "Margin" user)
    (31 "F.CrtYd" user "F.Courtyard")
    (29 "B.CrtYd" user "B.Courtyard")
    (35 "F.Fab" user)
    (33 "B.Fab" user)
  )"""


def _stackup_block(soldermask_color: str) -> str:
    color = SOLDERMASK_COLORS.get(soldermask_color, soldermask_color or "Green")
    return f"""    (stackup
      (layer "F.SilkS" (type "Top Silk Screen"))
      (layer "F.Paste" (type "Top Solder Paste"))
      (layer "F.Mask" (type "Top Solder Mask") (color "{color}") (thickness 0.01))
      (layer "F.Cu" (type "copper") (thickness 0.035))
      (layer "dielectric 1" (type "core") (thickness 1.51) (material "FR4")
        (epsilon_r 4.5) (loss_tangent 0.02))
      (layer "B.Cu" (type "copper") (thickness 0.035))
      (layer "B.Mask" (type "Bottom Solder Mask") (color "{color}") (thickness 0.01))
      (layer "B.Paste" (type "Bottom Solder Paste"))
      (layer "B.SilkS" (type "Bottom Silk Screen"))
      (copper_finish "ENIG")
      (dielectric_constraints no)
    )"""


def _setup_block(soldermask_color: str = DEFAULT_SOLDERMASK) -> str:
    return f"""  (setup
{_stackup_block(soldermask_color)}
    (pad_to_mask_clearance 0)
    (allow_soldermask_bridges_in_footprints no)
    (pcbplotparams
      (layerselection 0x00000000_00000000_00000000_000000a5)
      (plot_on_all_layers_selection 0x00000000_00000000_00000000_00000000)
      (disableapertmacros no)
      (usegerberextensions no)
      (usegerberattributes yes)
      (usegerberadvancedattributes yes)
      (creategerberjobfile yes)
      (svgprecision 6)
      (plotframeref no)
      (mode 1)
      (useauxorigin no)
      (plotinvisibletext no)
      (sketchpadsonfab no)
      (plotpadnumbers no)
      (hidednponfab no)
      (sketchdnponfab yes)
      (crossoutdnponfab yes)
      (subtractmaskfromsilk no)
      (outputformat 1)
      (mirror no)
      (drillshape 1)
      (scaleselection 1)
      (outputdirectory "")
    )
  )"""


def _fp_class(footprint: Optional[str], symbol: str) -> str:
    fp = (footprint or "").lower()
    sym = (symbol or "").lower()
    if "0402" in fp or "1005" in fp:
        return "0402"
    if "0805" in fp or "2012" in fp:
        return "0805"
    if "0603" in fp or "1608" in fp:
        return "0603"
    if "sot-23" in fp or "sot_23" in fp or "sot23" in fp:
        return "sot23"
    if "qfn" in fp or "dfn" in fp:
        return "ic_qfn"
    if "tssop" in fp or "soic" in fp or "msop" in fp:
        return "ic_wide"
    if "usb" in fp or "usb" in sym:
        return "usb_c"
    if "connector" in fp or "connector" in sym or "pinheader" in fp or "header" in sym:
        return "connector"
    if "testpoint" in fp or "testpoint" in sym or sym.startswith("connector:testpoint"):
        return "tp"
    if symbol.startswith("Device:R"):
        return "0603"
    if symbol.startswith("Device:C"):
        return "0603"
    if symbol.startswith("Device:L"):
        return "0805"
    if symbol.startswith("Device:LED") or symbol.startswith("Device:D"):
        return "0603"
    if symbol.startswith("Device:Q") or symbol.startswith("Device:U"):
        return "sot23"
    return "0603"


@dataclass
class PadDef:
    number: str
    x: float
    y: float
    w: float
    h: float
    shape: str = "roundrect"  # roundrect | rect | circle | oval
    thru: bool = False
    drill: float = 0.0


@dataclass
class FootprintGeom:
    pads: list[PadDef]
    body_hw: float  # half-width of component body (for fab/silk/3d)
    body_hh: float  # half-height
    body_h: float = 0.9  # extruded height for 3d (mm)
    color: tuple[float, float, float] = (0.12, 0.12, 0.14)


def _geom(fp_class: str) -> FootprintGeom:
    """Return pad layout + body extents (local mm coords) for a class."""
    def chip(pad_dx: float, pad_w: float, pad_h: float, body_hw: float, body_hh: float, color):
        return FootprintGeom(
            pads=[
                PadDef("1", -pad_dx, 0, pad_w, pad_h),
                PadDef("2", pad_dx, 0, pad_w, pad_h),
            ],
            body_hw=body_hw, body_hh=body_hh, body_h=0.55, color=color,
        )

    if fp_class == "0402":
        return chip(0.51, 0.54, 0.64, 0.5, 0.35, (0.18, 0.18, 0.2))
    if fp_class == "0603":
        return chip(0.825, 0.8, 0.95, 0.8, 0.45, (0.18, 0.18, 0.2))
    if fp_class == "0805":
        return chip(1.0, 1.0, 1.45, 1.0, 0.7, (0.2, 0.2, 0.22))
    if fp_class == "sot23":
        return FootprintGeom(
            pads=[
                PadDef("1", -1.0, 0.95, 0.6, 0.7),
                PadDef("2", -1.0, -0.95, 0.6, 0.7),
                PadDef("3", 1.0, 0, 0.6, 0.7),
            ],
            body_hw=0.7, body_hh=0.7, body_h=1.0, color=(0.1, 0.1, 0.12),
        )
    if fp_class == "ic_qfn":
        pads = []
        n_side = 4
        pitch = 0.65
        for i in range(n_side):
            y = -((n_side - 1) / 2) * pitch + i * pitch
            pads.append(PadDef(str(i + 1), -2.05, y, 1.0, 0.35))
        for i in range(n_side):
            y = ((n_side - 1) / 2) * pitch - i * pitch
            pads.append(PadDef(str(n_side + i + 1), 2.05, y, 1.0, 0.35))
        return FootprintGeom(pads=pads, body_hw=1.6, body_hh=1.6, body_h=0.9, color=(0.08, 0.08, 0.09))
    if fp_class == "ic_wide":
        pads = []
        n_side = 4
        pitch = 1.27
        for i in range(n_side):
            y = ((n_side - 1) / 2) * pitch - i * pitch
            pads.append(PadDef(str(i + 1), -2.7, y, 1.5, 0.6))
        for i in range(n_side):
            y = -((n_side - 1) / 2) * pitch + i * pitch
            pads.append(PadDef(str(n_side + i + 1), 2.7, y, 1.5, 0.6))
        return FootprintGeom(pads=pads, body_hw=2.0, body_hh=2.7, body_h=1.0, color=(0.08, 0.08, 0.09))
    if fp_class == "usb_c":
        pads = []
        for i in range(6):
            x = -3.0 + i * 1.2
            pads.append(PadDef(str(i + 1), x, 2.4, 0.6, 1.4))
        # shell mounting (thru)
        pads.append(PadDef("S1", -4.3, 0, 1.0, 1.8, shape="oval", thru=True, drill=0.9))
        pads.append(PadDef("S2", 4.3, 0, 1.0, 1.8, shape="oval", thru=True, drill=0.9))
        return FootprintGeom(pads=pads, body_hw=4.4, body_hh=3.2, body_h=3.2, color=(0.7, 0.7, 0.74))
    if fp_class == "connector":
        pads = []
        for i in range(4):
            x = -3.81 + i * 2.54
            pads.append(PadDef(str(i + 1), x, 0, 1.7, 1.7,
                               shape=("rect" if i == 0 else "circle"), thru=True, drill=1.0))
        return FootprintGeom(pads=pads, body_hw=5.3, body_hh=1.27, body_h=8.5, color=(0.05, 0.05, 0.06))
    if fp_class == "tp":
        return FootprintGeom(
            pads=[PadDef("1", 0, 0, 1.6, 1.6, shape="circle", thru=True, drill=0.8)],
            body_hw=0.8, body_hh=0.8, body_h=0.2, color=(0.8, 0.7, 0.2),
        )
    return chip(0.825, 0.8, 0.95, 0.8, 0.45, (0.18, 0.18, 0.2))


def _pad_layers(pad: PadDef) -> str:
    if pad.thru:
        return '(layers "*.Cu" "*.Mask")'
    return '(layers "F.Cu" "F.Paste" "F.Mask")'


def _footprint_body(
    ref: str,
    value: str,
    geom: FootprintGeom,
    fp_class: str,
    at_x: float,
    at_y: float,
    pad_nets: dict[str, tuple[int, str]],
) -> str:
    val = value or ref
    has_thru = any(p.thru for p in geom.pads)
    attr = "through_hole" if has_thru else "smd"
    hw, hh = geom.body_hw, geom.body_hh
    cy = max(hh + 1.2, 1.4)

    parts: list[str] = [
        f'  (footprint "circuit_agent:{_esc(fp_class)}"',
        '    (layer "F.Cu")',
        f'    (uuid "{_uid()}")',
        f'    (at {at_x:.4f} {at_y:.4f})',
        f'    (attr {attr})',
        f'    (property "Reference" "{_esc(ref)}"',
        f'      (at 0 {-cy:.3f} 0) (layer "F.SilkS") (uuid "{_uid()}")',
        '      (effects (font (size 1 1) (thickness 0.15))))',
        f'    (property "Value" "{_esc(val)}"',
        f'      (at 0 {cy:.3f} 0) (layer "F.Fab") (uuid "{_uid()}")',
        '      (effects (font (size 1 1) (thickness 0.15))))',
    ]

    # Silkscreen body outline + courtyard rectangle.
    parts.append(
        f'    (fp_rect (start {-hw:.3f} {-hh:.3f}) (end {hw:.3f} {hh:.3f})'
        f' (stroke (width 0.12) (type solid)) (fill no) (layer "F.SilkS") (uuid "{_uid()}"))'
    )
    parts.append(
        f'    (fp_rect (start {-(hw + 0.25):.3f} {-(hh + 0.25):.3f}) (end {hw + 0.25:.3f} {hh + 0.25:.3f})'
        f' (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd") (uuid "{_uid()}"))'
    )

    for pad in geom.pads:
        net = pad_nets.get(pad.number)
        net_tok = ""
        if net is not None and net[0] > 0:
            net_tok = f' (net {net[0]} "{_esc(net[1])}")'
        pad_type = "thru_hole" if pad.thru else "smd"
        drill = f" (drill {pad.drill})" if pad.thru and pad.drill else ""
        rr = " (roundrect_rratio 0.25)" if pad.shape == "roundrect" else ""
        parts.append(
            f'    (pad "{pad.number}" {pad_type} {pad.shape} (at {pad.x:.3f} {pad.y:.3f})'
            f' (size {pad.w:.3f} {pad.h:.3f}){drill} {_pad_layers(pad)}{rr}{net_tok}'
            f' (uuid "{_uid()}"))'
        )

    parts.append("  )")
    return "\n".join(parts)


def _assign_nets(model: CircuitModel) -> dict[str, int]:
    names: list[str] = []
    for net in model.nets:
        if net.name not in names:
            names.append(net.name)
    return {name: i + 1 for i, name in enumerate(names)}


def _pin_to_pad(geom: FootprintGeom, pin: str, used: set[str]) -> Optional[str]:
    """Best-effort map a schematic pin name to a physical pad number."""
    pad_numbers = [p.number for p in geom.pads]
    if pin in pad_numbers:
        return pin
    # Common 2-pin aliases.
    alias2 = {"A": "1", "K": "2", "+": "1", "-": "2", "P": "1", "N": "2"}
    if pin in alias2 and alias2[pin] in pad_numbers:
        return alias2[pin]
    # Fall back to next unused pad in order.
    for n in pad_numbers:
        if n not in used:
            return n
    return pad_numbers[0] if pad_numbers else None


def _pad_world(at: tuple[float, float], pad: PadDef) -> tuple[float, float]:
    return at[0] + pad.x, at[1] + pad.y


def compile_pcb(
    model: CircuitModel,
    out_dir: str,
    *,
    basename: str = "design",
    soldermask_color: str = DEFAULT_SOLDERMASK,
) -> CompilePCBResult:
    os.makedirs(out_dir, exist_ok=True)
    notes: list[str] = []
    pcb_path = os.path.join(out_dir, f"{basename}.kicad_pcb")

    comps = list(model.components)
    if not comps:
        return CompilePCBResult(ok=False, pcb_path=None, notes=["No components to place on PCB."])

    net_map = _assign_nets(model)

    # ref -> {pin: (net_num, net_name)}
    ref_pin_net: dict[str, dict[str, tuple[int, str]]] = {}
    for net in model.nets:
        nnum = net_map.get(net.name, 0)
        for conn in net.connections:
            try:
                ref, pin = split_refpin(conn)
            except ValueError:
                continue
            ref_pin_net.setdefault(ref, {})[str(pin)] = (nnum, net.name)

    placements: dict[str, tuple[float, float]] = {}
    geoms: dict[str, FootprintGeom] = {}
    pad_net_by_ref: dict[str, dict[str, tuple[int, str]]] = {}
    fp_blocks: list[str] = []

    ox, oy = _ORIGIN
    for i, comp in enumerate(comps):
        row, col = divmod(i, _COLS)
        at_x = ox + col * _PITCH_X
        at_y = oy + row * _PITCH_Y
        placements[comp.ref] = (at_x, at_y)
        fp_class = _fp_class(comp.footprint, comp.symbol)
        geom = _geom(fp_class)
        geoms[comp.ref] = geom

        # Map this component's pins to physical pads.
        pad_nets: dict[str, tuple[int, str]] = {}
        used: set[str] = set()
        for pin, netinfo in ref_pin_net.get(comp.ref, {}).items():
            pad_num = _pin_to_pad(geom, pin, used)
            if pad_num is not None:
                pad_nets[pad_num] = netinfo
                used.add(pad_num)
        pad_net_by_ref[comp.ref] = pad_nets

        fp_blocks.append(
            _footprint_body(comp.ref, comp.value or "", geom, fp_class, at_x, at_y, pad_nets)
        )

    # Tracks per net: star route from first pad to the rest (Manhattan).
    track_lines: list[str] = []
    for net in model.nets:
        nnum = net_map.get(net.name, 0)
        pts: list[tuple[float, float]] = []
        for conn in net.connections:
            try:
                ref, pin = split_refpin(conn)
            except ValueError:
                continue
            geom = geoms.get(ref)
            if not geom:
                continue
            pad_nets = pad_net_by_ref.get(ref, {})
            pad_num = next((pn for pn, ni in pad_nets.items() if ni[0] == nnum), None)
            if pad_num is None:
                continue
            pad = next((p for p in geom.pads if p.number == pad_num), None)
            if pad is None:
                continue
            pts.append(_pad_world(placements[ref], pad))
        if len(pts) < 2:
            continue
        hub = pts[0]
        for pt in pts[1:]:
            waypts = [hub]
            if abs(hub[0] - pt[0]) > 0.01 and abs(hub[1] - pt[1]) > 0.01:
                waypts.append((pt[0], hub[1]))
            waypts.append(pt)
            for (x1, y1), (x2, y2) in zip(waypts, waypts[1:]):
                if abs(x1 - x2) < 0.01 and abs(y1 - y2) < 0.01:
                    continue
                track_lines.append(
                    f'  (segment (start {x1:.4f} {y1:.4f}) (end {x2:.4f} {y2:.4f})'
                    f' (width {_TRACK_W}) (layer "F.Cu") (net {nnum}) (uuid "{_uid()}"))'
                )

    xs = [placements[c.ref][0] for c in comps]
    ys = [placements[c.ref][1] for c in comps]
    m = _BOARD_MARGIN
    x0, y0 = min(xs) - m, min(ys) - m
    x1, y1 = max(xs) + m, max(ys) + m

    # Edge.Cuts as 4 line segments (rounded corners look better than gr_rect in 3d).
    edge = []
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for (ax, ay), (bx, by) in zip(corners, corners[1:] + corners[:1]):
        edge.append(
            f'  (gr_line (start {ax:.4f} {ay:.4f}) (end {bx:.4f} {by:.4f})'
            f' (stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "{_uid()}"))'
        )

    net_lines = ['  (net 0 "")'] + [
        f'  (net {num} "{_esc(name)}")' for name, num in net_map.items()
    ]

    body = "\n".join([
        f'(kicad_pcb (version {KICAD_PCB_VERSION}) (generator "{GENERATOR}") (generator_version "{GENERATOR_VERSION}")',
        "  (general (thickness 1.6) (legacy_teardrops no))",
        '  (paper "A4")',
        _layers_block(),
        _setup_block(soldermask_color),
        *net_lines,
        *fp_blocks,
        *track_lines,
        *edge,
        '  (embedded_fonts no)',
        ")",
    ])

    with open(pcb_path, "w", encoding="utf-8") as fh:
        fh.write(body + "\n")

    notes.append(
        f"Placed {len(comps)} footprint(s), {len(model.nets)} net(s), {len(track_lines)} track segment(s)."
    )
    return CompilePCBResult(ok=True, pcb_path=pcb_path, notes=notes)


__all__ = ["CompilePCBResult", "compile_pcb", "SOLDERMASK_COLORS", "DEFAULT_SOLDERMASK"]
