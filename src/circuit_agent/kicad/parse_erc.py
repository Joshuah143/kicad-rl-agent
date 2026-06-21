"""Parse KiCad ERC reports (JSON or text) into a structured result."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from circuit_agent.kicad.run_kicad_cli import ERCRun


class ERCViolation(BaseModel):
    """A single ERC violation."""

    severity: str
    type: str
    description: str
    sheet: Optional[str] = None


class ERCResult(BaseModel):
    """Aggregated ERC outcome."""

    error_count: int = 0
    warning_count: int = 0
    violations: list[ERCViolation] = Field(default_factory=list)
    raw: str = ""
    parsed: bool = False


def _parse_json_report(data: dict, raw: str) -> ERCResult:
    """Parse the kicad-cli JSON ERC schema (sheets -> violations)."""
    violations: list[ERCViolation] = []
    errors = 0
    warnings = 0
    for sheet in data.get("sheets", []):
        sheet_name = sheet.get("path") or sheet.get("name")
        for v in sheet.get("violations", []):
            severity = str(v.get("severity", "error")).lower()
            vtype = str(v.get("type", "unknown"))
            desc = str(v.get("description", v.get("message", "")))
            violations.append(
                ERCViolation(severity=severity, type=vtype, description=desc, sheet=sheet_name)
            )
            if severity == "error":
                errors += 1
            elif severity == "warning":
                warnings += 1
    return ERCResult(
        error_count=errors,
        warning_count=warnings,
        violations=violations,
        raw=raw,
        parsed=True,
    )


def parse_erc_report(path: str) -> ERCResult:
    """Parse an ERC report file. Tolerates a missing file (``parsed=False``)."""
    p = Path(path)
    if not p.exists():
        return ERCResult(parsed=False)
    raw = p.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return _parse_json_report(data, raw)
    except (json.JSONDecodeError, ValueError):
        pass

    # Text fallback: count lines mentioning error/warning.
    errors = sum(1 for line in raw.splitlines() if "error" in line.lower())
    warnings = sum(1 for line in raw.splitlines() if "warning" in line.lower())
    return ERCResult(error_count=errors, warning_count=warnings, raw=raw, parsed=True)


def erc_result_from_run(run: ERCRun) -> Optional[ERCResult]:
    """Parse ``run.report_path`` if present, else return ``None``."""
    if not run.report_path:
        return None
    return parse_erc_report(run.report_path)
