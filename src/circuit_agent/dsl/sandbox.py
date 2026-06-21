"""Safely turn a model-authored program string into a :class:`CircuitModel`.

The program defines ``build() -> Circuit`` and uses ONLY the injected builder
API (no imports). Two layers of defence:

1. :func:`validate_program_ast` statically rejects imports, dunder access,
   denied builtins and dangerous module names.
2. :func:`run_program` re-validates, then executes the program in a *subprocess*
   with a timeout. An in-process fallback (:func:`run_program_in_namespace`)
   exists for environments where spawning a subprocess fails; it offers weaker
   isolation and is only used as a last resort.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from circuit_agent.dsl.builder import Circuit
from circuit_agent.dsl.schema import CircuitModel


class SandboxError(Exception):
    """Raised when a program is unsafe, malformed, or fails to produce a model."""


# Safe builtins exposed to the executed program.
ALLOWED_BUILTINS: dict = {
    "range": range,
    "len": len,
    "enumerate": enumerate,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "zip": zip,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
    "sorted": sorted,
    "reversed": reversed,
    "map": map,
    "filter": filter,
    "any": any,
    "all": all,
    "print": print,
    "True": True,
    "False": False,
    "None": None,
}

# Names that must never appear (callable escapes / introspection).
DENIED_NAMES: set[str] = {
    "__import__",
    "open",
    "exec",
    "eval",
    "compile",
    "input",
    "globals",
    "locals",
    "vars",
    "getattr",
    "setattr",
    "delattr",
    "exit",
    "quit",
    "help",
    "memoryview",
    "breakpoint",
}

# Module names that must not be referenced even as bare identifiers.
DENIED_MODULE_NAMES: set[str] = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "shutil",
    "pathlib",
    "importlib",
}


def validate_program_ast(code: str) -> None:
    """Statically validate ``code``; raise :class:`SandboxError` on anything unsafe."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:  # pragma: no cover - defensive
        raise SandboxError(f"syntax error in program: {exc}") from exc

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise SandboxError("imports are not allowed in sandboxed programs")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise SandboxError(f"dunder attribute access is not allowed: {node.attr!r}")
        if isinstance(node, ast.Name):
            if node.id in DENIED_NAMES:
                raise SandboxError(f"use of denied name is not allowed: {node.id!r}")
            if node.id in DENIED_MODULE_NAMES:
                raise SandboxError(f"reference to dangerous module is not allowed: {node.id!r}")


def _make_namespace() -> dict:
    """Build the restricted global namespace for executing a program."""
    return {
        "__builtins__": dict(ALLOWED_BUILTINS),
        "Circuit": Circuit,
    }


def run_program_in_namespace(code: str) -> CircuitModel:
    """Execute ``code`` in-process under a restricted namespace.

    WEAKER ISOLATION than :func:`run_program`: it relies solely on the AST
    validator + restricted builtins and shares the parent interpreter. Used only
    as a fallback when a subprocess cannot be spawned.
    """
    validate_program_ast(code)
    namespace = _make_namespace()
    try:
        exec(compile(code, "<sandbox>", "exec"), namespace)  # noqa: S102 - sandboxed
    except Exception as exc:  # noqa: BLE001
        raise SandboxError(f"program raised during execution: {exc}") from exc

    build = namespace.get("build")
    if not callable(build):
        raise SandboxError("program must define a callable build()")

    try:
        result = build()
    except Exception as exc:  # noqa: BLE001
        raise SandboxError(f"build() raised: {exc}") from exc

    if isinstance(result, CircuitModel):
        return result
    if isinstance(result, Circuit):
        return result.to_model()
    raise SandboxError("build() must return a Circuit (or CircuitModel)")


# Runner executed inside the subprocess. Reads the program from stdin, runs it
# under the restricted namespace, prints the model JSON to stdout.
_RUNNER = r"""
import json, sys, pathlib
sys.path.insert(0, %(src)r)
from circuit_agent.dsl.sandbox import run_program_in_namespace
code = sys.stdin.read()
try:
    model = run_program_in_namespace(code)
except Exception as exc:  # noqa: BLE001
    sys.stderr.write(str(exc))
    sys.exit(2)
sys.stdout.write(model.model_dump_json())
"""


def _src_dir() -> str:
    """Return the ``src/`` directory so the subprocess can import circuit_agent."""
    # this file: src/circuit_agent/dsl/sandbox.py -> parents[2] == src/
    return str(Path(__file__).resolve().parents[2])


def run_program(code: str, timeout: float = 10.0) -> CircuitModel:
    """Validate then execute ``code`` in a subprocess; return the CircuitModel.

    On timeout, non-zero exit, or unparseable output, raise :class:`SandboxError`
    (including the captured stderr). If spawning the subprocess fails entirely,
    fall back to the weaker in-process runner.
    """
    validate_program_ast(code)

    runner = _RUNNER % {"src": _src_dir()}
    try:
        proc = subprocess.run(
            [sys.executable, "-c", runner],
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise SandboxError(f"program timed out after {timeout}s") from exc
    except (OSError, ValueError):
        # Could not spawn the subprocess at all -> degrade to in-process.
        return run_program_in_namespace(code)

    if proc.returncode != 0:
        raise SandboxError(proc.stderr.strip() or "program exited with a non-zero status")

    out = proc.stdout.strip()
    if not out:
        raise SandboxError(proc.stderr.strip() or "program produced no output")

    try:
        return CircuitModel.model_validate_json(out)
    except Exception as exc:  # noqa: BLE001
        raise SandboxError(f"could not parse program output into a CircuitModel: {exc}") from exc
