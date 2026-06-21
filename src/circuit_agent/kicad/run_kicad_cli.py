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
