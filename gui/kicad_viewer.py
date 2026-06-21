"""KiCad-style design viewer: Schematic | Trace | 3D.

Trace and 3D use KiCad's *native* renderer via ``kicad-cli`` operating on a
``.kicad_pcb`` compiled from the circuit:

- Trace  -> ``pcb export svg``  (real copper/silkscreen plot)
- 3D     -> ``pcb export glb``  (interactive, shown with <model-viewer>)
- 3D     -> ``pcb render``      (ray-traced still, "Photo" mode)

If KiCad is unavailable the custom SVG/Three.js renderers are used as fallback.
"""

from __future__ import annotations

import base64
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Optional

import streamlit as st
import streamlit.components.v1 as components

from pcb_render import render_board_3d_html, render_trace_svg
from schematic import render_schematic_svg


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _kicad_available() -> bool:
    try:
        from circuit_agent.kicad.run_kicad_cli import kicad_available
        return kicad_available()
    except Exception:
        return False


def _circuit_hash(circuit: dict) -> str:
    blob = json.dumps(circuit, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:12]


def _pcb_workdir(cand_dir: Path, digest: str) -> Path:
    """A writable directory to hold the compiled board + exports."""
    candidate = cand_dir / "_pcb"
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        probe = candidate / ".w"
        probe.write_text("ok")
        probe.unlink()
        return candidate
    except Exception:
        tmp = Path(tempfile.gettempdir()) / "kicad_rl_pcb" / digest
        tmp.mkdir(parents=True, exist_ok=True)
        return tmp


@st.cache_data(show_spinner=False)
def _build_pcb_assets(
    circuit_json: str, cand_dir_str: str, digest: str, soldermask_color: str = "Green"
) -> dict:
    """Compile a PCB and export native trace SVG + GLB + render PNG.

    Cached by (circuit, dir, colour). Returns a dict of available asset paths.
    """
    out: dict = {"ok": False, "notes": [], "pcb": None, "trace_svg": None,
                 "glb": None, "render_png": None}
    try:
        from circuit_agent.dsl.schema import CircuitModel
        from circuit_agent.kicad.compile_pcb import compile_pcb
        from circuit_agent.kicad.run_kicad_cli import (
            export_pcb_glb,
            export_pcb_render_png,
            export_pcb_svg,
        )
    except Exception as exc:  # pragma: no cover
        out["notes"].append(f"import failed: {exc}")
        return out

    model = CircuitModel.model_validate(json.loads(circuit_json))
    workdir = _pcb_workdir(Path(cand_dir_str), digest)
    res = compile_pcb(model, str(workdir), soldermask_color=soldermask_color)
    out["notes"].extend(res.notes)
    if not res.ok or not res.pcb_path:
        return out
    out["pcb"] = res.pcb_path

    trace = workdir / "trace.svg"
    if export_pcb_svg(res.pcb_path, str(trace),
                      layers="F.Cu,B.Cu,F.SilkS,F.Fab,Edge.Cuts"):
        out["trace_svg"] = str(trace)

    glb = workdir / "board.glb"
    if export_pcb_glb(res.pcb_path, str(glb)):
        out["glb"] = str(glb)

    png = workdir / "render.png"
    if export_pcb_render_png(res.pcb_path, str(png), width=1100, height=800):
        out["render_png"] = str(png)

    out["ok"] = True
    return out


