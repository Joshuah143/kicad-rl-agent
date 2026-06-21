"""End-to-end design verifier.

``verify_design`` is the single entrypoint that turns one validated
:class:`~circuit_agent.dsl.schema.CircuitModel` into a deterministic reward plus
a set of on-disk artifacts. It runs entirely **locally by default** and only
reaches for KiCad when the ``kicad-cli`` binary is available; the hand-rolled SVG
graph is always produced so a visual exists even on machines without KiCad.

Modal is used *only* as a remote sandbox (KiCad image) for running the same
pipeline at scale. ``modal`` is imported lazily inside :func:`verify_design`
(behind ``use_modal=True``) so that importing this module — and the whole
``circuit_agent.infra`` package — never hard-requires Modal.

The function never raises on a *well-formed* model: any pipeline trouble is
folded into the reward's ``warnings``/``fatal_errors`` instead of propagating.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Optional

from circuit_agent.dsl.schema import CircuitModel
from circuit_agent.task import TaskSpec

if TYPE_CHECKING:  # pragma: no cover - typing only
    from circuit_agent.kicad.parse_erc import ERCResult
    from circuit_agent.validators.llm_critic import Critic


__all__ = ["verify_design"]


def _write_json(path: str, payload) -> None:
    """Write ``payload`` as pretty JSON to ``path`` (best effort)."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def _as_plain(obj):
    """Return a plain JSON-serialisable representation of ``obj``.

    Accepts pydantic models (``model_dump``) and falls back to the object as-is
    for plain dicts/values.
    """
    if obj is None:
        return None
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        return dump()
    return obj


def verify_design(
    model: CircuitModel,
    task: TaskSpec,
    out_dir: str,
    *,
    use_kicad: Optional[bool] = None,
    export: bool = True,
    critic: "Optional[Critic]" = None,
    use_modal: bool = False,
) -> dict:
    """Score one :class:`CircuitModel` end-to-end and write artifacts.

    Parameters
    ----------
    model:
        The validated circuit to evaluate.
    task:
        The :class:`TaskSpec` providing objectives/preferences/weights.
    out_dir:
        Directory to write artifacts into (created if missing).
    use_kicad:
        ``None`` -> auto-detect ``kicad-cli``; ``True``/``False`` to force.
    export:
        When ``True`` also produce visual artifacts (SVG always, PDF best-effort).
    critic:
        Optional LLM critic. When provided its :meth:`Critic.review` result feeds
        the ``llm_critic`` reward component.
    use_modal:
        When ``True`` dispatch the whole evaluation to the Modal sandbox; falls
        back to local execution (with a note) if Modal is unavailable.

    Returns
    -------
    dict
        ``{"reward": <reward dict>, "artifacts": {...}, "erc_ran": bool}``.
    """
    os.makedirs(out_dir, exist_ok=True)

    # --- Optional remote dispatch to the Modal sandbox -----------------------
    if use_modal:
        try:
            from circuit_agent.infra import modal_app  # lazy: never import at module load

            remote = modal_app.run_on_modal(model, task)
            # Persist what came back so the local artifact contract still holds.
            return _materialise_remote_result(remote, out_dir)
        except Exception as exc:  # pragma: no cover - depends on modal/network
            # Degrade gracefully to local execution; record why.
            _modal_fallback_note = (
                f"Modal dispatch failed ({type(exc).__name__}: {exc}); ran locally instead."
            )
            return _verify_local(
                model,
                task,
                out_dir,
                use_kicad=use_kicad,
                export=export,
                critic=critic,
                extra_warnings=[_modal_fallback_note],
            )

    return _verify_local(
        model,
        task,
        out_dir,
        use_kicad=use_kicad,
        export=export,
        critic=critic,
        extra_warnings=[],
    )


