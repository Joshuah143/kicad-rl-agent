#!/usr/bin/env python3
"""Validate a circuit design against a task and print a readable report.

Accepts either a serialized ``CircuitModel`` (``circuit.json``) or a sandbox
program (``.py`` defining ``build() -> Circuit``). Runs the deterministic
validator suite -- graph rules, electrical rules, BOM cost, package size,
availability -- and prints a pass/fail summary. Pure-local: no KiCad, no
network, no API key required.

Example::

    python scripts/validate_design.py --design runs/demo/best/circuit.json --task tasks/usb_c_5v_led.yaml
"""

from __future__ import annotations

import sys
import pathlib

# --- src/ path shim ---
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

import argparse

from circuit_agent.dsl.schema import CircuitModel
from circuit_agent.dsl.sandbox import run_program, SandboxError
from circuit_agent.task import load_task
from circuit_agent.validators import graph_rules, electrical_rules
from circuit_agent.validators import bom_cost, package_size, availability
from circuit_agent.validators.base import Severity, ValidatorResult


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_design",
        description="Run the deterministic validator suite on a circuit design.",
    )
    parser.add_argument(
        "--design",
        required=True,
        help="Path to a circuit.json (CircuitModel) OR a .py program defining build().",
    )
    parser.add_argument("--task", required=True, help="Path to the task YAML spec.")
    return parser


def load_design(path: str) -> CircuitModel:
    """Load a CircuitModel from a JSON model dump or a sandbox program file."""
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"design file not found: {path}")
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".py":
        return run_program(text)
    # Default: treat as a serialized CircuitModel.
    return CircuitModel.model_validate_json(text)


def _print_validator_result(res: ValidatorResult) -> None:
    """Print one ValidatorResult block with its issues grouped by severity."""
    frac = res.fraction()
    status = "PASS" if res.passed else "FAIL"
    print(f"[{status}] {res.name}: {res.score:.2f}/{res.max_score:.2f}  ({frac * 100:.0f}%)")
    for issue in res.issues:
        if issue.severity == Severity.FATAL:
            marker = "FATAL"
        elif issue.severity == Severity.WARNING:
            marker = "warn "
        else:
            marker = "info "
        refs = f"  [{', '.join(issue.refs)}]" if issue.refs else ""
        print(f"    {marker}  {issue.code}: {issue.message}{refs}")


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    try:
        model = load_design(args.design)
    except SandboxError as exc:
        print(f"error: failed to run program '{args.design}':\n{exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - malformed JSON / missing file etc.
        print(f"error: could not load design '{args.design}': {exc}", file=sys.stderr)
        return 2

    try:
        task = load_task(args.task)
    except Exception as exc:  # noqa: BLE001
        print(f"error: could not load task '{args.task}': {exc}", file=sys.stderr)
        return 2

    print(f"Design: {model.name}  ({len(model.components)} components, {len(model.nets)} nets)")
    print(f"Task:   {task.name}")
    print()

    graph_res = graph_rules.check(model)
    elec_res = electrical_rules.check(model, task)

    print("== Validators ==")
    _print_validator_result(graph_res)
    _print_validator_result(elec_res)
    print()

    bom = bom_cost.compute(model)
    size = package_size.compute(model)
    avail = availability.compute(model)

    print("== Metrics ==")
    print(f"  BOM cost:        ${bom.get('total_cost_usd', 0.0):.4f}")
    if bom.get("missing_cost_refs"):
        print(f"    (missing cost for: {', '.join(bom['missing_cost_refs'])})")
    print(f"  Total area:      {size.get('total_area_mm2', 0.0):.2f} mm^2")
    print(
        f"  SMT/THT/virtual: {size.get('smt_count', 0)}"
        f"/{size.get('tht_count', 0)}/{size.get('virtual_count', 0)}"
    )
    largest = size.get("largest") or {}
    if largest.get("ref"):
        print(f"  Largest part:    {largest['ref']} ({largest.get('area', 0.0):.2f} mm^2)")
    print(f"  Min availability: {avail.get('min_availability')}")
    print(f"  Avg availability: {avail.get('avg_availability')}")
    if avail.get("low_availability"):
        print(f"    (low availability: {', '.join(avail['low_availability'])})")
    print()

    overall_pass = graph_res.passed and elec_res.passed
    fatal_count = len(graph_res.fatals) + len(elec_res.fatals)
    warn_count = len(graph_res.warnings) + len(elec_res.warnings)

    print("== Overall ==")
    print(f"  Result:   {'PASS' if overall_pass else 'FAIL'}")
    print(f"  Fatals:   {fatal_count}")
    print(f"  Warnings: {warn_count}")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
