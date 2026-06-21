"""LLM critic: an abstract interface, a conservative deterministic stub, and a
Fireworks-backed implementation.

The critic is the *optional* qualitative layer on top of the deterministic
validators. It must be CONSERVATIVE: a design that merely "looks" plausible but
has fatal issues or ERC errors must never be rewarded. No Anthropic/OpenAI code
is involved -- the Fireworks implementation talks to the Fireworks OpenAI-compatible
REST endpoint.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from circuit_agent.dsl.schema import CircuitModel
from circuit_agent.task import TaskSpec
from circuit_agent.validators.base import CriticResult

if TYPE_CHECKING:  # pragma: no cover - typing only
    from circuit_agent.infra.fireworks_client import FireworksClient
    from circuit_agent.kicad.parse_erc import ERCResult


CRITIC_SYSTEM_PROMPT = (
    "You are a CONSERVATIVE senior hardware review engineer evaluating a proposed "
    "circuit. You are given the task, the circuit as DSL JSON, an ERC summary and a "
    "summary of deterministic validator results. Judge whether the circuit would "
    "actually FABRICATE and FUNCTION, not merely whether it looks plausible.\n\n"
    "Rules:\n"
    "- Never reward a plausible-but-wrong design. If there are any fatal validator "
    "issues or ERC errors, the score MUST be <= 0.2 and would_fabricate MUST be false.\n"
    "- Prefer pointing out concrete electrical problems (missing pulldowns, missing "
    "decoupling, shorts, floating pins) over stylistic comments.\n"
    "- Return STRICT JSON with exactly these fields: score (0..1 float), "
    "fatal_issues (list[str]), warnings (list[str]), suggestions (list[str]), "
    "would_fabricate (bool), rationale (str).\n"
    "- Do not include any text outside the JSON object."
)


def _has_fatal(validator_report: dict) -> bool:
    """Return True if any validator sub-report carries a FATAL issue."""
    for key in ("graph", "electrical"):
        sub = validator_report.get(key)
        if sub is None:
            continue
        # Accept either a ValidatorResult or a plain dict.
        fatals = getattr(sub, "fatals", None)
        if fatals is not None:
            if fatals:
                return True
            continue
        if isinstance(sub, dict):
            for issue in sub.get("issues", []):
                sev = issue.get("severity") if isinstance(issue, dict) else None
                if str(sev).lower() == "fatal":
                    return True
    return False


class Critic(ABC):
    """Abstract critic interface."""

    @abstractmethod
    def review(
        self,
        *,
        task: TaskSpec,
        model: CircuitModel,
        erc: "Optional[ERCResult]",
        validator_report: dict,
        svg_path: Optional[str] = None,
    ) -> CriticResult:
        """Return a :class:`CriticResult` for the design."""
        raise NotImplementedError


class StubCritic(Critic):
    """Deterministic, conservative critic derived from the deterministic signals."""

    def review(
        self,
        *,
        task: TaskSpec,
        model: CircuitModel,
        erc: "Optional[ERCResult]",
        validator_report: dict,
        svg_path: Optional[str] = None,
    ) -> CriticResult:
        has_fatal = _has_fatal(validator_report)
        erc_errors = bool(erc is not None and getattr(erc, "error_count", 0) > 0)

        if has_fatal or erc_errors:
            # Never reward a design with hard problems.
            score = 0.1
            fatal_issues = []
            if has_fatal:
                fatal_issues.append("Deterministic validators reported fatal issue(s).")
            if erc_errors:
                fatal_issues.append("ERC reported error(s).")
            return CriticResult(
                score=score,
                fatal_issues=fatal_issues,
                warnings=[],
                suggestions=["Resolve all fatal validator/ERC issues before fabrication."],
                would_fabricate=False,
                rationale="Conservative stub: hard issues present, withholding endorsement.",
                source="stub",
            )

        # No fatal issues: start neutral and reward clean ERC + passing rules.
        score = 0.5
        if erc is not None and getattr(erc, "error_count", 0) == 0:
            score += 0.2
        score = min(score, 0.8)
        return CriticResult(
            score=round(score, 4),
            fatal_issues=[],
            warnings=[],
            suggestions=[],
            would_fabricate=True,
            rationale="Conservative stub: no fatal issues detected from deterministic signals.",
            source="stub",
        )


class FireworksCritic(Critic):
    """Critic backed by a Fireworks-served model (OpenAI-compatible chat)."""

    def __init__(self, client: "FireworksClient", model: str) -> None:
        self.client = client
        self.model = model

    def review(
        self,
        *,
        task: TaskSpec,
        model: CircuitModel,
        erc: "Optional[ERCResult]",
        validator_report: dict,
        svg_path: Optional[str] = None,
    ) -> CriticResult:
        try:
            user = self._build_user_message(task, model, erc, validator_report)
            completions = self.client.chat(
                self.model,
                [
                    {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
                temperature=0.0,
                max_tokens=1024,
                n=1,
                response_format={"type": "json_object"},
            )
            text = completions[0] if completions else "{}"
            data = json.loads(text)
            result = CriticResult(
                score=float(data.get("score", 0.0)),
                fatal_issues=list(data.get("fatal_issues", []) or []),
                warnings=list(data.get("warnings", []) or []),
                suggestions=list(data.get("suggestions", []) or []),
                would_fabricate=bool(data.get("would_fabricate", False)),
                rationale=str(data.get("rationale", "")),
                source="fireworks",
            )
            # Enforce conservatism even if the model misbehaves.
            if result.fatal_issues and result.score > 0.2:
                result.score = 0.2
                result.would_fabricate = False
            return result
        except Exception as exc:  # noqa: BLE001 - fall back to the stub
            fallback = StubCritic().review(
                task=task,
                model=model,
                erc=erc,
                validator_report=validator_report,
                svg_path=svg_path,
            )
            fallback.rationale = (
                f"Fireworks critic failed ({type(exc).__name__}: {exc}); "
                f"fell back to stub. {fallback.rationale}"
            )
            return fallback

    def _build_user_message(
        self,
        task: TaskSpec,
        model: CircuitModel,
        erc: "Optional[ERCResult]",
        validator_report: dict,
    ) -> str:
        erc_summary = "ERC not run."
        if erc is not None:
            erc_summary = (
                f"ERC: {getattr(erc, 'error_count', 0)} error(s), "
                f"{getattr(erc, 'warning_count', 0)} warning(s)."
            )

        def _summarise(sub) -> dict:
            dump = getattr(sub, "model_dump", None)
            if callable(dump):
                return dump()
            return sub if isinstance(sub, dict) else {}

        validator_summary = {
            k: _summarise(v) for k, v in validator_report.items() if v is not None
        }
        return (
            f"TASK:\n{task.model_dump_json()}\n\n"
            f"CIRCUIT (DSL JSON):\n{model.model_dump_json()}\n\n"
            f"{erc_summary}\n\n"
            f"VALIDATOR SUMMARY:\n{json.dumps(validator_summary, default=str)}\n\n"
            "Return the strict JSON verdict now."
        )


def make_critic(kind: str, *, settings=None) -> Critic:
    """Build a critic by kind: ``"stub"`` or ``"fireworks"``."""
    key = (kind or "").strip().lower()
    if key == "stub":
        return StubCritic()
    if key == "fireworks":
        if settings is None:
            from circuit_agent.config import load_settings

            settings = load_settings()
        if not getattr(settings, "fireworks_api_key", None):
            raise ValueError(
                "FireworksCritic requires a Fireworks API key. Set FIREWORKS_API_KEY "
                "in the environment, or use the 'stub' critic."
            )
        from circuit_agent.infra.fireworks_client import FireworksClient

        client = FireworksClient.from_settings(settings)
        return FireworksCritic(client, settings.critic_model)
    raise ValueError(f"Unknown critic kind {kind!r}. Choose 'stub' or 'fireworks'.")


__all__ = [
    "Critic",
    "StubCritic",
    "FireworksCritic",
    "CRITIC_SYSTEM_PROMPT",
    "make_critic",
]
