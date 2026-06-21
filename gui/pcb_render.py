"""PCB trace (2D) and board (3D) renderers from a circuit netlist.

These produce KiCad-style views without requiring a loadable ``.kicad_pcb``:
* **Trace** — top-down copper, silkscreen, pads and board outline (SVG).
* **3D** — interactive Three.js board with extruded parts and copper (HTML).
"""

from __future__ import annotations

import html
import json
from typing import Optional

from circuit_agent.dsl.schema import CircuitModel, split_refpin

# Shared layout constants (mm, same grid as compile_pcb).
_ORIGIN = (50.0, 50.0)
_COLS = 4
_PITCH_X = 14.0
_PITCH_Y = 12.0
_BOARD_MARGIN = 8.0
_TRACK_W = 0.45

_BOARD_GREEN = "#2d6a4f"
_COPPER = "#c9a227"
_MASK = "#1b4332"
_SILK = "#f8fafc"
_OUTLINE = "#94a3b8"
_PAD = "#d4af37"


def _esc(t: object) -> str:
    return html.escape(str(t), quote=True)


def _fp_class(footprint: Optional[str], symbol: str) -> str:
    fp = (footprint or "").lower()
    if "0603" in fp or "1608" in fp:
        return "0603"
    if "0805" in fp:
        return "0805"
    if "sot-23" in fp:
        return "sot23"
    if "qfn" in fp or "usb" in fp or "connector" in (symbol or "").lower():
        return "wide"
    if symbol.startswith("Device:R") or symbol.startswith("Device:C") or symbol.startswith("Device:LED"):
        return "0603"
    return "0603"


def _body_size(fp_class: str) -> tuple[float, float, float]:
    """Return (width, depth, height) mm for 3D extrusion."""
    if fp_class == "0805":
        return 2.0, 1.25, 0.55
    if fp_class == "sot23":
        return 2.9, 2.8, 1.1
    if fp_class == "wide":
        return 8.0, 6.0, 2.0
    return 1.6, 0.8, 0.55  # 0603 default


def _pad_offsets(fp_class: str) -> dict[str, tuple[float, float]]:
    if fp_class == "0603":
        return {"1": (-0.95, 0), "2": (0.95, 0), "A": (-0.95, 0), "K": (0.95, 0)}
    if fp_class == "0805":
        return {"1": (-1.15, 0), "2": (1.15, 0), "A": (-1.15, 0), "K": (1.15, 0)}
    if fp_class == "sot23":
        return {"1": (-0.95, -1), "2": (-0.95, 0), "3": (-0.95, 1), "4": (1, 0), "5": (1, 0)}
    if fp_class == "wide":
        return {str(i): (-3.5 + (i - 1) * 2.3, 0) for i in range(1, 5)}
    return {"1": (-0.95, 0), "2": (0.95, 0), "A": (-0.95, 0), "K": (0.95, 0)}


def _layout(model: CircuitModel):
    comps = list(model.components)
    placements: dict[str, tuple[float, float, str, str]] = {}
    for i, c in enumerate(comps):
        row, col = divmod(i, _COLS)
        x = _ORIGIN[0] + col * _PITCH_X
        y = _ORIGIN[1] + row * _PITCH_Y
        fp = _fp_class(c.footprint, c.symbol)
        placements[c.ref] = (x, y, fp, c.value or c.ref)

    pin_pos: dict[tuple[str, str], tuple[float, float]] = {}
    for net in model.nets:
        for conn in net.connections:
            try:
                ref, pin = split_refpin(conn)
            except ValueError:
                continue
            if ref not in placements:
                continue
            bx, by, fp, _ = placements[ref]
            off = _pad_offsets(fp).get(pin, _pad_offsets(fp).get("1", (0, 0)))
            pin_pos[(ref, pin)] = (bx + off[0], by + off[1])

    xs = [p[0] for p in placements.values()] or [_ORIGIN[0]]
    ys = [p[1] for p in placements.values()] or [_ORIGIN[1]]
    board = (
        min(xs) - _BOARD_MARGIN,
        min(ys) - _BOARD_MARGIN,
        max(xs) + _BOARD_MARGIN,
        max(ys) + _BOARD_MARGIN,
    )
    return placements, pin_pos, board


