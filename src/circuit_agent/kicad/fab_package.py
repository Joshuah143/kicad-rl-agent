"""Build a vendor-ready fabrication package from a CircuitModel.

Pipeline:
    CircuitModel -> compile_pcb() -> .kicad_pcb (real, KiCad-loadable)
                 -> kicad-cli: gerbers + drill + pick&place + STEP + DRC
                 -> zip everything into <name>_fab.zip

The Gerber/drill output is genuine: a Gerber viewer opens it and a fab house
(JLCPCB / PCBWay / OSH Park) accepts it. The layout itself is auto-generated
(grid placement, simple routing, synthesized footprints) so it is sendable and
real, but not a DRC-clean production design.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from typing import Optional

from circuit_agent.dsl.schema import CircuitModel
from circuit_agent.kicad.compile_pcb import compile_pcb
from circuit_agent.kicad.run_kicad_cli import (
    export_drill,
    export_gerbers,
    export_pos,
    export_step,
    kicad_available,
    run_pcb_drc,
)


@dataclass
class FabResult:
    ok: bool
    zip_path: Optional[str] = None
    pcb_path: Optional[str] = None
    drc_report: Optional[str] = None
    contents: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def build_fab_package(
    model: CircuitModel,
    out_dir: str,
    *,
    name: str = "board",
) -> FabResult:
    """Compile a board and assemble a zipped fabrication package.

    ``out_dir`` is where the final ``<name>_fab.zip`` (and intermediate files)
    are written. Returns a :class:`FabResult` describing what was produced.
    """
    os.makedirs(out_dir, exist_ok=True)
    notes: list[str] = []

    if not kicad_available():
        return FabResult(ok=False, notes=["kicad-cli not found; cannot generate fab files."])

    # 1) Compile the board.
    pcb_dir = os.path.join(out_dir, "_pcb")
    res = compile_pcb(model, pcb_dir, basename=name)
    notes.extend(res.notes)
    if not res.ok or not res.pcb_path:
        return FabResult(ok=False, notes=notes + ["PCB compile failed."])
    pcb_path = res.pcb_path

    # 2) Stage manufacturing outputs in a clean working tree.
    work = tempfile.mkdtemp(prefix="fabpkg_")
    gerber_dir = os.path.join(work, "gerbers")
    contents: list[str] = []

    if export_gerbers(pcb_path, gerber_dir):
        notes.append("Plotted Gerbers (X2).")
    else:
        notes.append("Gerber export failed.")

    if export_drill(pcb_path, gerber_dir):  # drill files sit with the gerbers, as fabs expect
        notes.append("Generated Excellon drill files.")
    else:
        notes.append("Drill export failed.")

    pos_csv = os.path.join(work, f"{name}-pos.csv")
    if export_pos(pcb_path, pos_csv):
        notes.append("Generated pick-and-place (CPL) file.")

    step_path = os.path.join(work, f"{name}.step")
    if export_step(pcb_path, step_path):
        notes.append("Exported STEP mechanical model.")

    # Include the source board too (some shops accept native KiCad).
    shutil.copy2(pcb_path, os.path.join(work, f"{name}.kicad_pcb"))

    # 3) DRC report (advisory).
    drc_report = os.path.join(work, f"{name}-drc.json")
    drc = run_pcb_drc(pcb_path, drc_report)
    if drc.report_path and os.path.exists(drc.report_path):
        notes.append("Ran DRC (advisory report included).")
    else:
        drc_report = None

    # 4) Zip it all.
    zip_path = os.path.join(out_dir, f"{name}_fab.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(work):
            for fn in files:
                full = os.path.join(root, fn)
                arc = os.path.relpath(full, work)
                zf.write(full, arc)
                contents.append(arc)

    shutil.rmtree(work, ignore_errors=True)

    return FabResult(
        ok=True,
        zip_path=zip_path,
        pcb_path=pcb_path,
        drc_report=drc_report,
        contents=sorted(contents),
        notes=notes,
    )


__all__ = ["FabResult", "build_fab_package"]
