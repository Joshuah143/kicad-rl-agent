#!/usr/bin/env python3
"""Headline entrypoint: train (RFT-style loop) or run a single rollout.

This is the one command a user runs. By default it samples candidate circuit
programs from the Fireworks-served policy, compiles each into KiCad artifacts,
scores them with the deterministic validators (+ optional LLM critic), and
reports the best. With ``--train`` it repeats the rollout for ``--iters``
iterations, exporting an RFT dataset that a real Fireworks Reinforcement
Fine-Tuning job can consume.

Supported invocations:

    # HUD backend is a documented stub -> fails with a clear, actionable message:
    python train_or_rollout.py --task tasks/usb_c_5v_led.yaml --model gemma4 \
        --backend hud --n_candidates 8 --out runs/usb_c_5v_led_001

    # Fully offline MVP:
    python train_or_rollout.py --task tasks/usb_c_5v_led.yaml --backend mock \
        --n_candidates 3 --out runs/demo
"""

from __future__ import annotations

import sys
import pathlib

# --- src/ path shim (repo root: parent / "src") ---
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "src"))

import argparse

# Only the light, always-importable config module is imported at module scope.
# The heavy import chain (rollout / train loop / verifier / critic, which pull in
# the dsl + infra layers and optional dependencies) is imported lazily inside
# main() so that the "HUD backend is a stub" actionable message stays reachable
# even when those optional modules or dependencies are absent. See the FAILURE
# AREA 'hud-stub-graceful-exit': importing them up here turned a stub-backend run
# into a raw ModuleNotFoundError traceback before the guard could fire.
from circuit_agent.config import load_settings, have_fireworks


# The HUD backend is a documented stub; surface a clear, actionable message
# instead of dragging in (and possibly crashing on) the heavy import chain.
_HUD_STUB_HINT = (
    "the 'hud' backend is a stub and is not wired up. "
    "Use --backend mock (offline) or --backend fireworks (needs FIREWORKS_API_KEY)."
)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="train_or_rollout",
        description="Train (RFT-style) or run a single rollout of the circuit policy.",
    )
    parser.add_argument("--task", required=True, help="Path to the task YAML spec.")
    parser.add_argument(
        "--model",
        default="gemma4",
        help="Policy model alias or Fireworks id (default: gemma4).",
    )
    parser.add_argument(
        "--backend",
        choices=["mock", "fireworks", "hud"],
        default="fireworks",
        help="Sampling backend (default: fireworks).",
    )
    parser.add_argument(
        "--n_candidates",
        type=int,
        default=8,
        help="Candidate programs per rollout (default: 8).",
    )
    parser.add_argument("--out", required=True, help="Output directory for artifacts.")
    parser.add_argument(
        "--train",
        action="store_true",
        help="Run the multi-iteration training loop instead of a single rollout.",
    )
    parser.add_argument(
        "--iters",
        type=int,
        default=3,
        help="Number of training iterations when --train is set (default: 3).",
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
        default="stub",
        help="LLM critic to apply (default: stub).",
    )
    parser.add_argument(
        "--modal",
        action="store_true",
        help="Dispatch verification to the Modal KiCad sandbox.",
    )
    return parser


def _short_fatals(breakdown: dict, max_items: int = 2) -> str:
    fatals = breakdown.get("fatal_errors") or []
    if not fatals:
        return ""
    shown = [str(f) for f in fatals[:max_items]]
    suffix = f" (+{len(fatals) - max_items} more)" if len(fatals) > max_items else ""
    return "; ".join(shown) + suffix


def _print_rollout_summary(result, *, header: str | None = None) -> None:
    if header:
        print(header)
    print(f"Task:    {result.task}")
    print(f"Out dir: {result.out_dir}")
    line = f"{'idx':>3}  {'valid':<5}  {'reward':>8}  fatal/error"
    print(line)
    print("-" * max(len(line), 60))
    for cand in result.candidates:
        valid = "yes" if cand.valid else "no"
        if cand.valid:
            note = _short_fatals(cand.reward_breakdown)
        else:
            note = (cand.error or "").splitlines()[0] if cand.error else ""
        print(f"{cand.index:>3}  {valid:<5}  {cand.reward:>8.4f}  {note}")
    if result.best is not None:
        best_dir = str(pathlib.Path(result.out_dir) / "best")
        print(f"Best candidate: #{result.best.index}  (reward={result.best.reward:.4f})  -> {best_dir}")
    else:
        print("Best candidate: none (no valid candidate produced).")


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    settings = load_settings(model_alias=args.model)

    # The HUD backend is a stub: short-circuit BEFORE importing the heavy rollout
    # chain so the user always gets the actionable message, never a traceback,
    # regardless of whether the optional dsl/infra modules are present.
    if args.backend == "hud":
        print(
            "error: HUDBackend is a stub: the HUD reset/step RL environment "
            "integration is not implemented in this repository.",
            file=sys.stderr,
        )
        print(f"hint: {_HUD_STUB_HINT}", file=sys.stderr)
        return 2

    # Heavy imports are deferred to here (after the HUD guard) so a stub-backend
    # invocation never depends on the full import chain succeeding.
    try:
        from circuit_agent.rl.factory import make_backend
        from circuit_agent.rl.rollout import run_rollout
        from circuit_agent.rl.train_loop import train
        from circuit_agent.validators.llm_critic import make_critic
    except Exception as exc:  # noqa: BLE001
        print(
            f"error: failed to load the rollout/training components: {exc}",
            file=sys.stderr,
        )
        print(
            "hint: ensure the circuit_agent package is fully installed; for an "
            "offline smoke test use --backend mock.",
            file=sys.stderr,
        )
        return 2

    critic = None
    if args.critic != "none":
        try:
            critic = make_critic(args.critic, settings=settings)
        except Exception as exc:  # noqa: BLE001
            print(f"error: could not initialise '{args.critic}' critic: {exc}", file=sys.stderr)
            return 2

    try:
        backend = make_backend(args.backend, settings=settings, model=args.model)
    except Exception as exc:  # noqa: BLE001
        print(f"error: could not initialise '{args.backend}' backend: {exc}", file=sys.stderr)
        if args.backend == "fireworks" and not have_fireworks(settings):
            print(
                "hint: set FIREWORKS_API_KEY in your environment, or use --backend mock.",
                file=sys.stderr,
            )
        return 2

    try:
        if args.train:
            results = train(
                args.task,
                backend,
                args.iters,
                args.n_candidates,
                args.out,
                settings=settings,
                use_kicad=args.kicad,
                run_critic=critic is not None,
                critic=critic,
                use_modal=args.modal,
            )
            print()
            print("== Training summary ==")
            for k, res in enumerate(results):
                best_reward = res.best.reward if res.best is not None else 0.0
                print(f"  iter {k:03d}: best reward = {best_reward:.4f}  ({res.out_dir})")
            if results:
                final = results[-1]
                _print_rollout_summary(final, header="\n== Final iteration ==")
        else:
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
            print()
            _print_rollout_summary(result)
    except NotImplementedError as exc:
        # HUD backend (stub) -- fail with a clear message rather than a traceback.
        print(f"error: {exc}", file=sys.stderr)
        print(
            "hint: the 'hud' backend is a stub and is not wired up. "
            "Use --backend mock (offline) or --backend fireworks (needs FIREWORKS_API_KEY).",
            file=sys.stderr,
        )
        return 2
    finally:
        try:
            backend.close()
        except Exception:  # noqa: BLE001
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