def _verify_local(
    model: CircuitModel,
    task: TaskSpec,
    out_dir: str,
    *,
    use_kicad: Optional[bool],
    export: bool,
    critic: "Optional[Critic]",
    extra_warnings: list[str],
) -> dict:
    """The local evaluation pipeline (also what runs inside the Modal container)."""
    # Imports are local to keep the infra package importable with only
    # pydantic/pyyaml when nobody calls the verifier.
    import importlib

    # The package re-exports the compile_schematic *function* under the same name
    # as its submodule, so both `from circuit_agent.kicad import compile_schematic`
    # and `import circuit_agent.kicad.compile_schematic as x` yield the function
    # (the `as` form resolves the last component by attribute access). import_module
    # resolves via sys.modules and always returns the real submodule.
    _compile_mod = importlib.import_module("circuit_agent.kicad.compile_schematic")
    from circuit_agent.kicad import export_visuals as _visuals
    from circuit_agent.kicad import parse_erc as _parse_erc
    from circuit_agent.kicad import run_kicad_cli as _kicad_cli
    from circuit_agent.validators import availability as _availability
    from circuit_agent.validators import bom_cost as _bom_cost
    from circuit_agent.validators import electrical_rules as _electrical
    from circuit_agent.validators import graph_rules as _graph
    from circuit_agent.validators import package_size as _package_size
    from circuit_agent.validators import reward as _reward

    notes: list[str] = list(extra_warnings)

    artifacts: dict[str, Optional[str]] = {
        "kicad_project": None,
        "kicad_schematic": None,
        "erc": None,
        "svg": None,
        "pdf": None,
        "bom": None,
        "critic": None,
        "reward": None,
    }

    # --- 1. Compile to a (best-effort) KiCad project -------------------------
    schematic_path: Optional[str] = None
    try:
        compile_res = _compile_mod.compile_schematic(model, out_dir, basename="design")
        if getattr(compile_res, "ok", False):
            artifacts["kicad_project"] = getattr(compile_res, "project_path", None)
            artifacts["kicad_schematic"] = getattr(compile_res, "schematic_path", None)
            schematic_path = getattr(compile_res, "schematic_path", None)
        else:
            notes.append("KiCad compile did not succeed; relying on SVG graph visual.")
        for n in getattr(compile_res, "notes", []) or []:
            notes.append(str(n))
    except Exception as exc:  # never abort on a compile hiccup
        notes.append(f"compile_schematic raised {type(exc).__name__}: {exc}")

    # --- 2. ERC (only when KiCad is available) -------------------------------
    erc_ran = False
    erc_result: "Optional[ERCResult]" = None
    if use_kicad is None:
        try:
            use_kicad = bool(_kicad_cli.kicad_available())
        except Exception:
            use_kicad = False

    if use_kicad and schematic_path and os.path.exists(schematic_path):
        try:
            report_path = os.path.join(out_dir, "erc.rpt")
            run = _kicad_cli.run_erc(schematic_path, report_path, fmt="json")
            if getattr(run, "ok", False):
                erc_result = _parse_erc.erc_result_from_run(run)
                if erc_result is not None and getattr(erc_result, "parsed", False):
                    erc_ran = True
                    artifacts["erc"] = getattr(run, "report_path", None) or report_path
                else:
                    notes.append("ERC report could not be parsed; treating ERC as skipped.")
            else:
                notes.append("kicad-cli ERC run failed; treating ERC as skipped.")
        except Exception as exc:
            notes.append(f"ERC step raised {type(exc).__name__}: {exc}; ERC skipped.")
    elif use_kicad and not (schematic_path and os.path.exists(schematic_path)):
        notes.append("No schematic available for ERC; ERC skipped.")

    # --- 3. Visual export (SVG always; PDF best-effort) ----------------------
    if export:
        try:
            svg_path = os.path.join(out_dir, "schematic.svg")
            artifacts["svg"] = _visuals.export_graph_svg(model, svg_path, task=task)
        except Exception as exc:
            notes.append(f"SVG graph export raised {type(exc).__name__}: {exc}.")

        # Best-effort PDF from the graph SVG.
        if artifacts["svg"]:
            try:
                pdf_path = os.path.join(out_dir, "schematic.pdf")
                produced = _visuals.export_pdf(artifacts["svg"], pdf_path)
                if produced:
                    artifacts["pdf"] = produced
            except Exception as exc:
                notes.append(f"PDF export raised {type(exc).__name__}: {exc}.")

        # If KiCad is around, prefer its native renders when they succeed.
        if use_kicad and schematic_path and os.path.exists(schematic_path):
            try:
                kicad_svg = _kicad_cli.export_svg(schematic_path, out_dir)
                if kicad_svg and os.path.exists(kicad_svg):
                    artifacts["svg"] = kicad_svg
            except Exception as exc:
                notes.append(f"kicad-cli SVG export raised {type(exc).__name__}: {exc}.")
            try:
                kicad_pdf = os.path.join(out_dir, "schematic_kicad.pdf")
                produced = _kicad_cli.export_pdf(schematic_path, kicad_pdf)
                if produced and os.path.exists(produced):
                    artifacts["pdf"] = produced
            except Exception as exc:
                notes.append(f"kicad-cli PDF export raised {type(exc).__name__}: {exc}.")

    # --- 4. Deterministic validators ----------------------------------------
    graph_result = _graph.check(model)
    electrical_result = _electrical.check(model, task)
    bom = _bom_cost.compute(model)
    size = _package_size.compute(model)
    avail = _availability.compute(model)

    # --- 5. Optional LLM critic ----------------------------------------------
    critic_result = None
    if critic is not None:
        try:
            validator_report = {
                "graph": graph_result,
                "electrical": electrical_result,
                "bom": bom,
                "size": size,
                "availability": avail,
            }
            critic_result = critic.review(
                task=task,
                model=model,
                erc=erc_result,
                validator_report=validator_report,
                svg_path=artifacts["svg"],
            )
        except Exception as exc:
            notes.append(f"Critic.review raised {type(exc).__name__}: {exc}; critic skipped.")
            critic_result = None

    # --- 6. Deterministic reward ---------------------------------------------
    reward_dict = _reward.compute_reward(
        model,
        task,
        schema_valid=True,
        erc=erc_result,
        erc_ran=erc_ran,
        graph=graph_result,
        electrical=electrical_result,
        bom=bom,
        size=size,
        avail=avail,
        critic=critic_result,
    )

    # Fold any pipeline notes into the reward's warnings (deterministic ordering
    # is preserved: reward warnings first, then our pipeline notes).
    if notes:
        existing = list(reward_dict.get("warnings", []))
        reward_dict["warnings"] = existing + notes

    # --- 7. Persist artifacts -------------------------------------------------
    reward_path = os.path.join(out_dir, "reward.json")
    _write_json(reward_path, reward_dict)
    artifacts["reward"] = reward_path

    bom_path = os.path.join(out_dir, "bom.json")
    _write_json(bom_path, bom)
    artifacts["bom"] = bom_path

    critic_path = os.path.join(out_dir, "critic.json")
    _write_json(critic_path, _as_plain(critic_result) or {})
    artifacts["critic"] = critic_path

    return {"reward": reward_dict, "artifacts": artifacts, "erc_ran": erc_ran}


