"""RL layer: policy backends, the rollout, and the outer train loop.

Public surface (per the project contract):

* Backends -- :class:`RLBackend` (ABC), :class:`MockBackend` (offline, deterministic),
  :class:`HUDBackend` (documented stub), :class:`FireworksBackend` (the working
  Fireworks-hosted policy path).
* Factory -- :func:`make_backend`.
* Rollout -- :func:`run_rollout`, :class:`RolloutResult` (and :class:`CandidateResult`).
* Training -- :func:`train`.

Importing this package only pulls in stdlib + pydantic. Re-exports are resolved
**lazily** (PEP 562 ``__getattr__``) so that simply importing ``circuit_agent.rl``
-- or a lightweight submodule such as :mod:`circuit_agent.rl.hud_backend` or
:mod:`circuit_agent.rl.factory` -- does not eagerly drag in the rollout / train
loop, which depend on the heavier ``dsl`` / ``infra`` layers. This keeps the
"HUD backend is a stub" actionable message reachable even when those optional
modules or dependencies are absent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# name -> submodule that defines it. Resolved on first attribute access.
_LAZY_EXPORTS: dict[str, str] = {
    "RLBackend": "circuit_agent.rl.hud_backend",
    "MockBackend": "circuit_agent.rl.hud_backend",
    "HUDBackend": "circuit_agent.rl.hud_backend",
    "FireworksBackend": "circuit_agent.rl.fireworks_backend",
    "make_backend": "circuit_agent.rl.factory",
    "run_rollout": "circuit_agent.rl.rollout",
    "RolloutResult": "circuit_agent.rl.rollout",
    "CandidateResult": "circuit_agent.rl.rollout",
    "train": "circuit_agent.rl.train_loop",
}

__all__ = list(_LAZY_EXPORTS)

if TYPE_CHECKING:  # pragma: no cover - import-time only for type checkers
    from circuit_agent.rl.factory import make_backend
    from circuit_agent.rl.fireworks_backend import FireworksBackend
    from circuit_agent.rl.hud_backend import HUDBackend, MockBackend, RLBackend
    from circuit_agent.rl.rollout import (
        CandidateResult,
        RolloutResult,
        run_rollout,
    )
    from circuit_agent.rl.train_loop import train


def __getattr__(name: str) -> Any:
    """Lazily import and return a public symbol on first access (PEP 562)."""
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, name)


def __dir__() -> list[str]:
    return sorted(set(__all__) | set(globals()))
