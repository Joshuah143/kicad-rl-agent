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

import json
import os
import pathlib
import re
from abc import ABC, abstractmethod
from typing import Any, Optional

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_think(text: str) -> str:
    """Remove ``<think>...</think>`` reasoning blocks emitted by Qwen-style models.

    ``kicad-rl-8b`` (Qwen3-8B) wraps its chain-of-thought in ``<think>`` tags
    before the real answer; an unterminated block (truncated output) is dropped
    from the first opening tag. Returns the visible answer text, stripped.
    """
    if not text:
        return ""
    cleaned = _THINK_RE.sub("", text)
    # Drop a dangling, unterminated <think> with no closing tag.
    lower = cleaned.lower()
    if "<think>" in lower and "</think>" not in lower:
        cleaned = cleaned[: lower.index("<think>")]
    return cleaned.strip()


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


_DEFAULT_HUD_DATASET_PATH = os.path.join("out", "hud_dataset.jsonl")


class HUDBackend(RLBackend):
    """Policy backend that samples a custom model from the HUD model gateway.

    The HUD gateway is OpenAI-compatible, so this reuses the same chat client as
    the Fireworks backend, pointed at the HUD base URL with the HUD API key.
    Completions from Qwen-style trainables (e.g. ``kicad-rl-8b``) may include
    ``<think>`` reasoning blocks, which are stripped before code extraction.

    Parameters
    ----------
    settings:
        Runtime settings carrying ``hud_api_key`` / ``hud_base_url``. When
        ``None`` it is lazily loaded from the environment.
    model:
        HUD gateway model NAME (not UUID). Defaults to ``kicad-rl-8b``.
    temperature, max_tokens:
        Sampling parameters forwarded to the gateway.
    dataset_path:
        Where :meth:`update` appends graded rollout rows (JSONL).
    """

    def __init__(
        self,
        settings: Optional[Any] = None,
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        dataset_path: Optional[str] = None,
        **config: Any,
    ) -> None:
        if settings is None:
            from circuit_agent.config import load_settings

            settings = load_settings()
        from circuit_agent.config import DEFAULT_HUD_POLICY_MODEL, resolve_hud_model

        self.settings = settings
        self.model = resolve_hud_model(model) if model else DEFAULT_HUD_POLICY_MODEL
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.dataset_path = dataset_path or _DEFAULT_HUD_DATASET_PATH
        self.config: dict[str, Any] = dict(config)
        self._client = None

    def _get_client(self):
        if self._client is None:
            from circuit_agent.infra.fireworks_client import FireworksClient

            self._client = FireworksClient.from_hud(self.settings)
        return self._client

    def sample(self, prompt: str, n: int) -> list[str]:
        """Sample ``n`` candidate programs for one combined prompt."""
        if n <= 0:
            return []
        client = self._get_client()
        completions = client.chat(
            self.model,
            [{"role": "user", "content": prompt}],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            n=n,
        )
        return [self.extract_code(c) for c in completions]

    def sample_chat(self, system: str, user: str, n: int) -> list[str]:
        """Sample ``n`` completions from an explicit system + user message pair."""
        if n <= 0:
            return []
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        client = self._get_client()
        completions = client.chat(
            self.model,
            messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            n=n,
        )
        return [self.extract_code(c) for c in completions]

    def update(self, samples: list[dict]) -> None:
        """Append graded rollouts to a JSONL dataset (no online weight update)."""
        if not samples:
            return
        path = pathlib.Path(self.dataset_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for rec in samples:
                row = {
                    "prompt": rec.get("prompt", ""),
                    "completion": rec.get("completion", rec.get("code", "")),
                    "reward": float(rec.get("reward", 0.0) or 0.0),
                }
                fh.write(json.dumps(row, ensure_ascii=False))
                fh.write("\n")

    @staticmethod
    def extract_code(text: str) -> str:
        """Strip ``<think>`` blocks then pull Python from a fenced block."""
        from circuit_agent.rl.fireworks_backend import FireworksBackend

        return FireworksBackend.extract_code(strip_think(text))


__all__ = ["RLBackend", "MockBackend", "HUDBackend", "strip_think"]
