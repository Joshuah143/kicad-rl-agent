"""Train loop: repeat rollouts and let the backend accumulate training signal.

This is the outer RL loop. Each iteration runs one :func:`circuit_agent.rl.rollout.run_rollout`
into ``out_dir/iter_{k:03d}``, which samples candidate DSL programs, scores them with the
deterministic reward, and (inside the rollout) calls ``backend.update`` with the per-candidate
records.

Where do real weight updates happen?
------------------------------------
There is no in-process gradient step here. For the working RL path the policy is a
Fireworks-hosted Gemma model and learning happens via **Fireworks Reinforcement
Fine-Tuning (RFT)**: ``FireworksBackend.update`` appends the scored
``{messages, completion, reward}`` records to an RFT-style JSONL dataset. A separate
job (``firectl create rft`` against that dataset + this reward) performs the actual
weight update. Launching that job is a documented TODO on the Fireworks backend; this
loop produces the dataset and the per-iteration metrics it needs.

The :class:`~circuit_agent.rl.hud_backend.MockBackend` makes the whole loop runnable
offline with no weight updates at all (it just logs counts), which is what powers the
MVP command.

Imports stay light so the loop runs with only ``pydantic``/``pyyaml`` installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from circuit_agent.rl.hud_backend import RLBackend
from circuit_agent.rl.rollout import RolloutResult, run_rollout

if TYPE_CHECKING:  # pragma: no cover - typing only
    from circuit_agent.config import Settings
    from circuit_agent.validators.llm_critic import Critic


def train(
    task_path: str,
    backend: RLBackend,
    n_iters: int,
    n_candidates: int,
    out_dir: str,
    *,
    settings: "Optional[Settings]" = None,
    use_kicad: Optional[bool] = None,
    run_critic: bool = False,
    critic: "Optional[Critic]" = None,
    use_modal: bool = False,
    log_jsonl: bool = True,
) -> list[RolloutResult]:
    """Run ``n_iters`` rollouts, returning the per-iteration :class:`RolloutResult`.

    Each iteration writes to ``out_dir/iter_{k:03d}`` and prints a one-line best-reward
    summary. ``backend.update`` is invoked *inside* each rollout with that iteration's
    records, so by the end of training the backend has accumulated the full dataset
    (e.g. the Fireworks RFT JSONL).

    Parameters mirror :func:`run_rollout`; ``n_iters`` is the number of rollout rounds.
    """

    Path(out_dir).mkdir(parents=True, exist_ok=True)

    results: list[RolloutResult] = []

    for k in range(n_iters):
        iter_dir = str(Path(out_dir) / f"iter_{k:03d}")
        result = run_rollout(
            task_path,
            backend,
            n_candidates,
            iter_dir,
            settings=settings,
            use_kicad=use_kicad,
            run_critic=run_critic,
            critic=critic,
            use_modal=use_modal,
            log_jsonl=log_jsonl,
        )
        results.append(result)

        best_reward = result.best.reward if result.best is not None else 0.0
        n_valid = sum(1 for c in result.candidates if c.valid)
        print(
            f"[train] iter {k + 1}/{n_iters} "
            f"task={result.task} "
            f"valid={n_valid}/{len(result.candidates)} "
            f"best_reward={best_reward:.4f} "
            f"-> {iter_dir}"
        )

    # NOTE: real weight updates are launched out-of-band via Fireworks RFT using the
    # dataset that FireworksBackend.update has accumulated across these iterations.
    return results
