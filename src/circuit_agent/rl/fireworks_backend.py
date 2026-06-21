"""Fireworks-served policy backend for the RL loop.

This is the working "learning" backend. Sampling goes to a Fireworks AI model
over the OpenAI-compatible chat-completions REST endpoint (via
:class:`circuit_agent.infra.fireworks_client.FireworksClient`, which imports
``requests`` lazily). Graded rollouts are exported to an RFT-style JSONL dataset
suitable for Fireworks Reinforcement Fine-Tuning; launching the actual training
job is a documented stub (:func:`FireworksBackend.launch_rft_job`).

No Anthropic/OpenAI-the-company code is involved -- the only network destination
is the Fireworks REST endpoint configured in :class:`circuit_agent.config.Settings`.
"""

from __future__ import annotations

import json
import os
import pathlib
from typing import Optional

from circuit_agent.config import Settings, resolve_model
from circuit_agent.rl.hud_backend import RLBackend

_DEFAULT_DATASET_PATH = os.path.join("out", "rft_dataset.jsonl")


class FireworksBackend(RLBackend):
    """Sample candidate DSL programs from a Fireworks-served model.

    Parameters
    ----------
    settings:
        Runtime configuration carrying the Fireworks API key, base URL and the
        resolved policy model id.
    model:
        Optional explicit model id/alias override. When ``None`` the backend uses
        ``settings.policy_model``.
    temperature, max_tokens:
        Default sampling parameters forwarded to the chat endpoint.
    dataset_path:
        Where :meth:`update` appends RFT training rows (JSONL). Defaults to
        ``out/rft_dataset.jsonl``.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        dataset_path: Optional[str] = None,
    ) -> None:
        self.settings = settings
        self.model = resolve_model(model) if model else settings.policy_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.dataset_path = dataset_path or _DEFAULT_DATASET_PATH
        self._client = None  # built lazily on first sample()

    # ------------------------------------------------------------------ #
    # Client management
    # ------------------------------------------------------------------ #
    def _get_client(self):
        """Build (and cache) the Fireworks client; raise a clear error if no key."""
        if self._client is None:
            from circuit_agent.infra.fireworks_client import FireworksClient

            self._client = FireworksClient.from_settings(self.settings)
        return self._client

    # ------------------------------------------------------------------ #
    # Sampling
    # ------------------------------------------------------------------ #
    def sample(self, prompt: str, n: int) -> list[str]:
        """Sample ``n`` completions for a single combined prompt.

        The combined prompt is sent as one user message. Prefer
        :meth:`sample_chat` when a system/user split is available.
        """
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
        """Sample ``n`` completions using an explicit system + user message pair."""
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

    # ------------------------------------------------------------------ #
    # Dataset export (RFT)
    # ------------------------------------------------------------------ #
    def update(self, samples: list[dict]) -> None:
        """Append graded rollouts to the RFT-style JSONL dataset.

        Each input record is expected to carry at least ``prompt``, ``completion``
        and ``reward`` keys (extra keys such as ``system`` or ``task`` are used
        when present). One JSON object is written per line in the shape Fireworks
        Reinforcement Fine-Tuning consumes::

            {"messages": [{"role": ...}, ...], "completion": "<code>", "reward": <float>}

        The directory is created if needed. No training job is launched here --
        see :meth:`launch_rft_job`.
        """
        if not samples:
            return
        path = pathlib.Path(self.dataset_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for rec in samples:
                fh.write(json.dumps(self._to_rft_row(rec), ensure_ascii=False))
                fh.write("\n")

    def _to_rft_row(self, rec: dict) -> dict:
        """Translate a rollout record into an RFT dataset row."""
        messages = rec.get("messages")
        if not messages:
            messages = []
            system = rec.get("system")
            if system:
                messages.append({"role": "system", "content": system})
            prompt = rec.get("prompt", "")
            messages.append({"role": "user", "content": prompt})
        completion = rec.get("completion", rec.get("code", ""))
        reward = rec.get("reward", 0.0)
        try:
            reward = float(reward)
        except (TypeError, ValueError):
            reward = 0.0
        return {"messages": messages, "completion": completion, "reward": reward}

    # ------------------------------------------------------------------ #
    # RFT job launch (documented stub)
    # ------------------------------------------------------------------ #
    def launch_rft_job(
        self,
        *,
        base_model: Optional[str] = None,
        dataset_path: Optional[str] = None,
        output_model: Optional[str] = None,
    ) -> str:
        """Describe how to launch a Fireworks Reinforcement Fine-Tuning job.

        This is a DOCUMENTED STUB. The dataset export performed by :meth:`update`
        is functional and produces a file Fireworks RFT can consume; actually
        kicking off the job is left as a manual / future step.

        Intended workflow (see Fireworks docs for the current ``firectl`` syntax)::

            firectl create rft \\
                --base-model <base_model> \\
                --dataset <dataset_path> \\
                --reward <this repo's deterministic reward> \\
                --output-model <output_model>

        Returns the would-be command string and raises ``NotImplementedError`` if
        invoked expecting an actual launch.
        """
        base = base_model or self.model
        ds = dataset_path or self.dataset_path
        out = output_model or "accounts/<your-account>/models/<new-model-name>"
        command = (
            "firectl create rft "
            f"--base-model {base} "
            f"--dataset {ds} "
            "--reward circuit_agent.validators.reward.compute_reward "
            f"--output-model {out}"
        )
        raise NotImplementedError(
            "Launching the Fireworks RFT job is not automated yet. "
            "The dataset has been exported and is ready; run the equivalent of:\n  "
            + command
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def extract_code(text: str) -> str:
        """Pull Python source from a model completion.

        Prefers the contents of the first fenced ``python`` (or bare ```` ``` ````)
        block; otherwise returns the stripped text unchanged.
        """
        if not text:
            return ""
        marker = "```"
        if marker not in text:
            return text.strip()

        idx = text.find(marker)
        rest = text[idx + len(marker):]
        # Drop an optional language tag (e.g. "python") on the opening fence line.
        newline = rest.find("\n")
        if newline != -1:
            first_line = rest[:newline].strip().lower()
            if first_line in ("python", "py", "python3", ""):
                rest = rest[newline + 1:]
            elif first_line.isalpha():
                # Unknown but plausible language tag -> still strip the tag line.
                rest = rest[newline + 1:]
        end = rest.find(marker)
        if end != -1:
            rest = rest[:end]
        return rest.strip()


__all__ = ["FireworksBackend"]
