"""Render a *proper* schematic SVG from a validated circuit dict.

Unlike the core ``export_visuals`` graph (boxes + net hubs), this draws real
electronic symbols — resistors, capacitors, LEDs, ICs, connectors, test points —
with pins, junction dots, ground/power symbols and net-label flags. It uses the
**global net-label convention** (the same connectivity model the compiler emits):
each connected pin gets a short wire stub ending in a labelled flag, exactly how
engineers draw schematics when explicit wires would clutter the sheet.

The output is a self-contained, light-themed SVG string with a sheet frame and a
title block, so it reads as an engineering schematic rather than a mock graph.
"""

from __future__ import annotations

import html
import math
from typing import Optional

# --------------------------------------------------------------------------- #
# Palette (light theme, modern engineering look)
# --------------------------------------------------------------------------- #
INK = "#1e293b"        # symbol bodies / leads
WIRE = "#64748b"       # pin stubs
PIN_TXT = "#94a3b8"    # pin numbers
REF_TXT = "#4338ca"    # component reference (R1, U1)
VAL_TXT = "#0f172a"    # component value
POWER = "#dc2626"      # +V rails
GND = "#0f172a"        # ground
SIGNAL = "#2563eb"     # signal nets
SIGNAL_BG = "#eff6ff"
SHEET = "#e2e8f0"      # sheet frame
GRID = "#f1f5f9"       # faint background grid

_POWER_NAMES = {
    "+5V", "+3V3", "+3.3V", "VBUS", "VCC", "VDD", "5V", "3V3", "+12V", "+1V8", "VIN", "VOUT",
}
_GND_NAMES = {"GND", "GNDA", "AGND", "DGND", "VSS"}


def _esc(t: object) -> str:
    return html.escape(str(t), quote=True)


def _classify_net(name: str, net_class: Optional[str]) -> str:
    up = (name or "").upper()
    if up in _GND_NAMES or "GND" in up or up == "VSS":
        return "gnd"
    if up in {n.upper() for n in _POWER_NAMES}:
        return "power"
    if net_class and ("power" in net_class.lower() or "gnd" in net_class.lower()):
        return "power"
    if up.startswith("+") or (up.startswith("V") and len(up) <= 4 and up not in {"VBUS"}):
        return "power"
    return "signal"


def _classify_comp(symbol: str) -> str:
    s = symbol or ""
    low = s.lower()
    if s.startswith("Device:R") or low.startswith("device:r"):
        return "resistor"
    if s.startswith("Device:C") or low.startswith("device:c"):
        return "capacitor"
    if s.startswith("Device:LED") or "led" in low or s.startswith("Device:D"):
        return "led"
    if "testpoint" in low:
        return "testpoint"
    if s.startswith("Connector"):
        return "connector"
    return "ic"


# --------------------------------------------------------------------------- #
# Small SVG primitives
# --------------------------------------------------------------------------- #
def _line(p, x1, y1, x2, y2, color=INK, w=2.0, cap="round"):
    p.append(
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{color}" stroke-width="{w}" stroke-linecap="{cap}"/>'
    )


def _dot(p, x, y, color=WIRE, r=2.6):
    p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}"/>')


def _text(p, x, y, s, size=12, color=INK, weight="400", anchor="start", family="ui"):
    fam = "'JetBrains Mono', ui-monospace, monospace" if family == "mono" else \
          "'Inter', system-ui, sans-serif"
    p.append(
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
        f'fill="{color}" text-anchor="{anchor}" font-family="{fam}">{_esc(s)}</text>'
    )


# --------------------------------------------------------------------------- #
# Net flags (the labelled wire-stub terminations)
# --------------------------------------------------------------------------- #
def _net_flag(p, x, y, direction, name, kind):
    """Draw a junction + stub from (x,y) outward, terminated by a net label."""
    dx, dy = direction
    stub = 24.0
    ex, ey = x + dx * stub, y + dy * stub
    _dot(p, x, y)
    _line(p, x, y, ex, ey, color=WIRE, w=1.6)

    if kind == "gnd":
        _ground(p, ex, ey, direction)
    elif kind == "power":
        _power(p, ex, ey, direction, name)
    else:
        _signal(p, ex, ey, direction, name)


