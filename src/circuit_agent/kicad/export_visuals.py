"""Always-available visual export: a hand-rolled SVG graph of the circuit.

This has NO external dependencies and is the *reliable* visual for a design (the
KiCad-native SVG/PDF export is best-effort and only available when KiCad is
installed). Components are drawn as boxes in a grid; nets as labeled hub nodes
with thin lines to each connected component. Power nets are emphasised.
"""

from __future__ import annotations

import html
import os
from typing import Optional

from circuit_agent.dsl.schema import CircuitModel, split_refpin

_POWER_NET_NAMES = {"GND", "GNDA", "AGND", "DGND", "+5V", "+3V3", "+3.3V", "VBUS", "VCC", "VDD", "5V", "3V3"}


def _is_power_net(name: str, net_class: Optional[str]) -> bool:
    if name.upper() in {n.upper() for n in _POWER_NET_NAMES}:
        return True
    if net_class and ("power" in net_class.lower() or "gnd" in net_class.lower()):
        return True
    return False


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def export_graph_svg(model: CircuitModel, out_svg: str, *, task=None) -> str:
    """Render ``model`` to a self-contained SVG at ``out_svg``; return the path."""
    os.makedirs(os.path.dirname(os.path.abspath(out_svg)) or ".", exist_ok=True)

    comps = list(model.components)
    nets = list(model.nets)

    box_w, box_h = 150, 70
    gap_x, gap_y = 60, 60
    cols = max(1, int(len(comps) ** 0.5) or 1)
    margin = 40

    comp_pos: dict[str, tuple[int, int]] = {}
    for i, comp in enumerate(comps):
        r, c = divmod(i, cols)
        x = margin + c * (box_w + gap_x)
        y = margin + 60 + r * (box_h + gap_y)
        comp_pos[comp.ref] = (x, y)

    comp_rows = (len(comps) + cols - 1) // cols if comps else 0
    net_y0 = margin + 60 + comp_rows * (box_h + gap_y) + 40
    net_pos: dict[str, tuple[int, int]] = {}
    for i, net in enumerate(nets):
        x = margin + (i % max(1, cols + 1)) * (box_w + gap_x)
        y = net_y0 + (i // max(1, cols + 1)) * 70
        net_pos[net.name] = (x + box_w // 2, y)

    width = margin * 2 + cols * (box_w + gap_x)
    net_rows = (len(nets) + cols) // max(1, cols + 1) if nets else 0
    height = net_y0 + net_rows * 70 + margin

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="sans-serif">'
    )
    parts.append(f'<text x="{margin}" y="30" font-size="22" font-weight="bold">{_esc(model.name)}</text>')

    # Edges first (so boxes draw on top).
    for net in nets:
        if net.name not in net_pos:
            continue
        nx, ny = net_pos[net.name]
        power = _is_power_net(net.name, net.net_class)
        stroke = "#b00020" if power else "#888"
        sw = 2.5 if power else 1.0
        for conn in net.connections:
            try:
                ref, _pin = split_refpin(conn)
            except ValueError:
                continue
            if ref not in comp_pos:
                continue
            cx, cy = comp_pos[ref]
            parts.append(
                f'<line x1="{cx + box_w // 2}" y1="{cy + box_h // 2}" x2="{nx}" y2="{ny}" '
                f'stroke="{stroke}" stroke-width="{sw}"/>'
            )

    # Component boxes.
    for comp in comps:
        x, y = comp_pos[comp.ref]
        parts.append(
            f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="6" '
            f'fill="#f5f7fa" stroke="#333" stroke-width="1.2"/>'
        )
        parts.append(f'<text x="{x + 8}" y="{y + 20}" font-size="14" font-weight="bold">{_esc(comp.ref)}</text>')
        parts.append(f'<text x="{x + 8}" y="{y + 38}" font-size="11">{_esc(comp.value or "")}</text>')
        parts.append(f'<text x="{x + 8}" y="{y + 54}" font-size="9" fill="#555">{_esc(comp.symbol)}</text>')

    # Net hubs.
    for net in nets:
        if net.name not in net_pos:
            continue
        nx, ny = net_pos[net.name]
        power = _is_power_net(net.name, net.net_class)
        fill = "#b00020" if power else "#3366cc"
        radius = 9 if power else 6
        parts.append(f'<circle cx="{nx}" cy="{ny}" r="{radius}" fill="{fill}"/>')
        weight = "bold" if power else "normal"
        parts.append(
            f'<text x="{nx + 12}" y="{ny + 4}" font-size="12" font-weight="{weight}" '
            f'fill="{fill}">{_esc(net.name)}</text>'
        )

    parts.append("</svg>")
    svg = "\n".join(parts)

    with open(out_svg, "w", encoding="utf-8") as fh:
        fh.write(svg)
    return out_svg


def export_pdf(svg_path: str, out_pdf: str) -> Optional[str]:
    """Best-effort SVG -> PDF. Returns the path or ``None``; never raises."""
    try:
        import cairosvg  # type: ignore
    except ImportError:
        return None
    try:
        os.makedirs(os.path.dirname(os.path.abspath(out_pdf)) or ".", exist_ok=True)
        cairosvg.svg2pdf(url=svg_path, write_to=out_pdf)
    except Exception:  # noqa: BLE001 - never raise from a visual exporter
        return None
    return out_pdf if os.path.exists(out_pdf) else None


def render(model: CircuitModel, out_dir: str, *, basename: str = "schematic") -> dict:
    """Render the graph SVG plus a best-effort PDF; return their paths."""
    os.makedirs(out_dir, exist_ok=True)
    svg_path = os.path.join(out_dir, f"{basename}.svg")
    export_graph_svg(model, svg_path)
    pdf_path = export_pdf(svg_path, os.path.join(out_dir, f"{basename}.pdf"))
    return {"svg": svg_path, "pdf": pdf_path}
