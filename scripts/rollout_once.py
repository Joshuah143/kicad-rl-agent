#!/usr/bin/env python3
"""Run a single RL rollout against a task and print a summary table.

This is the offline-friendly MVP entrypoint. With ``--backend mock`` it draws
candidate programs from the built-in reference examples (no network, no API key)
so the whole pipeline -- sandbox -> compile -> validators -> reward -- can be
exercised with only ``pydantic`` and ``pyyaml`` installed.

Example (works offline)::

    python scripts/rollout_once.py --task tasks/usb_c_5v_led.yaml --backend mock --n_candidates 3 --out runs/demo
"""

from __future__ import annotations

import sys
import pathlib

# --- src/ path shim: lets this script run without installing the package ---
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

import argparse

from circuit_agent.config import load_settings, have_fireworks
from circuit_agent.rl.factory import make_backend
from circuit_agent.rl.rollout import run_rollout
from circuit_agent.validators.llm_critic import make_critic


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rollout_once",
        description="Sample N candidate circuit programs, score each, and report the best.",
    )
    parser.add_argument("--task", required=True, help="Path to the task YAML spec.")
    parser.add_argument(
        "--backend",
        choices=["mock", "fireworks", "hud"],
        default="mock",
        help="Sampling backend (default: mock, fully offline).",
    )
    parser.add_argument(
        "--n_candidates",
        type=int,
        default=3,
        help="Number of candidate programs to sample (default: 3).",
    )
    parser.add_argument("--out", required=True, help="Output directory for artifacts.")
    parser.add_argument(
        "--model",
        default="gemma4",
        help="Policy model alias or Fireworks id (default: gemma4).",
    )

    kicad_group = parser.add_mutually_exclusive_group()
    kicad_group.add_argument(
        "--kicad",
        dest="kicad",
        action="store_true",
        default=None,
        help="Force-enable KiCad ERC (default: auto-detect).",
    )
    kicad_group.add_argument(
        "--no-kicad",
        dest="kicad",
        action="store_false",
        help="Force-disable KiCad ERC.",
    )

    parser.add_argument(
        "--critic",
        choices=["none", "stub", "fireworks"],
        default="none",
        help="LLM critic to apply (default: none).",
    )
    parser.add_argument(
        "--modal",
        action="store_true",
        help="Dispatch verification to the Modal KiCad sandbox.",
    )
    return parser


def _short_fatals(breakdown: dict, max_items: int = 2) -> str:
    """Render the first couple of fatal errors from a reward breakdown dict."""
    fatals = breakdown.get("fatal_errors") or []
    if not fatals:
        return ""
    shown = [str(f) for f in fatals[:max_items]]
    suffix = f" (+{len(fatals) - max_items} more)" if len(fatals) > max_items else ""
    return "; ".join(shown) + suffix


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    settings = load_settings(model_alias=args.model)

    # Critic construction can require a Fireworks key; surface that clearly.
    critic = None
    if args.critic != "none":
        try:
            critic = make_critic(args.critic, settings=settings)
        except Exception as exc:  # noqa: BLE001 - actionable message, no traceback
            print(f"error: could not initialise '{args.critic}' critic: {exc}", file=sys.stderr)
            return 2

    # Backend construction (fireworks/hud) may also fail with a clear message.
    try:
        backend = make_backend(
            args.backend,
            settings=settings,
            model=args.model,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"error: could not initialise '{args.backend}' backend: {exc}", file=sys.stderr)
        if args.backend == "fireworks" and not have_fireworks(settings):
            print(
                "hint: set FIREWORKS_API_KEY in your environment, or use --backend mock.",
                file=sys.stderr,
            )
        return 2

    try:
        result = run_rollout(
            args.task,
            backend,
            args.n_candidates,
            args.out,
            settings=settings,
            use_kicad=args.kicad,
            run_critic=critic is not None,
            critic=critic,
            use_modal=args.modal,
        )
    except NotImplementedError as exc:
        # HUD backend (or any stub) signals "not wired up" via NotImplementedError.
        print(f"error: {exc}", file=sys.stderr)
        print("hint: this backend is a stub. Use --backend mock or --backend fireworks.", file=sys.stderr)
        return 2
    finally:
        try:
            backend.close()
        except Exception:  # noqa: BLE001 - close must never mask the real result
            pass

    _print_summary(result)
    return 0


def _print_summary(result) -> None:
    """Pretty-print the per-candidate scoreboard and the chosen best directory."""
    print()
    print(f"Task:    {result.task}")
    print(f"Out dir: {result.out_dir}")
    print()
    header = f"{'idx':>3}  {'valid':<5}  {'reward':>8}  fatal/error"
    print(header)
    print("-" * max(len(header), 60))
    for cand in result.candidates:
        valid = "yes" if cand.valid else "no"
        reward = f"{cand.reward:.4f}"
        if cand.valid:
            note = _short_fatals(cand.reward_breakdown)
        else:
            note = (cand.error or "").splitlines()[0] if cand.error else ""
        print(f"{cand.index:>3}  {valid:<5}  {reward:>8}  {note}")
    print()
    if result.best is not None:
        best = result.best
        print(f"Best candidate: #{best.index}  (reward={best.reward:.4f})")
        best_dir = str(pathlib.Path(result.out_dir) / "best")
        print(f"Best artifacts: {best_dir}")
    else:
        print("Best candidate: none (no valid candidate produced).")


if __name__ == "__main__":
    raise SystemExit(main())