def _ground(p, x, y, direction):
    dx, dy = direction
    px, py = -dy, dx  # perpendicular
    for d, hw, wdt in ((0.0, 11.0, 2.0), (6.0, 7.0, 2.0), (12.0, 3.5, 2.0)):
        bx, by = x + dx * d, y + dy * d
        _line(p, bx - px * hw, by - py * hw, bx + px * hw, by + py * hw, color=GND, w=wdt)


def _power(p, x, y, direction, name):
    dx, dy = direction
    px, py = -dy, dx
    # short perpendicular bar (the rail) then the name beyond it
    bx, by = x + dx * 2, y + dy * 2
    _line(p, bx - px * 8, by - py * 8, bx + px * 8, by + py * 8, color=POWER, w=2.4)
    tx, ty = x + dx * 12, y + dy * 12
    anchor = "middle"
    if dx > 0:
        anchor, tx = "start", x + 12
    elif dx < 0:
        anchor, tx = "end", x - 12
    if dy != 0:
        ty = y + dy * 16 + (4 if dy > 0 else 0)
    else:
        ty = y + 4
    _text(p, tx, ty, name, size=11.5, color=POWER, weight="700", anchor=anchor, family="mono")


def _signal(p, x, y, direction, name):
    dx, dy = direction
    label = str(name)
    w = max(34.0, len(label) * 7.2 + 16.0)
    h = 20.0
    # Position the tag box just past the stub end, extending in `direction`.
    if dx > 0:
        bx, by = x, y - h / 2
    elif dx < 0:
        bx, by = x - w, y - h / 2
    elif dy > 0:
        bx, by = x - w / 2, y
    else:
        bx, by = x - w / 2, y - h
    p.append(
        f'<rect x="{bx:.1f}" y="{by:.1f}" width="{w:.1f}" height="{h:.1f}" rx="5" '
        f'fill="{SIGNAL_BG}" stroke="{SIGNAL}" stroke-width="1.3"/>'
    )
    _text(p, bx + w / 2, by + h / 2 + 4, label, size=11, color="#1e40af",
          weight="600", anchor="middle", family="mono")


# --------------------------------------------------------------------------- #
# Component symbols
# --------------------------------------------------------------------------- #
PASSIVE_W, PASSIVE_H = 184, 188


def _passive_pins(used):
    """Return (top_pin, bottom_pin) ids for a 2-terminal device."""
    order = list(dict.fromkeys(used))
    if len(order) >= 2:
        return order[0], order[1]
    if len(order) == 1:
        other = "2" if order[0] != "2" else "1"
        return order[0], other
    return "1", "2"


def _draw_passive(p, x, y, kind, comp, used, pin_net, net_kind):
    cx = x + PASSIVE_W / 2
    top_y, bot_y = y + 46, y + PASSIVE_H - 46
    top_pin, bot_pin = _passive_pins(used)

    if kind == "resistor":
        bt, bb = y + 70, y + PASSIVE_H - 70
        _line(p, cx, top_y, cx, bt)
        _line(p, cx, bb, cx, bot_y)
        p.append(
            f'<rect x="{cx-13:.1f}" y="{bt:.1f}" width="26" height="{bb-bt:.1f}" rx="3" '
            f'fill="#ffffff" stroke="{INK}" stroke-width="2"/>'
        )
    elif kind == "capacitor":
        py1, py2 = y + 84, y + 98
        _line(p, cx, top_y, cx, py1)
        _line(p, cx - 17, py1, cx + 17, py1, w=2.4)
        _line(p, cx - 17, py2, cx + 17, py2, w=2.4)
        _line(p, cx, py2, cx, bot_y)
    elif kind == "led":
        ttop, tbot = y + 74, y + 104
        _line(p, cx, top_y, cx, ttop)
        p.append(
            f'<path d="M {cx-13:.1f} {ttop:.1f} L {cx+13:.1f} {ttop:.1f} '
            f'L {cx:.1f} {tbot:.1f} Z" fill="#ffffff" stroke="{INK}" stroke-width="2" '
            f'stroke-linejoin="round"/>'
        )
        _line(p, cx - 13, tbot, cx + 13, tbot, w=2.4)  # cathode bar
        _line(p, cx, tbot, cx, bot_y)
        # emission arrows
        for off in (0, 7):
            ax, ay = cx + 16 + off, ttop + 4 + off
            _line(p, ax, ay, ax + 9, ay - 9, color=INK, w=1.4)
            p.append(
                f'<path d="M {ax+9:.1f} {ay-9:.1f} l -5 1 l 4 4 z" fill="{INK}"/>'
            )

    # leads' net flags
    _net_flag(p, cx, top_y, (0, -1), pin_net.get((comp["ref"], top_pin), "?"),
              net_kind.get(pin_net.get((comp["ref"], top_pin)), "signal"))
    _net_flag(p, cx, bot_y, (0, 1), pin_net.get((comp["ref"], bot_pin), "?"),
              net_kind.get(pin_net.get((comp["ref"], bot_pin)), "signal"))

    # ref + value to the right of the body
    _text(p, cx + 26, y + PASSIVE_H / 2 - 4, comp["ref"], size=14, color=REF_TXT, weight="700")
    if comp.get("value"):
        _text(p, cx + 26, y + PASSIVE_H / 2 + 14, comp["value"], size=12, color=VAL_TXT)


