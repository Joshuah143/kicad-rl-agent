"""RL backend interface plus an offline ``MockBackend`` and a documented ``HUDBackend`` stub.

An :class:`RLBackend` is the abstraction the rollout / training loop uses to obtain
candidate DSL programs (``sample``) and to feed graded rollouts back for learning
(``update``). Three concrete implementations exist in this package:

* :class:`MockBackend` (here) -- fully offline; draws candidates from the
  hand-written reference programs in :mod:`circuit_agent.dsl.examples`. This is
  what makes the MVP rollout command run with only ``pydantic``/``pyyaml`` present.
* :class:`HUDBackend` (here) -- a documented STUB describing how a HUD-style
  (reset/step) RL environment would plug in. It intentionally raises a clear,
  actionable error rather than half-working, and points callers at the
  Fireworks path as the real, working learning backend.
* :class:`circuit_agent.rl.fireworks_backend.FireworksBackend` -- talks to a
  Fireworks-served policy model over the OpenAI-compatible REST endpoint and
  exports an RFT-style dataset for reinforcement fine-tuning.

Keeping HUD internals behind this interface means the rest of the system never
needs to import any HUD package.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class RLBackend(ABC):
    """Abstract policy backend: produce candidate programs and consume graded rollouts."""

    @abstractmethod
    def sample(self, prompt: str, n: int) -> list[str]:
        """Return ``n`` candidate completions (each a DSL ``build()`` program string)."""
        raise NotImplementedError

    def sample_chat(self, system: str, user: str, n: int) -> list[str]:
        """Sample with an explicit system/user split.

        Default implementation flattens the two messages into a single prompt and
        delegates to :meth:`sample`. Backends that natively support chat roles
        (e.g. :class:`FireworksBackend`) should override this.
        """
        combined = f"{system}\n\n{user}" if system else user
        return self.sample(combined, n)

    @abstractmethod
    def update(self, samples: list[dict]) -> None:
        """Consume graded rollout records (``{"prompt","completion","reward",...}``).

        For online backends this would drive a weight update; for dataset-export
        backends it appends RFT training rows; for the mock it just logs.
        """
        raise NotImplementedError

    def close(self) -> None:
        """Release any resources held by the backend. Default: no-op."""
        return None


class MockBackend(RLBackend):
    """Offline backend that cycles through the reference example programs.

    It ignores the prompt content entirely and simply returns ``n`` programs
    drawn (with wraparound) from :data:`circuit_agent.dsl.examples.EXAMPLE_PROGRAMS`,
    applying a tiny deterministic textual tweak per index so that candidates are
    distinct (the verifier/reward must still treat them as separate rollouts).
    This makes the end-to-end rollout command run with no network and no API key.
    """

    def __init__(self, examples: Optional[dict[str, str]] = None) -> None:
        if examples is None:
            # Imported lazily so importing this module never forces the DSL package
            # to be importable before it exists in a partially-built tree.
            from circuit_agent.dsl.examples import EXAMPLE_PROGRAMS

            examples = dict(EXAMPLE_PROGRAMS)
        # Stable ordering => deterministic cycling.
        self._examples: list[tuple[str, str]] = sorted(examples.items())
        if not self._examples:
            raise ValueError("MockBackend requires at least one example program.")
        self._log: list[dict] = []

    def sample(self, prompt: str, n: int) -> list[str]:
        """Return ``n`` example programs, cycling and lightly varying each by index."""
        if n <= 0:
            return []
        out: list[str] = []
        count = len(self._examples)
        for i in range(n):
            name, program = self._examples[i % count]
            # Deterministic per-index variety so identical examples still differ as
            # text (distinct completions); the trailing comment does not change the
            # compiled circuit.
            varied = f"{program.rstrip()}\n\n# mock-candidate index={i} source={name}\n"
            out.append(varied)
        return out

    def update(self, samples: list[dict]) -> None:
        """Record graded rollouts in an in-memory log (no learning)."""
        self._log.extend(samples)
        # Lightweight visibility for the offline MVP; intentionally cheap.
        print(f"[MockBackend] update: received {len(samples)} sample(s) "
              f"(total logged: {len(self._log)})")

    @property
    def log(self) -> list[dict]:
        """All rollout records seen via :meth:`update` (useful for tests)."""
        return self._log


_HUD_MESSAGE = (
    "HUDBackend is a stub: the HUD reset/step RL environment integration is not "
    "implemented in this repository. The intended design wraps a HUD-compatible "
    "environment whose `env.reset()` yields the task prompt and whose `env.step()` "
    "submits a candidate DSL program and returns the deterministic reward computed "
    "by circuit_agent.validators.reward.compute_reward. Until that environment "
    "exists, use a working backend instead:\n"
    "  --backend mock       (fully offline; draws from the reference examples)\n"
    "  --backend fireworks  (samples a Fireworks-served policy model; requires "
    "FIREWORKS_API_KEY and the optional 'requests' dependency)."
)


class HUDBackend(RLBackend):
    """Documented stub for a HUD / HUD-compatible RL environment backend.

    The constructor accepts and stores arbitrary configuration so the rest of the
    system can construct it uniformly, but :meth:`sample` and :meth:`update` raise
    :class:`NotImplementedError` with an actionable message. This keeps the HUD
    interface seam in place without pulling any HUD package into the import graph.
    """

    def __init__(self, **config: Any) -> None:
        self.config: dict[str, Any] = dict(config)

    def sample(self, prompt: str, n: int) -> list[str]:  # noqa: D401 - stub
        raise NotImplementedError(_HUD_MESSAGE)

    def update(self, samples: list[dict]) -> None:  # noqa: D401 - stub
        raise NotImplementedError(_HUD_MESSAGE)


__all__ = ["RLBackend", "MockBackend", "HUDBackend"]
