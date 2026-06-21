"""Shared result types for validators and the critic (pydantic v2, stdlib only)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Severity of a validation issue."""

    FATAL = "fatal"
    WARNING = "warning"
    INFO = "info"


class ValidationIssue(BaseModel):
    """A single problem found by a validator."""

    severity: Severity
    code: str
    message: str
    refs: list[str] = Field(default_factory=list)


class ValidatorResult(BaseModel):
    """The outcome of running one validator."""

    name: str
    score: float
    max_score: float
    issues: list[ValidationIssue] = Field(default_factory=list)
    details: dict = Field(default_factory=dict)

    @property
    def fatals(self) -> list[ValidationIssue]:
        """All FATAL issues."""
        return [i for i in self.issues if i.severity is Severity.FATAL]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """All WARNING issues."""
        return [i for i in self.issues if i.severity is Severity.WARNING]

    @property
    def passed(self) -> bool:
        """``True`` when there are no FATAL issues."""
        return not self.fatals

    def fraction(self) -> float:
        """Return ``score / max_score`` (1.0 when ``max_score`` is 0)."""
        if self.max_score == 0:
            return 1.0
        return self.score / self.max_score


class CriticResult(BaseModel):
    """The LLM critic's structured verdict."""

    score: float = 0.0  # 0..1
    fatal_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    would_fabricate: bool = False
    rationale: str = ""
    source: str = "stub"  # "stub" | "fireworks"
