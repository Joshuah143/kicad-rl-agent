"""Runtime configuration for the circuit-agent.

Reads Fireworks AI connection details from the environment and resolves friendly
model aliases to concrete Fireworks model ids. This module deliberately depends
only on the stdlib so it is always importable (it sits at the root of many import
chains, including the headline ``train_or_rollout.py`` entrypoint).

NOTE: the model ids in :data:`MODEL_ALIASES` are *placeholders*. Adjust them to
the exact Fireworks model ids you have access to -- e.g. a "Gemma 4" model may not
exist on Fireworks yet, in which case point the ``gemma4`` alias at whatever Gemma
(or other) instruct model you intend to use as the policy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Friendly alias -> Fireworks model id. These are placeholders; edit to match the
# model ids your Fireworks account can actually serve.
MODEL_ALIASES: dict[str, str] = {
    "gemma4": "accounts/fireworks/models/gemma-3-27b-it",
    "gemma": "accounts/fireworks/models/gemma-3-27b-it",
    "critic": "accounts/fireworks/models/qwen2p5-72b-instruct",
}

# Default Fireworks OpenAI-compatible REST base url.
DEFAULT_FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"


def resolve_model(alias_or_id: str) -> str:
    """Resolve a friendly alias to a Fireworks model id.

    A value containing ``"/"`` is treated as a literal Fireworks model id and
    returned unchanged. Otherwise it is looked up in :data:`MODEL_ALIASES`,
    defaulting to the value itself when the alias is unknown.
    """
    value = (alias_or_id or "").strip()
    if "/" in value:
        return value
    return MODEL_ALIASES.get(value, value)


@dataclass
class Settings:
    """Resolved runtime settings for talking to Fireworks AI.

    Attributes
    ----------
    fireworks_api_key:
        The Fireworks API key, or ``None`` when unset (offline / mock mode).
    fireworks_base_url:
        OpenAI-compatible REST base url for Fireworks.
    policy_model:
        Resolved Fireworks model id used for sampling candidate programs.
    critic_model:
        Resolved Fireworks model id used by the optional LLM critic.
    request_timeout:
        Per-request timeout (seconds) for HTTP calls.
    """

    fireworks_api_key: Optional[str] = None
    fireworks_base_url: str = DEFAULT_FIREWORKS_BASE_URL
    policy_model: str = field(default_factory=lambda: resolve_model("gemma4"))
    critic_model: str = field(default_factory=lambda: resolve_model("critic"))
    request_timeout: float = 120.0


_DOTENV_LOADED = False


def _iter_candidate_dirs() -> list[Path]:
    """Directories to search for a ``.env``: cwd upward, then this module upward."""
    seen: list[Path] = []
    for start in (Path.cwd(), Path(__file__).resolve().parent):
        cur = start
        while True:
            if cur not in seen:
                seen.append(cur)
            if cur.parent == cur:
                break
            cur = cur.parent
    return seen


def load_dotenv(path: Optional[Path] = None, *, override: bool = False) -> bool:
    """Load ``KEY=VALUE`` pairs from a ``.env`` file into ``os.environ``.

    When ``path`` is not given, searches the current working directory and this
    module's directory upward for a ``.env``. Existing environment variables win
    unless ``override`` is True, so a shell ``export`` always takes precedence.
    Tolerant of a missing file and malformed lines; never raises. Returns True if
    a file was read.
    """
    target = path
    if target is None:
        for d in _iter_candidate_dirs():
            candidate = d / ".env"
            if candidate.is_file():
                target = candidate
                break
    if target is None or not Path(target).is_file():
        return False
    try:
        text = Path(target).read_text(encoding="utf-8")
    except OSError:
        return False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
    return True


def load_settings(model_alias: str = "gemma4", critic_alias: str = "critic") -> Settings:
    """Build :class:`Settings` from the environment.

    Reads ``FIREWORKS_API_KEY`` and ``FIREWORKS_BASE_URL`` from the environment
    and resolves the given policy/critic aliases to concrete model ids. Never
    raises on a missing key -- ``fireworks_api_key`` is simply ``None`` and
    callers that actually need it (Fireworks backend / critic) raise a clear,
    actionable error at use time.
    """
    global _DOTENV_LOADED
    if not _DOTENV_LOADED:
        load_dotenv()
        _DOTENV_LOADED = True
    api_key = os.environ.get("FIREWORKS_API_KEY") or None
    base_url = os.environ.get("FIREWORKS_BASE_URL") or DEFAULT_FIREWORKS_BASE_URL
    return Settings(
        fireworks_api_key=api_key,
        fireworks_base_url=base_url,
        policy_model=resolve_model(model_alias),
        critic_model=resolve_model(critic_alias),
    )


def have_fireworks(settings: Settings) -> bool:
    """Return ``True`` when a Fireworks API key is configured."""
    return bool(settings.fireworks_api_key)


__all__ = [
    "MODEL_ALIASES",
    "load_dotenv",
    "DEFAULT_FIREWORKS_BASE_URL",
    "Settings",
    "resolve_model",
    "load_settings",
    "have_fireworks",
]
