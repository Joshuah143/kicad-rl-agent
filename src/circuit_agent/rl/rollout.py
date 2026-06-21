"""Rollout: sample candidate DSL programs, compile + score each, pick the best.

A *rollout* is one round of: build a prompt from a :class:`~circuit_agent.task.TaskSpec`,
ask an :class:`~circuit_agent.rl.hud_backend.RLBackend` for ``n`` candidate programs,
turn each program string into a :class:`~circuit_agent.dsl.schema.CircuitModel` via the
sandbox, score it end-to-end with :func:`circuit_agent.infra.verifier.verify_design`, and
record everything to a JSONL training log that the backend can later consume for
reinforcement fine-tuning.

The rollout is deliberately *robust*: a single malformed candidate (sandbox error,
verifier hiccup) is recorded with ``valid=False`` / ``reward=0.0`` and never aborts the
batch. All heavy/optional work (KiCad, Modal, the LLM critic) is delegated to
``verify_design`` and degrades gracefully there.

Imports stay light (stdlib + the in-package contract surface) so the mock + local path
runs with only ``pydantic``/``pyyaml`` installed.
"""

from __future__ import annotations

import json
import shutil
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from circuit_agent.dsl.sandbox import SandboxError, run_program
from circuit_agent.infra.verifier import verify_design
from circuit_agent.rl import prompts
from circuit_agent.rl.hud_backend import RLBackend
from circuit_agent.task import TaskSpec, load_task

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids heavy/eager imports
    from circuit_agent.config import Settings
    from circuit_agent.validators.llm_critic import Critic


@dataclass
class CandidateResult:
    """The fully-scored outcome of a single sampled program."""

    index: int
    raw_completion: str
    code: str
    valid: bool
    error: Optional[str]
    reward: float
    reward_breakdown: dict
    artifacts: dict
    circuit: Optional[dict]


@dataclass
class RolloutResult:
    """The aggregate result of one rollout over ``n`` candidates."""

    task: str
    out_dir: str
    candidates: list[CandidateResult] = field(default_factory=list)
    best_index: Optional[int] = None
    best: Optional[CandidateResult] = None


def _extract_code(backend: RLBackend, raw: str) -> str:
    """Best-effort extraction of a runnable program from a raw completion.

    Fireworks-style backends expose a static ``extract_code`` helper that strips
    Markdown fences; if the backend does not provide one, fall back to a local
    fenced-block strip so the mock/local path stays dependency-free.
    """

    extractor = getattr(type(backend), "extract_code", None)
    if callable(extractor):
        try:
            return extractor(raw)
        except Exception:  # pragma: no cover - defensive; never let extraction abort
            pass
    return _strip_fenced_code(raw)


def _strip_fenced_code(text: str) -> str:
    """Pull Python from a fenced ```python block if present, else strip the text."""

    if "```" not in text:
        return text.strip()
    parts = text.split("```")
    # Markdown fence layout: prose ``` lang\ncode``` prose -> odd indices are blocks.
    for chunk in parts[1::2]:
        body = chunk
        # Drop a leading language tag line (e.g. "python\n...").
        first_nl = body.find("\n")
        if first_nl != -1:
            head = body[:first_nl].strip().lower()
            if head in {"python", "py", "python3", ""}:
                body = body[first_nl + 1 :]
        body = body.strip()
        if body:
            return body
    return text.strip()


def run_rollout(
    task_path: str,
    backend: RLBackend,
    n_candidates: int,
    out_dir: str,
    *,
    settings: "Optional[Settings]" = None,
    use_kicad: Optional[bool] = None,
    run_critic: bool = False,
    critic: "Optional[Critic]" = None,
    use_modal: bool = False,
    log_jsonl: bool = True,
) -> RolloutResult:
    """Sample, compile, score and rank ``n_candidates`` programs for one task.

    Parameters
    ----------
    task_path:
        Path to a task YAML loadable by :func:`circuit_agent.task.load_task`.
    backend:
        The policy backend used to :meth:`~RLBackend.sample` programs and receive the
        :meth:`~RLBackend.update` training records.
    n_candidates:
        Number of programs to sample for this rollout.
    out_dir:
        Directory to write per-candidate artifacts, the ``best/`` copy and the JSONL log.
    settings:
        Optional :class:`Settings`; only used to thread Fireworks config to the critic /
        verifier. The local + mock path works with ``settings=None``.
    use_kicad:
        Tri-state KiCad toggle forwarded to the verifier (``None`` -> auto-detect).
    run_critic / critic:
        If ``critic`` is supplied it is used directly. Otherwise, when ``run_critic`` is
        true a conservative stub critic is constructed lazily.
    use_modal:
        Forward to the verifier to run KiCad + validators inside the Modal sandbox.
    log_jsonl:
        Write ``training_log.jsonl`` (one record per candidate) and call
        ``backend.update`` with those records.

    Returns
    -------
    RolloutResult
        Per-candidate results plus the selected best (highest reward among valid
        candidates; ties broken by lowest index).
    """

    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    task: TaskSpec = load_task(task_path)

    # Resolve a critic exactly once for the whole batch.
    active_critic = _resolve_critic(critic, run_critic, settings)

    prompt = prompts.build_prompt(task)

    # Sampling itself can fail (network for Fireworks); surface a clear error rather
    # than half-running the batch.
    completions = list(backend.sample(prompt, n_candidates))

    candidates: list[CandidateResult] = []
    records: list[dict] = []

    for i, raw in enumerate(completions):
        cand_dir = out_root / f"cand_{i:03d}"
        cand_dir.mkdir(parents=True, exist_ok=True)

        code = _extract_code(backend, raw)
        (cand_dir / "program.py").write_text(code, encoding="utf-8")

        candidate = _score_candidate(
            index=i,
            raw=raw,
            code=code,
            cand_dir=cand_dir,
            task=task,
            critic=active_critic,
            use_kicad=use_kicad,
            use_modal=use_modal,
        )
        candidates.append(candidate)

        records.append(
            {
                "task": task.name,
                "prompt": prompt,
                "completion": code,
                "valid": candidate.valid,
                "reward": candidate.reward,
                "reward_breakdown": candidate.reward_breakdown,
                "artifacts": candidate.artifacts,
            }
        )

    best_index, best = _select_best(candidates)
    if best is not None:
        _copy_best(out_root, best)

    if log_jsonl:
        _write_training_log(out_root / "training_log.jsonl", records)

    # Hand the batch to the backend so it can grow an RFT dataset / log counts.
    # A backend failure here must not destroy the already-computed results.
    try:
        backend.update(records)
    except NotImplementedError:
        # HUD backend is a documented stub; treat update as a no-op for rollouts.
        pass
    except Exception:  # pragma: no cover - defensive
        traceback.print_exc()

    return RolloutResult(
        task=task.name,
        out_dir=str(out_root),
        candidates=candidates,
        best_index=best_index,
        best=best,
    )