def _materialise_remote_result(remote: dict, out_dir: str) -> dict:
    """Persist a result returned from the Modal sandbox into ``out_dir``.

    The remote function returns the reward dict plus a few inline artifacts
    (notably the SVG string). We write those out so the local artifact contract
    is preserved regardless of where the work ran.
    """
    os.makedirs(out_dir, exist_ok=True)

    reward_dict = remote.get("reward", {})
    erc_ran = bool(remote.get("erc_ran", False))
    inline = remote.get("inline", {}) or {}

    artifacts: dict[str, Optional[str]] = {
        "kicad_project": None,
        "kicad_schematic": None,
        "erc": None,
        "svg": None,
        "pdf": None,
        "bom": None,
        "critic": None,
        "reward": None,
    }

    reward_path = os.path.join(out_dir, "reward.json")
    _write_json(reward_path, reward_dict)
    artifacts["reward"] = reward_path

    bom = remote.get("bom") or {}
    bom_path = os.path.join(out_dir, "bom.json")
    _write_json(bom_path, bom)
    artifacts["bom"] = bom_path

    critic_payload = remote.get("critic") or {}
    critic_path = os.path.join(out_dir, "critic.json")
    _write_json(critic_path, critic_payload)
    artifacts["critic"] = critic_path

    svg_text = inline.get("svg")
    if isinstance(svg_text, str) and svg_text.strip():
        svg_path = os.path.join(out_dir, "schematic.svg")
        with open(svg_path, "w", encoding="utf-8") as fh:
            fh.write(svg_text)
        artifacts["svg"] = svg_path

    return {"reward": reward_dict, "artifacts": artifacts, "erc_ran": erc_ran}
