"""KiCad layer: compile to a project, run ERC, and export visuals."""

from __future__ import annotations

from circuit_agent.kicad.compile_schematic import CompileResult, compile_schematic
from circuit_agent.kicad.export_visuals import export_graph_svg, render
from circuit_agent.kicad.export_visuals import export_pdf as export_graph_pdf
from circuit_agent.kicad.parse_erc import (
    ERCResult,
    ERCViolation,
    erc_result_from_run,
    parse_erc_report,
)
from circuit_agent.kicad.run_kicad_cli import (
    ERCRun,
    export_pdf,
    export_svg,
    find_kicad_cli,
    kicad_available,
    run_erc,
)

__all__ = [
    "compile_schematic",
    "CompileResult",
    "run_erc",
    "export_svg",
    "export_pdf",
    "find_kicad_cli",
    "kicad_available",
    "ERCRun",
    "parse_erc_report",
    "ERCResult",
    "ERCViolation",
    "erc_result_from_run",
    "render",
    "export_graph_svg",
    "export_graph_pdf",
]