def _route(points: list[tuple[float, float]]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    if len(points) < 2:
        return []
    segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    hub = points[0]
    for pt in points[1:]:
        if abs(hub[0] - pt[0]) > 0.01 and abs(hub[1] - pt[1]) > 0.01:
            mid = (pt[0], hub[1])
            segs.extend([(hub, mid), (mid, pt)])
        elif abs(hub[0] - pt[0]) > 0.01 or abs(hub[1] - pt[1]) > 0.01:
            segs.append((hub, pt))
    return segs


def render_trace_svg(model: CircuitModel, *, width: int = 900) -> str:
    """Top-down PCB trace view as SVG."""
    placements, pin_pos, board = _layout(model)
    x0, y0, x1, y1 = board
    bh, bw = y1 - y0, x1 - x0
    scale = min((width - 40) / bw, 8.0)
    ox, oy = 20 - x0 * scale, 20 - y0 * scale

    def tx(x: float, y: float) -> tuple[float, float]:
        return ox + x * scale, oy + y * scale

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{int(bh * scale + 40)}" viewBox="0 0 {width} {int(bh * scale + 40)}">'
    )
    parts.append(f'<rect width="100%" height="100%" fill="#f1f5f9"/>')

    # Board body.
    bx, by = tx(x0, y0)
    parts.append(
        f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw * scale:.1f}" height="{bh * scale:.1f}" '
        f'rx="4" fill="{_BOARD_GREEN}" stroke="{_OUTLINE}" stroke-width="1.5"/>'
    )

    # Copper tracks per net.
    for net in model.nets:
        pts = []
        for conn in net.connections:
            try:
                ref, pin = split_refpin(conn)
            except ValueError:
                continue
            if (ref, pin) in pin_pos:
                pts.append(pin_pos[(ref, pin)])
        for (a, b) in _route(pts):
            x1p, y1p = tx(*a)
            x2p, y2p = tx(*b)
            parts.append(
                f'<line x1="{x1p:.1f}" y1="{y1p:.1f}" x2="{x2p:.1f}" y2="{y2p:.1f}" '
                f'stroke="{_COPPER}" stroke-width="{max(2, _TRACK_W * scale):.1f}" '
                f'stroke-linecap="round"/>'
            )

    # Pads + silkscreen refs.
    for ref, (cx, cy, fp, val) in placements.items():
        w, d, _ = _body_size(fp)
        px, py = tx(cx, cy)
        pw, ph = w * scale * 0.9, d * scale * 0.9
        parts.append(
            f'<rect x="{px - pw / 2:.1f}" y="{py - ph / 2:.1f}" width="{pw:.1f}" height="{ph:.1f}" '
            f'fill="#64748b" stroke="{_SILK}" stroke-width="0.8" rx="1"/>'
        )
        parts.append(
            f'<text x="{px:.1f}" y="{py - ph / 2 - 4:.1f}" text-anchor="middle" '
            f'font-family="JetBrains Mono,monospace" font-size="10" fill="{_SILK}">{_esc(ref)}</text>'
        )
        for pin, (oxp, oyp) in _pad_offsets(fp).items():
            if (ref, pin) not in pin_pos and pin not in ("A", "K", "3", "4", "5"):
                continue
            if (ref, pin) in pin_pos:
                ppx, ppy = tx(*pin_pos[(ref, pin)])
            else:
                ppx, ppy = tx(cx + oxp, cy + oyp)
            parts.append(f'<circle cx="{ppx:.1f}" cy="{ppy:.1f}" r="{max(2.5, 0.5 * scale):.1f}" fill="{_PAD}"/>')

    parts.append(
        f'<text x="16" y="{int(bh * scale + 28)}" font-family="Inter,sans-serif" '
        f'font-size="11" fill="#64748b">{_esc(model.name)} · trace view (F.Cu)</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def render_board_3d_html(model: CircuitModel, *, height: int = 520) -> str:
    """Interactive Three.js 3D board viewer."""
    placements, pin_pos, board = _layout(model)
    x0, y0, x1, y1 = board
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

    parts_3d = []
    for ref, (px, py, fp, val) in placements.items():
        w, d, h = _body_size(fp)
        parts_3d.append({
            "ref": ref,
            "value": val,
            "x": px - cx,
            "y": py - cy,
            "w": w,
            "d": d,
            "h": h,
            "color": "#64748b" if fp == "0603" else "#475569",
        })

    tracks_3d = []
    for net in model.nets:
        pts = []
        for conn in net.connections:
            try:
                ref, pin = split_refpin(conn)
            except ValueError:
                continue
            if (ref, pin) in pin_pos:
                p = pin_pos[(ref, pin)]
                pts.append((p[0], p[1]))
        for (a, b) in _route(pts):
            tracks_3d.append([
                [a[0] - cx, a[1] - cy],
                [b[0] - cx, b[1] - cy],
            ])

    payload = json.dumps({
        "name": model.name,
        "board": {"w": x1 - x0, "h": y1 - y0},
        "parts": parts_3d,
        "tracks": tracks_3d,
    })

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"/>
<style>
  html,body{{margin:0;padding:0;background:#eef2f7;overflow:hidden;font-family:Inter,system-ui,sans-serif}}
  #info{{position:absolute;left:14px;top:12px;color:#334155;font-size:12px;pointer-events:none;z-index:2}}
  #hint{{position:absolute;right:14px;bottom:10px;color:#94a3b8;font-size:11px;pointer-events:none}}
  canvas{{display:block;width:100%;height:{height}px}}
</style>
</head><body>
<div id="info"><b id="title"></b><br><span id="sub"></span></div>
<div id="hint">drag to orbit · scroll to zoom</div>
<script type="importmap">{{"imports":{{"three":"https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/"}}}}</script>
<script type="module">
import * as THREE from 'three';
import {{ OrbitControls }} from 'three/addons/controls/OrbitControls.js';
const DATA = {payload};
document.getElementById('title').textContent = DATA.name;
document.getElementById('sub').textContent = DATA.parts.length + ' parts · ' + DATA.tracks.length + ' track segments';

const el = document.body;
const W = el.clientWidth || 800, H = {height};
const renderer = new THREE.WebGLRenderer({{antialias:true}});
renderer.setSize(W, H);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xeef2f7);
const camera = new THREE.PerspectiveCamera(42, W/H, 0.1, 500);
camera.position.set(0, -38, 32);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.target.set(0, 0, 0.8);

scene.add(new THREE.AmbientLight(0xffffff, 0.55));
const key = new THREE.DirectionalLight(0xffffff, 0.85);
key.position.set(20, -15, 40);
key.castShadow = true;
scene.add(key);
const fill = new THREE.DirectionalLight(0xdbeafe, 0.35);
fill.position.set(-25, 20, 10);
scene.add(fill);

// Board (FR4 green).
const boardGeo = new THREE.BoxGeometry(DATA.board.w, DATA.board.h, 1.6);
const boardMat = new THREE.MeshStandardMaterial({{color:0x2d6a4f, roughness:0.75, metalness:0.05}});
const board = new THREE.Mesh(boardGeo, boardMat);
board.position.z = 0.8;
board.receiveShadow = true;
scene.add(board);

// Edge outline.
const edgeShape = new THREE.Shape();
const hw=DATA.board.w/2, hh=DATA.board.h/2;
edgeShape.moveTo(-hw,-hh); edgeShape.lineTo(hw,-hh); edgeShape.lineTo(hw,hh); edgeShape.lineTo(-hw,hh); edgeShape.closePath();
const edgeGeo = new THREE.EdgesGeometry(new THREE.ShapeGeometry(edgeShape));
// skip edge - board box is enough

// Copper tracks.
const copperMat = new THREE.MeshStandardMaterial({{color:0xc9a227, roughness:0.35, metalness:0.85}});
for (const [[x1,y1],[x2,y2]] of DATA.tracks) {{
  const dx=x2-x1, dy=y2-y1, len=Math.hypot(dx,dy)||0.01;
  const geo = new THREE.BoxGeometry(len, 0.45, 0.08);
  const mesh = new THREE.Mesh(geo, copperMat);
  mesh.position.set((x1+x2)/2, (y1+y2)/2, 1.68);
  mesh.rotation.z = Math.atan2(dy, dx);
  scene.add(mesh);
}}

// Components.
for (const p of DATA.parts) {{
  const geo = new THREE.BoxGeometry(p.w, p.d, p.h);
  const mat = new THREE.MeshStandardMaterial({{color: parseInt(p.color.replace('#','0x')), roughness:0.45, metalness:0.25}});
  const mesh = new THREE.Mesh(geo, mat);
  mesh.position.set(p.x, p.y, 1.6 + p.h/2);
  mesh.castShadow = true;
  scene.add(mesh);
}}

function animate() {{
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}}
animate();
window.addEventListener('resize', () => {{
  const w = el.clientWidth || W, h = {height};
  camera.aspect = w/h; camera.updateProjectionMatrix();
  renderer.setSize(w, h);
}});
</script></body></html>"""


__all__ = ["render_trace_svg", "render_board_3d_html"]
