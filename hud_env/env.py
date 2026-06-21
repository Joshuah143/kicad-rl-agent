"""KiCad schematics HUD Environment.

A self-contained HUD (hud.ai) v6 Environment that lets an LLM agent learn to
generate KiCad-quality circuit designs. The agent's "answer" is a Python
``build() -> Circuit`` program (a string); we run it through the project's
deterministic verifier and return its *normalized* (0..1) reward.

Grading pipeline (identical for local eval, remote rollout, and training):

    answer (program text)
      -> circuit_agent.dsl.sandbox.run_program  -> CircuitModel
      -> circuit_agent.infra.verifier.verify_design  -> reward dict
      -> reward["reward"]["reward_normalized"]  (0..1, GRPO-ready)

The grading is FAIL-CLOSED: any exception (unsafe/garbage program, sandbox
rejection, verifier hiccup) yields reward 0.0 with an explanatory ``content``
and never propagates.

Verified against hud-python 0.6.6:
  - ``from hud import Environment``        (== ``hud.environment.Environment``)
  - ``from hud.graders import EvaluationResult``
        EvaluationResult(*, reward=0.0, done=True, content=None, info={}, ...)
  - ``@env.template(id=...)`` decorates an ASYNC GENERATOR that does
        ``answer = yield <prompt>`` then ``yield <EvaluationResult>``.
    With ``returns=None`` (default) the answer arrives as the raw string the
    agent produced (see hud/cli/templates.py: ``answer or ""``).
  - Calling the template (e.g. ``kicad_design(task_name=...)``) returns a
    ``hud.Task`` with settable ``.slug`` / ``.columns``.

Env vars honored:
  - KICAD_RL_TASKS_DIR     : directory of task YAMLs (else ../tasks).
  - KICAD_RL_DISABLE_ERC   : any truthy value -> skip KiCad ERC (faster
                             rollouts). Default: auto-detect kicad-cli.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from hud import Environment
from hud.graders import EvaluationResult

from circuit_agent.infra.verifier import verify_design
from circuit_agent.dsl.sandbox import run_program
from circuit_agent.rl.prompts import build_prompt
from circuit_agent.task import load_task, TaskSpec

env = Environment(name="kicad-schematics")

# The 5 shipped task base names (each has a tasks/<name>.yaml).
TASK_NAMES = [
    "usb_c_5v_led",
    "led_resistor",
    "ldo_3v3",
    "i2c_sensor_breakout",
    "mcu_minimal",
]


def _truthy(val: str | None) -> bool:
    return str(val or "").strip().lower() in {"1", "true", "yes", "on", "y"}


def tasks_dir() -> Path:
    """Locate the task YAML directory robustly.

    Prefer ``KICAD_RL_TASKS_DIR`` if set; otherwise the repo's ``tasks/`` dir
    one level up from this file (hud_env/ -> repo root -> tasks/).
    """
    env_dir = os.environ.get("KICAD_RL_TASKS_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    return Path(__file__).resolve().parent.parent / "tasks"


def load_taskspec(task_name: str) -> TaskSpec:
    """Load the :class:`TaskSpec` for ``task_name`` from the task dir."""
    path = tasks_dir() / f"{task_name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"task YAML not found: {path}")
    return load_task(path)


def _use_kicad() -> bool | None:
    """Decide the ``use_kicad`` flag for verify_design.

    ``False`` when KICAD_RL_DISABLE_ERC is truthy (fast rollouts); otherwise
    ``None`` so verify_design auto-detects a local kicad-cli.
    """
    if _truthy(os.environ.get("KICAD_RL_DISABLE_ERC")):
        return False
    return None


def _extract_answer_text(answer) -> str:
    """Coerce the agent's answer into the raw program string.

    With ``returns=None`` hud delivers a plain string. Be defensive in case a
    future SDK wraps it in an Answer-like object exposing ``.content``/``.raw``.
    """
    if answer is None:
        return ""
    if isinstance(answer, str):
        return answer
    for attr in ("content", "raw", "text"):
        val = getattr(answer, attr, None)
        if isinstance(val, str):
            return val
    return str(answer)


def grade_program(task_name: str, program_text) -> EvaluationResult:
    """Grade one program against ``task_name`` and return an EvaluationResult.

    Fully self-contained and FAIL-CLOSED: never raises. This is the single
    grading code path used by the template (and exercised directly by the
    offline smoke test), so what we test is exactly what trains.
    """
    program = _extract_answer_text(program_text)

    # Load the task spec first. A missing/broken task spec is a configuration
    # error, but we still fail closed (reward 0) rather than crash a rollout.
    try:
        taskspec = load_taskspec(task_name)
    except Exception as exc:  # noqa: BLE001
        return EvaluationResult(
            reward=0.0,
            done=True,
            content=f"task-load error: {type(exc).__name__}: {exc}",
            info={"raw_reward": 0.0, "passed": False, "fatal_errors": [str(exc)]},
        )

    out_dir = tempfile.mkdtemp(prefix=f"kicad-hud-{task_name}-")
    try:
        model = run_program(program)
        # NOTE: the installed verify_design has no ``run_critic`` kwarg (despite
        # what an older spec implied). Omitting ``critic`` is exactly "no critic"
        # -> the llm_critic component contributes 0 and is excluded from
        # reward_max, so the normalized reward stays well-calibrated.
        res = verify_design(
            model,
            taskspec,
            out_dir,
            use_kicad=_use_kicad(),
        )
        reward_dict = res.get("reward", {}) or {}
        reward01 = float(reward_dict.get("reward_normalized", 0.0) or 0.0)
        passed = bool(reward_dict.get("passed", False))
        breakdown = reward_dict.get("breakdown", {})
        fatal_errors = list(reward_dict.get("fatal_errors", []))
        raw_reward = float(reward_dict.get("reward", 0.0) or 0.0)

        top_fatals = "; ".join(fatal_errors[:3]) if fatal_errors else "none"
        content = (
            f"passed={passed} reward={reward01:.4f} "
            f"(raw={raw_reward:.4f}, erc_ran={res.get('erc_ran')}) "
            f"fatal_errors[:3]={top_fatals}"
        )
        return EvaluationResult(
            reward=reward01,
            done=True,
            content=content,
            info={
                "breakdown": breakdown,
                "fatal_errors": fatal_errors,
                "raw_reward": raw_reward,
                "reward_max": reward_dict.get("reward_max"),
                "passed": passed,
                "erc_ran": res.get("erc_ran"),
            },
        )
    except Exception as exc:  # noqa: BLE001 - FAIL CLOSED, any failure -> 0
        return EvaluationResult(
            reward=0.0,
            done=True,
            content=f"grading failed (program rejected/invalid): {type(exc).__name__}: {exc}",
            info={"raw_reward": 0.0, "passed": False, "fatal_errors": [str(exc)]},
        )
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


@env.template(id="kicad_design")
async def kicad_design(task_name: str = "usb_c_5v_led"):
    """Mint one circuit-design task.

    Setup phase (before first yield): load the TaskSpec and build the prompt.
    Evaluate phase: grade the agent's answer (a build() program string) through
    the project verifier and return its normalized 0..1 reward.
    """
    # --- setup phase ---------------------------------------------------------
    taskspec = load_taskspec(task_name)
    prompt = build_prompt(taskspec)

    # Hand the prompt to the agent; receive its final answer (raw program text).
    answer = yield prompt

    # --- evaluate phase (fail-closed) ----------------------------------------
    yield grade_program(task_name, answer)


__all__ = ["env", "kicad_design", "grade_program", "load_taskspec", "tasks_dir", "TASK_NAMES"]
