#!/usr/bin/env python3
"""Compile a circuit design to KiCad artifacts and export visuals.

Accepts either a serialized ``CircuitModel`` (``circuit.json``) or a sandbox
program (``.py`` defining ``build() -> Circuit``). Always emits the hand-rolled
graph SVG (no external dependencies). Best-effort emits a ``.kicad_sch`` project,
a PDF (via cairosvg if installed), and -- when KiCad is available -- a KiCad SVG.

Example::

    python scripts/export_design.py --design runs/demo/best/circuit.json --out runs/demo/export
"""

from __future__ import annotations

import sys
import pathlib

# --- src/ path shim ---
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

import argparse

from circuit_agent.dsl.schema import CircuitModel
from circuit_agent.dsl.sandbox import run_program, SandboxError
from circuit_agent.kicad.compile_schematic import compile_schematic
from circuit_agent.kicad.export_visuals import export_graph_svg, export_pdf
from circuit_agent.kicad.run_kicad_cli import (
    kicad_available,
    export_svg as kicad_export_svg,
    export_pdf as kicad_export_pdf,
)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="export_design",
        description="Compile a circuit design to KiCad artifacts and export visuals.",
    )
    parser.add_argument(
        "--design",
        required=True,
        help="Path to a circuit.json (CircuitModel) OR a .py program defining build().",
    )
    parser.add_argument("--out", required=True, help="Output directory for artifacts.")

    kicad_group = parser.add_mutually_exclusive_group()
    kicad_group.add_argument(
        "--kicad",
        dest="kicad",
        action="store_true",
        default=None,
        help="Force-enable KiCad export (default: auto-detect).",
    )
    kicad_group.add_argument(
        "--no-kicad",
        dest="kicad",
        action="store_false",
        help="Force-disable KiCad export (graph SVG only).",
    )
    return parser


def load_design(path: str) -> CircuitModel:
    """Load a CircuitModel from a JSON model dump or a sandbox program file."""
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"design file not found: {path}")
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".py":
        return run_program(text)
    return CircuitModel.model_validate_json(text)


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    try:
        model = load_design(args.design)
    except SandboxError as exc:
        print(f"error: failed to run program '{args.design}':\n{exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"error: could not load design '{args.design}': {exc}", file=sys.stderr)
        return 2

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    produced: dict[str, str | None] = {
        "kicad_project": None,
        "kicad_schematic": None,
        "svg": None,
        "pdf": None,
    }

    # 1. Compile to a (best-effort) KiCad project.
    compile_res = compile_schematic(model, str(out_dir))
    if compile_res.ok:
        produced["kicad_project"] = compile_res.project_path
        produced["kicad_schematic"] = compile_res.schematic_path
    else:
        print("note: KiCad compilation did not fully succeed:", file=sys.stderr)
        for n in compile_res.notes:
            print(f"  - {n}", file=sys.stderr)

    # 2. Always emit the dependency-free graph SVG.
    svg_path = str(out_dir / "schematic.svg")
    svg_path = export_graph_svg(model, svg_path)
    produced["svg"] = svg_path

    # 3. Best-effort PDF from the SVG (cairosvg if installed).
    pdf_path = export_pdf(svg_path, str(out_dir / "schematic.pdf"))
    if pdf_path:
        produced["pdf"] = pdf_path

    # 4. When KiCad is available (and not disabled), prefer its native renders.
    use_kicad = args.kicad
    if use_kicad is None:
        use_kicad = kicad_available()

    if use_kicad and produced["kicad_schematic"]:
        k_svg = kicad_export_svg(produced["kicad_schematic"], str(out_dir / "kicad_svg"))
        if k_svg:
            produced["svg"] = k_svg  # prefer KiCad's render when it succeeds
        k_pdf = kicad_export_pdf(produced["kicad_schematic"], str(out_dir / "kicad_schematic.pdf"))
        if k_pdf:
            produced["pdf"] = k_pdf
    elif use_kicad and not produced["kicad_schematic"]:
        print("note: --kicad requested but no .kicad_sch was produced; using graph SVG.", file=sys.stderr)

    print()
    print(f"Design: {model.name}")
    print("Produced artifacts:")
    for label, path in produced.items():
        print(f"  {label:<16} {path if path else '(none)'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
