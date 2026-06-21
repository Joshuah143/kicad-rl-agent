"""Task specification.

A :class:`TaskSpec` captures *what* circuit to build (requirements), *how* to
weight the deterministic reward (:class:`Objectives`), and the soft *preferences*
(package type, hand-solderability, budgets) the validators consult.

Tasks are authored as YAML and loaded with :func:`load_task`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class Objectives(BaseModel):
    """Weights applied to each deterministic reward component."""

    model_config = ConfigDict(extra="forbid")

    erc_weight: float = 3.0
    graph_rule_weight: float = 2.0
    electrical_rule_weight: float = 4.0
    cost_weight: float = 1.0
    size_weight: float = 0.5
    availability_weight: float = 1.0
    llm_critic_weight: float = 2.0


class Preferences(BaseModel):
    """Soft design preferences (used to bias, not hard-fail, the reward)."""

    model_config = ConfigDict(extra="forbid")

    package_type: Optional[str] = None
    min_hand_solderable: Optional[str] = None
    max_bom_cost_usd: Optional[float] = None
    max_area_mm2: Optional[float] = None
    min_availability: Optional[float] = None


class TaskSpec(BaseModel):
    """A single circuit-design task."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    requirements: list[str] = Field(default_factory=list)
    objectives: Objectives = Field(default_factory=Objectives)
    preferences: Preferences = Field(default_factory=Preferences)
    allowed_parts: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


def load_task(path: Union[str, Path]) -> TaskSpec:
    """Load a :class:`TaskSpec` from a YAML file."""
    import yaml  # stdlib-adjacent core dep; safe to import eagerly here

    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    return TaskSpec.model_validate(data)


__all__ = ["Objectives", "Preferences", "TaskSpec", "load_task"]