def _draw_testpoint(p, x, y, comp, used, pin_net, net_kind):
    cx = x + 110 / 2
    cy = y + 70
    pin = (used or ["1"])[0]
    _line(p, cx, cy, cx, cy - 16)
    p.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5.5" fill="#ffffff" '
             f'stroke="{INK}" stroke-width="2"/>')
    _net_flag(p, cx, cy - 16, (0, -1), pin_net.get((comp["ref"], pin), "?"),
              net_kind.get(pin_net.get((comp["ref"], pin)), "signal"))
    _text(p, cx, cy + 22, comp["ref"], size=13, color=REF_TXT, weight="700", anchor="middle")
    if comp.get("value"):
        _text(p, cx, cy + 38, comp["value"], size=11, color=VAL_TXT, anchor="middle")


def _ic_dims(n_pins):
    per_side = max(1, math.ceil(n_pins / 2))
    body_h = max(96, per_side * 34 + 30)
    body_w = 132
    flag = 150
    return body_w, body_h, flag, per_side


def _draw_ic(p, x, y, comp, used, pin_net, net_kind):
    pins = list(dict.fromkeys(used)) or ["1"]
    body_w, body_h, flag, per_side = _ic_dims(len(pins))
    bx = x + flag
    by = y + 24
    p.append(
        f'<rect x="{bx:.1f}" y="{by:.1f}" width="{body_w}" height="{body_h:.1f}" rx="8" '
        f'fill="#f8fafc" stroke="{INK}" stroke-width="2"/>'
    )
    # ref + value header inside the body
    _text(p, bx + body_w / 2, by + 20, comp["ref"], size=14, color=REF_TXT,
          weight="700", anchor="middle")
    if comp.get("value"):
        _text(p, bx + body_w / 2, by + 37, comp["value"], size=10.5, color=VAL_TXT,
              anchor="middle")

    left = pins[:per_side]
    right = pins[per_side:]

    def place(side_pins, side):
        count = len(side_pins)
        if not count:
            return
        usable = body_h - 30
        step = usable / max(1, count)
        for i, pin in enumerate(side_pins):
            py = by + 30 + step * (i + 0.5)
            if side == "left":
                edge_x = bx
                stub_x = bx - 16
                _line(p, edge_x, py, stub_x, py, color=WIRE, w=1.6)
                _text(p, bx + 6, py + 3.5, pin, size=9.5, color=PIN_TXT, anchor="start", family="mono")
                _net_flag(p, stub_x, py, (-1, 0), pin_net.get((comp["ref"], pin), "?"),
                          net_kind.get(pin_net.get((comp["ref"], pin)), "signal"))
            else:
                edge_x = bx + body_w
                stub_x = edge_x + 16
                _line(p, edge_x, py, stub_x, py, color=WIRE, w=1.6)
                _text(p, bx + body_w - 6, py + 3.5, pin, size=9.5, color=PIN_TXT, anchor="end", family="mono")
                _net_flag(p, stub_x, py, (1, 0), pin_net.get((comp["ref"], pin), "?"),
                          net_kind.get(pin_net.get((comp["ref"], pin)), "signal"))

    place(left, "left")
    place(right, "right")


