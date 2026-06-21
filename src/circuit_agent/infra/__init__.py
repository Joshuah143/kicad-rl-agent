"""Infrastructure: Fireworks client, end-to-end verifier, and the Modal sandbox.

This package is intentionally light at import time. Heavy/optional dependencies
(``requests`` for Fireworks, ``modal`` for the sandbox) are imported lazily by
their respective modules, so importing ``circuit_agent.infra`` never requires
them.

``FireworksClient``/``FireworksError`` are re-exported when their module is
present; they are guarded so this package stays importable even before the
Fireworks client module has been created.
"""

from __future__ import annotations

__all__ = ["FireworksClient", "FireworksError"]

try:  # Fireworks client is an optional sibling module.
    from circuit_agent.infra.fireworks_client import (  # noqa: F401
        FireworksClient,
        FireworksError,
    )
except Exception:  # pragma: no cover - module not present yet / requests missing
    pass
