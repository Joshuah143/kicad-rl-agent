"""Locate and drive the ``kicad-cli`` executable.

All functions degrade gracefully: if KiCad is not installed they return a result
indicating failure rather than raising, so the rest of the pipeline can skip
ERC/exports cleanly.
"""

from __future__ import annotations

import glob
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional

_CACHED_CLI: Optional[str] = None
_CACHE_SET = False


def find_kicad_cli() -> Optional[str]:
    """Return a path to ``kicad-cli`` or ``None``. Result is cached."""
    global _CACHED_CLI, _CACHE_SET
    if _CACHE_SET:
        return _CACHED_CLI

    found = shutil.which("kicad-cli")
    if not found:
        candidates = [
            "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
            "/usr/bin/kicad-cli",
            "/usr/local/bin/kicad-cli",
        ]
        candidates.extend(glob.glob("C:/Program Files/KiCad/*/bin/kicad-cli.exe"))
        for cand in candidates:
            if shutil.os.path.exists(cand):
                found = cand
                break

    _CACHED_CLI = found
    _CACHE_SET = True
    return _CACHED_CLI


def kicad_available() -> bool:
    """Return ``True`` if a usable ``kicad-cli`` was found."""
    return find_kicad_cli() is not None


@dataclass
class ERCRun:
    """The outcome of attempting to run ERC."""

    ok: bool
    report_path: Optional[str]
    returncode: int
    stdout: str
    stderr: str