def _cell_size(kind, n_pins):
    if kind in ("resistor", "capacitor", "led"):
        return PASSIVE_W, PASSIVE_H
    if kind == "testpoint":
        return 110, 130
    body_w, body_h, flag, _ = _ic_dims(n_pins)
    return flag * 2 + body_w, body_h + 60


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def render_schematic_svg(circuit: dict, *, max_width: int = 1180) -> str:
    """Render ``circuit`` (a CircuitModel dict) to a schematic SVG string."""
    comps = list(circuit.get("components", []) or [])
    nets = list(circuit.get("nets", []) or [])

    # Build pin -> net and net -> kind maps.
    pin_net: dict[tuple, str] = {}
    net_kind: dict[str, str] = {}
    used_pins: dict[str, list] = {c["ref"]: [] for c in comps}
    for net in nets:
        nm = net.get("name", "")
        net_kind[nm] = _classify_net(nm, net.get("net_class"))
        for conn in net.get("connections", []) or []:
            if "." not in conn:
                continue
            ref, pin = conn.split(".", 1)
            pin_net[(ref, pin)] = nm
            if ref in used_pins and pin not in used_pins[ref]:
                used_pins[ref].append(pin)

    if not comps:
        return ('<svg xmlns="http://www.w3.org/2000/svg" width="420" height="120">'
                f'<text x="20" y="60" font-family="Inter,sans-serif" fill="{INK}">'
                'No components to render.</text></svg>')

    # Shelf-pack components into rows.
    margin = 34
    gap = 26
    x, y, row_h = margin, margin + 14, 0.0
    placements = []
    for c in comps:
        kind = _classify_comp(c.get("symbol", ""))
        n_pins = len(used_pins.get(c["ref"], [])) or 2
        w, h = _cell_size(kind, n_pins)
        if x > margin and x + w > margin + max_width:
            x = margin
            y += row_h + gap
            row_h = 0.0
        placements.append((c, kind, x, y, w, h))
        x += w + gap
        row_h = max(row_h, h)

    total_w = margin * 2 + max(
        max((px + w for (_, _, px, _, w, _) in placements), default=max_width),
        margin + 320,
    ) - margin
    total_w = max(total_w, 420)
    total_h = y + row_h + margin + 60  # extra room for title block

    p: list[str] = []
    p.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" '
        f'height="{total_h:.0f}" viewBox="0 0 {total_w:.0f} {total_h:.0f}">'
    )
    # faint dot grid background
    p.append(
        f'<defs><pattern id="grid" width="22" height="22" patternUnits="userSpaceOnUse">'
        f'<circle cx="1" cy="1" r="1" fill="{GRID}"/></pattern></defs>'
    )
    p.append(f'<rect width="{total_w:.0f}" height="{total_h:.0f}" fill="#ffffff"/>')
    p.append(f'<rect width="{total_w:.0f}" height="{total_h:.0f}" fill="url(#grid)"/>')
    # sheet frame
    p.append(
        f'<rect x="10" y="10" width="{total_w-20:.0f}" height="{total_h-20:.0f}" rx="10" '
        f'fill="none" stroke="{SHEET}" stroke-width="1.5"/>'
    )

    for c, kind, px, py, w, h in placements:
        used = used_pins.get(c["ref"], [])
        if kind in ("resistor", "capacitor", "led"):
            _draw_passive(p, px, py, kind, c, used, pin_net, net_kind)
        elif kind == "testpoint":
            _draw_testpoint(p, px, py, c, used, pin_net, net_kind)
        else:
            _draw_ic(p, px, py, c, used, pin_net, net_kind)

    # title block (bottom-right)
    tb_w, tb_h = 260, 46
    tbx, tby = total_w - tb_w - 16, total_h - tb_h - 16
    p.append(
        f'<rect x="{tbx:.1f}" y="{tby:.1f}" width="{tb_w}" height="{tb_h}" rx="8" '
        f'fill="#ffffff" stroke="{SHEET}" stroke-width="1.5"/>'
    )
    _text(p, tbx + 14, tby + 20, circuit.get("name", "circuit"), size=13,
          color=VAL_TXT, weight="700", family="mono")
    _text(p, tbx + 14, tby + 36, f"{len(comps)} parts · {len(nets)} nets · kicad-rl-agent",
          size=10, color="#94a3b8")

    p.append("</svg>")
    return "\n".join(p)
