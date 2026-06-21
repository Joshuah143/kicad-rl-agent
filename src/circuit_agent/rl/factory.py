"""Factory for constructing RL policy backends by name.

Centralises backend construction so scripts and the training loop can select a
backend with a single string (``"mock"``, ``"fireworks"`` or ``"hud"``) without
importing the concrete classes directly. The Fireworks path lazily builds a
:class:`~circuit_agent.config.Settings` instance when one is not supplied.
"""

from __future__ import annotations

from typing import Optional

from circuit_agent.config import Settings
from circuit_agent.rl.fireworks_backend import FireworksBackend
from circuit_agent.rl.hud_backend import HUDBackend, MockBackend, RLBackend

_CHOICES = ("mock", "fireworks", "hud")


def make_backend(
    name: str,
    *,
    settings: Optional[Settings] = None,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    **kw,
) -> RLBackend:
    """Build an :class:`RLBackend` by name.

    Parameters
    ----------
    name:
        One of ``"mock"``, ``"fireworks"`` or ``"hud"``.
    settings:
        Runtime settings; required (or auto-loaded) only for the Fireworks
        backend. When ``name == "fireworks"`` and ``settings`` is ``None``,
        :func:`circuit_agent.config.load_settings` is called.
    model, temperature, max_tokens:
        Forwarded to the Fireworks backend.
    **kw:
        Extra keyword arguments. For ``"hud"`` they become the backend config;
        ``"mock"`` accepts an optional ``examples`` dict.

    Raises
    ------
    ValueError
        If ``name`` is not a recognised backend.
    """
    key = (name or "").strip().lower()

    if key == "mock":
        examples = kw.get("examples")
        return MockBackend(examples=examples)

    if key == "fireworks":
        if settings is None:
            from circuit_agent.config import load_settings

            settings = load_settings(model or "gemma4")
        return FireworksBackend(
            settings,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            dataset_path=kw.get("dataset_path"),
        )

    if key == "hud":
        return HUDBackend(**kw)

    raise ValueError(
        f"Unknown RL backend {name!r}. Choose one of: {', '.join(_CHOICES)}."
    )


__all__ = ["make_backend"]
