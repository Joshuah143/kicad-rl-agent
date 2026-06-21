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

# Friendly alias -> Fireworks model id. Point these at model ids your Fireworks
# account can actually serve (check the serverless catalog at app.fireworks.ai).
MODEL_ALIASES: dict[str, str] = {
    # Current working serverless defaults (2026 catalog):
    "policy": "accounts/fireworks/models/kimi-k2p7-code",
    "kimi": "accounts/fireworks/models/kimi-k2p7-code",
    "qwen": "accounts/fireworks/models/qwen3p7-plus",
    "critic": "accounts/fireworks/models/qwen3p7-plus",
    # Legacy aliases kept working (Gemma is no longer on Fireworks serverless):
    "gemma4": "accounts/fireworks/models/kimi-k2p7-code",
    "gemma": "accounts/fireworks/models/kimi-k2p7-code",
}

# Default Fireworks OpenAI-compatible REST base url.
DEFAULT_FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"

# HUD model gateway (OpenAI-compatible). NOTE: the working endpoint is the beta
# host with a /v1 suffix -- the public docs list ``inference.hud.ai`` which
# currently returns 401 for gateway keys. Override with ``HUD_BASE_URL`` if HUD
# promotes the gateway out of beta.
DEFAULT_HUD_BASE_URL = "https://inference.beta.hud.ai/v1"

# Friendly alias -> HUD gateway model NAME (not UUID). HUD model names have no
# "/", so they pass through resolve_model unchanged; these are conveniences.
HUD_MODEL_ALIASES: dict[str, str] = {
    "policy": "kicad-rl-8b",      # the custom trained circuit policy
    "kicad": "kicad-rl-8b",
    "chat": "claude-sonnet-4-5",  # frontier model for the design conversation
}

# Default chat model used by the Design conversation (clarifying questions).
DEFAULT_HUD_CHAT_MODEL = "claude-sonnet-4-5"
# Default policy model used to generate circuit programs.
DEFAULT_HUD_POLICY_MODEL = "kicad-rl-8b"


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
    # HUD model gateway (OpenAI-compatible). ``hud_api_key`` is ``None`` when unset.
    hud_api_key: Optional[str] = None
    hud_base_url: str = DEFAULT_HUD_BASE_URL


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
        hud_api_key=os.environ.get("HUD_API_KEY") or None,
        hud_base_url=os.environ.get("HUD_BASE_URL") or DEFAULT_HUD_BASE_URL,
    )


def resolve_hud_model(alias_or_name: str) -> str:
    """Resolve a friendly alias to a HUD gateway model NAME.

    HUD model names contain no ``/`` and are used verbatim by the gateway, so an
    unknown value is returned unchanged. Known aliases (``policy``/``kicad`` ->
    ``kicad-rl-8b``, ``chat`` -> ``claude-sonnet-4-5``) are conveniences.
    """
    value = (alias_or_name or "").strip()
    return HUD_MODEL_ALIASES.get(value, value)


def have_fireworks(settings: Settings) -> bool:
    """Return ``True`` when a Fireworks API key is configured."""
    return bool(settings.fireworks_api_key)


def have_hud(settings: Settings) -> bool:
    """Return ``True`` when a HUD gateway API key is configured."""
    return bool(settings.hud_api_key)


__all__ = [
    "MODEL_ALIASES",
    "HUD_MODEL_ALIASES",
    "load_dotenv",
    "DEFAULT_FIREWORKS_BASE_URL",
    "DEFAULT_HUD_BASE_URL",
    "DEFAULT_HUD_CHAT_MODEL",
    "DEFAULT_HUD_POLICY_MODEL",
    "Settings",
    "resolve_model",
    "resolve_hud_model",
    "load_settings",
    "have_fireworks",
    "have_hud",
]
