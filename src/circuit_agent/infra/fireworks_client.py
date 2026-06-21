"""Thin OpenAI-compatible chat client for Fireworks AI.

Talks to the Fireworks REST ``/chat/completions`` endpoint. ``requests`` is
imported lazily inside :meth:`FireworksClient.chat` so importing this module (and
the ``circuit_agent.infra`` package) never hard-requires it. There is no
Anthropic/OpenAI-the-company code here: the only network destination is the
Fireworks endpoint configured in :class:`circuit_agent.config.Settings`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover - typing only
    from circuit_agent.config import Settings


class FireworksError(Exception):
    """Raised on configuration or HTTP errors talking to Fireworks."""


class FireworksClient:
    """Minimal chat-completions client over the Fireworks OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.fireworks.ai/inference/v1",
        timeout: float = 120.0,
    ) -> None:
        if not api_key:
            raise FireworksError("FireworksClient requires a non-empty API key.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @classmethod
    def from_settings(cls, settings: "Settings") -> "FireworksClient":
        """Build a client from :class:`Settings`; raise if no API key is set."""
        if not settings.fireworks_api_key:
            raise FireworksError(
                "No Fireworks API key configured. Set FIREWORKS_API_KEY in the "
                "environment before using the Fireworks backend/critic."
            )
        return cls(
            api_key=settings.fireworks_api_key,
            base_url=settings.fireworks_base_url,
            timeout=settings.request_timeout,
        )

    def chat(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        n: int = 1,
        stop=None,
        response_format: Optional[dict] = None,
    ) -> list[str]:
        """POST a chat-completions request; return the choice message contents."""
        try:
            import requests  # lazy: only needed for an actual network call
        except Exception as exc:  # ImportError
            raise FireworksError(
                "The 'requests' package is required for Fireworks calls. Install it "
                "with `pip install requests` (or `pip install -e '.[fireworks]'`)."
            ) from exc

        url = f"{self.base_url}/chat/completions"
        body: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "n": n,
        }
        if stop is not None:
            body["stop"] = stop
        if response_format is not None:
            body["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(url, json=body, headers=headers, timeout=self.timeout)
        except Exception as exc:  # noqa: BLE001 - network failure
            raise FireworksError(f"Fireworks request failed: {exc}") from exc

        if resp.status_code != 200:
            raise FireworksError(
                f"Fireworks returned HTTP {resp.status_code}: {resp.text[:500]}"
            )

        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise FireworksError(f"Could not decode Fireworks response: {exc}") from exc

        choices = data.get("choices") or []
        contents: list[str] = []
        for choice in choices:
            message = choice.get("message") or {}
            contents.append(message.get("content", "") or "")
        return contents


def available(settings) -> bool:
    """Return ``True`` when settings carry a Fireworks API key."""
    return bool(getattr(settings, "fireworks_api_key", None))


__all__ = ["FireworksError", "FireworksClient", "available"]