def run_erc(sch_path: str, out_report: str, fmt: str = "json") -> ERCRun:
    """Run ``kicad-cli sch erc`` on ``sch_path``; never raises."""
    cli = find_kicad_cli()
    if not cli:
        return ERCRun(ok=False, report_path=None, returncode=-1, stdout="", stderr="kicad-cli not found")
    try:
        proc = subprocess.run(
            [cli, "sch", "erc", "--output", out_report, "--format", fmt, sch_path],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ERCRun(ok=False, report_path=None, returncode=-1, stdout="", stderr=str(exc))
    return ERCRun(
        ok=proc.returncode in (0, 5),  # kicad-cli returns 5 when violations exist
        report_path=out_report,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def export_svg(sch_path: str, out_dir: str) -> Optional[str]:
    """Export a schematic to SVG via kicad-cli; return a produced path or None."""
    cli = find_kicad_cli()
    if not cli:
        return None
    try:
        proc = subprocess.run(
            [cli, "sch", "export", "svg", "--output", out_dir, sch_path],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    svgs = sorted(glob.glob(shutil.os.path.join(out_dir, "*.svg")))
    return svgs[0] if svgs else None


def export_pdf(sch_path: str, out_pdf: str) -> Optional[str]:
    """Export a schematic to PDF via kicad-cli; return the path or None."""
    cli = find_kicad_cli()
    if not cli:
        return None
    try:
        proc = subprocess.run(
            [cli, "sch", "export", "pdf", "--output", out_pdf, sch_path],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return out_pdf if shutil.os.path.exists(out_pdf) else None


def export_pcb_svg(
    pcb_path: str,
    out_svg: str,
    *,
    layers: str = "F.Cu,F.SilkS,Edge.Cuts,B.Cu",
) -> Optional[str]:
    """Export PCB layer stack to a single SVG; return path or None."""
    cli = find_kicad_cli()
    if not cli or not shutil.os.path.exists(pcb_path):
        return None
    try:
        proc = subprocess.run(
            [
                cli, "pcb", "export", "svg",
                "--output", out_svg,
                "--layers", layers,
                "--page-size-mode", "2",
                "--exclude-drawing-sheet",
                "--mode-single",
                pcb_path,
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return out_svg if shutil.os.path.exists(out_svg) else None


def export_pcb_glb(pcb_path: str, out_glb: str) -> Optional[str]:
    """Export an interactive 3D GLB model from a PCB; return path or None."""
    cli = find_kicad_cli()
    if not cli or not shutil.os.path.exists(pcb_path):
        return None
    try:
        proc = subprocess.run(
            [
                cli, "pcb", "export", "glb",
                "--output", out_glb,
                "--include-tracks",
                "--include-pads",
                "--include-silkscreen",
                "--include-soldermask",
                "--force",
                pcb_path,
            ],
            capture_output=True,
            text=True,
            timeout=240,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return out_glb if shutil.os.path.exists(out_glb) else None


def export_pcb_render_png(
    pcb_path: str,
    out_png: str,
    *,
    width: int = 1600,
    height: int = 900,
    rotate: str = "325,0,330",
) -> Optional[str]:
    """Render KiCad 3D view to PNG (fallback when GLB unavailable).

    Note: ``--rotate`` values must be non-negative (the CLI parser treats a
    leading ``-`` as a flag), so use equivalents like ``325`` instead of ``-35``.
    """
    cli = find_kicad_cli()
    if not cli or not shutil.os.path.exists(pcb_path):
        return None
    try:
        proc = subprocess.run(
            [
                cli, "pcb", "render",
                "--output", out_png,
                "--width", str(width),
                "--height", str(height),
                "--quality", "high",
                "--side", "top",
                "--background", "transparent",
                # follow_pcb_editor uses the editor's green board theme -> a proper
                # green PCB instead of the bare-FR4 brown default. (KiCad 9.0.2's
                # render predates --use-board-stackup-colors, so this is how we
                # control board appearance.)
                "--preset", "follow_pcb_editor",
                "--perspective",
                "--rotate", rotate,
                pcb_path,
            ],
            capture_output=True,
            text=True,
            timeout=240,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return out_png if shutil.os.path.exists(out_png) else None


# Standard fabrication layer set (2-layer board): copper, mask, silk, paste, edge.
_FAB_GERBER_LAYERS = "F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,F.Paste,B.Paste,Edge.Cuts"


def export_gerbers(
    pcb_path: str,
    out_dir: str,
    *,
    layers: str = _FAB_GERBER_LAYERS,
) -> Optional[str]:
    """Plot fabrication Gerbers (X2) for ``pcb_path`` into ``out_dir``.

    Returns ``out_dir`` on success or ``None``.
    """
    cli = find_kicad_cli()
    if not cli or not shutil.os.path.exists(pcb_path):
        return None
    shutil.os.makedirs(out_dir, exist_ok=True)
    try:
        proc = subprocess.run(
            [
                cli, "pcb", "export", "gerbers",
                "--output", out_dir,
                "--layers", layers,
                "--no-protel-ext",
                pcb_path,
            ],
            capture_output=True,
            text=True,
            timeout=240,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return out_dir


def export_drill(pcb_path: str, out_dir: str) -> Optional[str]:
    """Generate Excellon drill files (+ a drill map) into ``out_dir``."""
    cli = find_kicad_cli()
    if not cli or not shutil.os.path.exists(pcb_path):
        return None
    shutil.os.makedirs(out_dir, exist_ok=True)
    try:
        proc = subprocess.run(
            [
                cli, "pcb", "export", "drill",
                "--output", out_dir + shutil.os.sep,
                "--format", "excellon",
                "--excellon-separate-th",
                "--generate-map",
                "--map-format", "gerberx2",
                pcb_path,
            ],
            capture_output=True,
            text=True,
            timeout=240,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return out_dir


def export_pos(pcb_path: str, out_csv: str) -> Optional[str]:
    """Generate a pick-and-place position file (CSV)."""
    cli = find_kicad_cli()
    if not cli or not shutil.os.path.exists(pcb_path):
        return None
    try:
        proc = subprocess.run(
            [
                cli, "pcb", "export", "pos",
                "--output", out_csv,
                "--side", "both",
                "--format", "csv",
                "--units", "mm",
                pcb_path,
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return out_csv if shutil.os.path.exists(out_csv) else None


def export_step(pcb_path: str, out_step: str) -> Optional[str]:
    """Export a STEP mechanical model of the board."""
    cli = find_kicad_cli()
    if not cli or not shutil.os.path.exists(pcb_path):
        return None
    try:
        proc = subprocess.run(
            [
                cli, "pcb", "export", "step",
                "--output", out_step,
                "--no-dnp",
                "--force",
                pcb_path,
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return out_step if shutil.os.path.exists(out_step) else None


def run_pcb_drc(pcb_path: str, out_report: str, fmt: str = "json") -> ERCRun:
    """Run ``kicad-cli pcb drc``; never raises. Reuses the ERCRun shape."""
    cli = find_kicad_cli()
    if not cli or not shutil.os.path.exists(pcb_path):
        return ERCRun(ok=False, report_path=None, returncode=-1, stdout="", stderr="kicad-cli/pcb not found")
    try:
        proc = subprocess.run(
            [cli, "pcb", "drc", "--output", out_report, "--format", fmt, pcb_path],
            capture_output=True,
            text=True,
            timeout=240,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ERCRun(ok=False, report_path=None, returncode=-1, stdout="", stderr=str(exc))
    return ERCRun(
        ok=proc.returncode in (0, 5),
        report_path=out_report,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