def _model_viewer_html(glb_path: str, height: int = 540) -> str:
    data = Path(glb_path).read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    src = f"data:model/gltf-binary;base64,{b64}"
    return f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <script type="module"
      src="https://unpkg.com/@google/model-viewer@3.5.0/dist/model-viewer.min.js"></script>
    <style>
      html, body {{ margin: 0; padding: 0; background: transparent; }}
      model-viewer {{
        width: 100%; height: {height}px;
        background: linear-gradient(180deg, #f8fafc 0%, #eef1f6 100%);
        border-radius: 12px;
        --poster-color: transparent;
      }}
      .hint {{
        position: absolute; bottom: 10px; left: 12px;
        font: 12px -apple-system, system-ui, sans-serif; color: #64748b;
        background: rgba(255,255,255,0.7); padding: 3px 8px; border-radius: 6px;
      }}
    </style>
  </head>
  <body>
    <model-viewer
      src="{src}"
      camera-controls
      auto-rotate
      auto-rotate-delay="600"
      rotation-per-second="18deg"
      shadow-intensity="1"
      exposure="1.1"
      camera-orbit="35deg 65deg 240mm"
      min-camera-orbit="auto auto auto"
      max-camera-orbit="auto auto 600mm"
      interaction-prompt="none">
      <div class="hint">drag to orbit · scroll to zoom · right-drag to pan</div>
    </model-viewer>
  </body>
</html>
"""


def _kicad_schematic_svg(cand_dir: Path) -> Optional[str]:
    for name in ("design.svg", "schematic_kicad.svg"):
        p = cand_dir / name
        if p.exists():
            return _read_text(p)

    sch = cand_dir / "design.kicad_sch"
    if not sch.exists():
        return None
    try:
        from circuit_agent.kicad.run_kicad_cli import export_svg, kicad_available
    except Exception:
        return None
    if not kicad_available():
        return None
    out = cand_dir / "design.svg"
    if not out.exists():
        produced = export_svg(str(sch), str(cand_dir))
        if produced:
            out = Path(produced)
    return _read_text(out) if out.exists() else None


def render_design_viewer(circuit: Optional[dict], cand_dir: Path) -> None:
    """Three-tab KiCad-like viewer for one candidate directory."""
    view = st.radio(
        "View",
        ["Schematic", "Trace", "3D"],
        horizontal=True,
        label_visibility="collapsed",
    )

    st.markdown(
        '<div class="viewer-toolbar">'
        f'<span class="view-label">{view}</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    if not circuit:
        st.info("No circuit data — viewer unavailable.")
        return

    if view == "Schematic":
        svg = _kicad_schematic_svg(cand_dir)
        source = "KiCad Eeschema export" if svg else "Netlist schematic renderer"
        if not svg:
            try:
                svg = render_schematic_svg(circuit)
            except Exception as exc:
                st.warning(f"Could not render schematic: {exc}")
                return
        st.caption(source)
        st.markdown(f'<div class="sheet viewer-sheet">{svg}</div>', unsafe_allow_html=True)
        return

    # Trace / 3D both need a compiled board.
    assets: dict = {"ok": False}
    if _kicad_available():
        digest = _circuit_hash(circuit)
        with st.spinner("Compiling board with KiCad…"):
            assets = _build_pcb_assets(json.dumps(circuit, default=str), str(cand_dir), digest)

    if view == "Trace":
        svg = _read_text(Path(assets["trace_svg"])) if assets.get("trace_svg") else None
        if svg:
            st.caption("KiCad native plot · F.Cu / B.Cu / silkscreen / edge cuts")
            st.markdown(
                f'<div class="sheet viewer-sheet trace-sheet">{svg}</div>',
                unsafe_allow_html=True,
            )
            return
        # Fallback.
        try:
            from circuit_agent.dsl.schema import CircuitModel
            model = CircuitModel.model_validate(circuit)
            svg = render_trace_svg(model)
        except Exception as exc:
            st.warning(f"Could not render trace view: {exc}")
            return
        st.caption("Top copper (F.Cu) · fallback renderer (KiCad CLI unavailable)")
        st.markdown(
            f'<div class="sheet viewer-sheet trace-sheet">{svg}</div>',
            unsafe_allow_html=True,
        )
        return

    # 3D
    glb = assets.get("glb")
    render_png = assets.get("render_png")
    if glb:
        modes = ["Interactive"] + (["Photo (ray-traced)"] if render_png else [])
        mode = st.segmented_control(
            "3D mode", modes, default="Interactive", label_visibility="collapsed"
        ) if len(modes) > 1 else "Interactive"
        if mode == "Interactive":
            st.caption("KiCad GLB model · drag to orbit, scroll to zoom")
            components.html(_model_viewer_html(glb, height=540), height=560, scrolling=False)
        else:
            st.caption("KiCad ray-traced render (`pcb render`)")
            st.image(render_png, width="stretch")
        return

    # Fallback Three.js.
    try:
        from circuit_agent.dsl.schema import CircuitModel
        model = CircuitModel.model_validate(circuit)
        html = render_board_3d_html(model, height=540)
    except Exception as exc:
        st.warning(f"Could not render 3D view: {exc}")
        return
    st.caption("Interactive 3D board · fallback renderer (KiCad CLI unavailable)")
    components.html(html, height=560, scrolling=False)


__all__ = ["render_design_viewer"]