def _resolve_critic(
    critic: "Optional[Critic]",
    run_critic: bool,
    settings: "Optional[Settings]",
) -> "Optional[Critic]":
    """Return an explicit critic, build a stub on request, or ``None``."""

    if critic is not None:
        return critic
    if not run_critic:
        return None
    # Lazy import keeps the critic module out of the light/offline import path.
    from circuit_agent.validators.llm_critic import make_critic

    return make_critic("stub", settings=settings)


def _score_candidate(
    *,
    index: int,
    raw: str,
    code: str,
    cand_dir: Path,
    task: TaskSpec,
    critic: "Optional[Critic]",
    use_kicad: Optional[bool],
    use_modal: bool,
) -> CandidateResult:
    """Compile + verify a single candidate; never raise on a well-formed program."""

    # 1) Sandbox the program string into a validated CircuitModel.
    try:
        model = run_program(code)
    except SandboxError as exc:
        return CandidateResult(
            index=index,
            raw_completion=raw,
            code=code,
            valid=False,
            error=f"sandbox: {exc}",
            reward=0.0,
            reward_breakdown={},
            artifacts={},
            circuit=None,
        )
    except Exception as exc:  # pragma: no cover - defensive: any unexpected build error
        return CandidateResult(
            index=index,
            raw_completion=raw,
            code=code,
            valid=False,
            error=f"build: {exc}",
            reward=0.0,
            reward_breakdown={},
            artifacts={},
            circuit=None,
        )

    circuit_dict = model.model_dump()
    (cand_dir / "circuit.json").write_text(
        json.dumps(circuit_dict, indent=2), encoding="utf-8"
    )

    # 2) Score end-to-end. verify_design is contracted not to raise on a well-formed
    #    model, but we still guard so one verifier failure cannot abort the batch.
    try:
        verdict = verify_design(
            model,
            task,
            str(cand_dir),
            use_kicad=use_kicad,
            export=True,
            critic=critic,
            use_modal=use_modal,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return CandidateResult(
            index=index,
            raw_completion=raw,
            code=code,
            valid=False,
            error=f"verify: {exc}",
            reward=0.0,
            reward_breakdown={},
            artifacts={},
            circuit=circuit_dict,
        )

    reward_dict = verdict.get("reward", {}) if isinstance(verdict, dict) else {}
    artifacts = verdict.get("artifacts", {}) if isinstance(verdict, dict) else {}

    # Prefer the on-disk reward.json (the authoritative artifact) when present.
    reward_path = artifacts.get("reward") if isinstance(artifacts, dict) else None
    if reward_path:
        loaded = _read_json(reward_path)
        if isinstance(loaded, dict):
            reward_dict = loaded

    reward_value = float(reward_dict.get("reward", 0.0)) if reward_dict else 0.0

    return CandidateResult(
        index=index,
        raw_completion=raw,
        code=code,
        valid=True,
        error=None,
        reward=reward_value,
        reward_breakdown=reward_dict,
        artifacts=artifacts if isinstance(artifacts, dict) else {},
        circuit=circuit_dict,
    )


def _read_json(path: str) -> Optional[dict]:
    """Read a JSON file, returning ``None`` on any error (missing/corrupt)."""

    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _select_best(
    candidates: list[CandidateResult],
) -> tuple[Optional[int], Optional[CandidateResult]]:
    """Pick the highest-reward *valid* candidate; ties resolve to the lowest index."""

    best: Optional[CandidateResult] = None
    for cand in candidates:
        if not cand.valid:
            continue
        if best is None or cand.reward > best.reward:
            best = cand
    if best is None:
        return None, None
    return best.index, best


def _copy_best(out_root: Path, best: CandidateResult) -> None:
    """Copy the winning candidate's directory contents into ``out_dir/best/``."""

    src = out_root / f"cand_{best.index:03d}"
    dst = out_root / "best"
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    try:
        if src.is_dir():
            shutil.copytree(src, dst)
        else:  # pragma: no cover - src always created above
            dst.mkdir(parents=True, exist_ok=True)
    except Exception:  # pragma: no cover - defensive: never abort on a copy hiccup
        dst.mkdir(parents=True, exist_ok=True)


def _write_training_log(path: Path, records: list[dict]) -> None:
    """Write one JSON object per line (JSONL) for downstream RFT consumption."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec))
            fh.write("\n")
