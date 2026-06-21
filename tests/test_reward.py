"""Tests for :mod:`circuit_agent.validators.reward`.

``compute_reward`` is *the* deterministic reward. Given identical inputs it must
return an identical dict (no wall-clock, no randomness). It combines:

* ``schema_valid``        (fixed unit weight)
* ``erc``                 (``objectives.erc_weight``)
* ``graph_rules``         (``objectives.graph_rule_weight`` * ``graph.fraction()``)
* ``electrical_rules``    (``objectives.electrical_rule_weight`` * ``electrical.fraction()``)
* ``cost`` / ``size`` / ``availability`` / ``llm_critic``

These tests pin the contract's invariants without over-fitting to exact float
values: determinism, the effect of FATAL issues on ``passed`` and the total
reward, weight application via :class:`~circuit_agent.task.Objectives`, the
required output shape, and graceful handling of skipped ERC.
"""

from __future__ import annotations

from circuit_agent.dsl.builder import Circuit
from circuit_agent.dsl.schema import CircuitModel
from circuit_agent.task import Objectives, Preferences, TaskSpec
from circuit_agent.validators import reward as reward_mod
from circuit_agent.validators.base import (
    CriticResult,
    Severity,
    ValidationIssue,
    ValidatorResult,
)

# --------------------------------------------------------------------------- #
# Fixtures / builders
# --------------------------------------------------------------------------- #
def _clean_model() -> CircuitModel:
    c = Circuit("clean")
    r1 = c.add_resistor("R1", "330")
    d1 = c.add_led("D1", "RED")
    c.net("VCC").connect(r1, "1")
    c.net("A").connect(r1, "2").connect(d1, "A")
    c.net("GND").connect(d1, "K")
    return c.to_model()


def _task(objectives: Objectives | None = None, preferences: Preferences | None = None) -> TaskSpec:
    return TaskSpec(
        name="reward_task",
        objectives=objectives or Objectives(),
        preferences=preferences or Preferences(),
    )


def _passing_graph() -> ValidatorResult:
    """A graph result that passes (full fraction, no FATALs)."""
    return ValidatorResult(name="graph_rules", score=10.0, max_score=10.0, issues=[])


def _failing_graph() -> ValidatorResult:
    """A graph result with a FATAL issue and a reduced score."""
    return ValidatorResult(
        name="graph_rules",
        score=4.0,
        max_score=10.0,
        issues=[
            ValidationIssue(
                severity=Severity.FATAL,
                code="duplicate_ref",
                message="Duplicate component ref R1",
                refs=["R1"],
            )
        ],
    )


def _passing_electrical() -> ValidatorResult:
    return ValidatorResult(name="electrical_rules", score=8.0, max_score=8.0, issues=[])


def _bom(total: float = 0.71, missing: list[str] | None = None) -> dict:
    return {
        "total_cost_usd": total,
        "line_items": [
            {"ref": "R1", "value": "330", "unit_cost_usd": 0.002, "package_type": "SMD"},
            {"ref": "D1", "value": "RED", "unit_cost_usd": 0.04, "package_type": "SMD"},
        ],
        "missing_cost_refs": missing or [],
    }


def _size(total_area: float = 8.0, smt: int = 2, tht: int = 0) -> dict:
    return {
        "total_area_mm2": total_area,
        "smt_count": smt,
        "tht_count": tht,
        "virtual_count": 0,
        "by_ref": {"R1": 4.0, "D1": 4.0},
        "largest": {"ref": "R1", "area": 4.0},
        "missing_dims_refs": [],
    }


def _avail(min_av: float = 0.9, avg: float = 0.92) -> dict:
    return {
        "min_availability": min_av,
        "avg_availability": avg,
        "low_availability": [],
        "missing_refs": [],
    }


def _compute(
    *,
    model: CircuitModel,
    task: TaskSpec,
    schema_valid: bool = True,
    erc=None,
    erc_ran: bool = False,
    graph: ValidatorResult | None = None,
    electrical: ValidatorResult | None = None,
    bom: dict | None = None,
    size: dict | None = None,
    avail: dict | None = None,
    critic: CriticResult | None = None,
) -> dict:
    return reward_mod.compute_reward(
        model,
        task,
        schema_valid=schema_valid,
        erc=erc,
        erc_ran=erc_ran,
        graph=graph if graph is not None else _passing_graph(),
        electrical=electrical if electrical is not None else _passing_electrical(),
        bom=bom if bom is not None else _bom(),
        size=size if size is not None else _size(),
        avail=avail if avail is not None else _avail(),
        critic=critic,
    )


# --------------------------------------------------------------------------- #
# Output shape
# --------------------------------------------------------------------------- #
def test_reward_shape() -> None:
    """The returned dict has exactly the contracted top-level + nested keys."""
    out = _compute(model=_clean_model(), task=_task())

    assert set(out.keys()) == {
        "reward",
        "passed",
        "breakdown",
        "fatal_errors",
        "warnings",
        "metrics",
    }
    assert set(out["breakdown"].keys()) == {
        "schema_valid",
        "erc",
        "graph_rules",
        "electrical_rules",
        "cost",
        "size",
        "availability",
        "llm_critic",
    }
    assert set(out["metrics"].keys()) == {
        "total_cost_usd",
        "total_area_mm2",
        "min_availability",
        "smt_count",
        "tht_count",
    }
    assert isinstance(out["reward"], float)
    assert isinstance(out["passed"], bool)
    assert isinstance(out["fatal_errors"], list)
    assert isinstance(out["warnings"], list)


def test_metrics_reflect_inputs() -> None:
    """The metrics block mirrors the bom/size/avail inputs."""
    out = _compute(
        model=_clean_model(),
        task=_task(),
        bom=_bom(total=1.23),
        size=_size(total_area=42.0, smt=3, tht=1),
        avail=_avail(min_av=0.77),
    )
    metrics = out["metrics"]
    assert metrics["total_cost_usd"] == 1.23
    assert metrics["total_area_mm2"] == 42.0
    assert metrics["min_availability"] == 0.77
    assert metrics["smt_count"] == 3
    assert metrics["tht_count"] == 1


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #
def test_reward_is_deterministic() -> None:
    """Same inputs -> byte-identical dicts across repeated calls."""
    model = _clean_model()
    task = _task()
    critic = CriticResult(score=0.85, would_fabricate=True, source="stub")

    first = _compute(model=model, task=task, critic=critic)
    second = _compute(model=model, task=task, critic=critic)
    assert first == second


def test_reward_deterministic_with_fresh_objects() -> None:
    """Determinism must not depend on object identity of the inputs."""
    a = _compute(
        model=_clean_model(),
        task=_task(Objectives()),
        graph=_passing_graph(),
        electrical=_passing_electrical(),
    )
    b = _compute(
        model=_clean_model(),
        task=_task(Objectives()),
        graph=_passing_graph(),
        electrical=_passing_electrical(),
    )
    assert a == b


# --------------------------------------------------------------------------- #
# FATAL handling
# --------------------------------------------------------------------------- #
def test_graph_fatal_fails_and_lowers_reward() -> None:
    """A FATAL graph issue -> passed False and a strictly lower reward."""
    model = _clean_model()
    task = _task()

    clean = _compute(model=model, task=task, graph=_passing_graph())
    broken = _compute(model=model, task=task, graph=_failing_graph())

    assert clean["passed"] is True
    assert broken["passed"] is False
    assert broken["reward"] < clean["reward"]
    # The FATAL message must surface in fatal_errors.
    assert any("R1" in msg or "Duplicate" in msg for msg in broken["fatal_errors"])


def test_schema_invalid_fails() -> None:
    """schema_valid=False -> passed False and a recorded fatal error."""
    out = _compute(model=_clean_model(), task=_task(), schema_valid=False)
    assert out["passed"] is False
    assert out["breakdown"]["schema_valid"] == 0.0
    assert len(out["fatal_errors"]) >= 1


def test_reward_non_negative() -> None:
    """Even a fully-broken design keeps reward >= 0."""
    out = _compute(
        model=_clean_model(),
        task=_task(),
        schema_valid=False,
        graph=_failing_graph(),
        electrical=ValidatorResult(
            name="electrical_rules",
            score=0.0,
            max_score=8.0,
            issues=[
                ValidationIssue(
                    severity=Severity.FATAL,
                    code="usb_cc_missing_rd",
                    message="CC2 missing Rd pulldown",
                    refs=["J1"],
                )
            ],
        ),
        bom=_bom(total=999.0),
        size=_size(total_area=99999.0),
        avail=_avail(min_av=0.0, avg=0.0),
    )
    assert out["reward"] >= 0.0
    assert out["passed"] is False


# --------------------------------------------------------------------------- #
# Weights from Objectives are applied
# --------------------------------------------------------------------------- #
def test_graph_weight_scales_component() -> None:
    """Doubling graph_rule_weight doubles the graph_rules breakdown component."""
    model = _clean_model()
    base_obj = Objectives(graph_rule_weight=2.0)
    dbl_obj = Objectives(graph_rule_weight=4.0)

    base = _compute(model=model, task=_task(base_obj), graph=_passing_graph())
    dbl = _compute(model=model, task=_task(dbl_obj), graph=_passing_graph())

    # graph passes with fraction 1.0, so component == weight.
    assert base["breakdown"]["graph_rules"] == 2.0
    assert dbl["breakdown"]["graph_rules"] == 4.0


def test_electrical_weight_scales_component() -> None:
    """The electrical component equals electrical_rule_weight * fraction()."""
    model = _clean_model()
    obj = Objectives(electrical_rule_weight=4.0)
    elec = _passing_electrical()  # fraction == 1.0
    out = _compute(model=model, task=_task(obj), electrical=elec)
    assert out["breakdown"]["electrical_rules"] == 4.0


def test_zero_weight_zeroes_component() -> None:
    """A zero objective weight removes that component entirely."""
    model = _clean_model()
    obj = Objectives(
        graph_rule_weight=0.0,
        electrical_rule_weight=0.0,
        cost_weight=0.0,
        size_weight=0.0,
        availability_weight=0.0,
        erc_weight=0.0,
        llm_critic_weight=0.0,
    )
    out = _compute(model=model, task=_task(obj))
    bd = out["breakdown"]
    assert bd["graph_rules"] == 0.0
    assert bd["electrical_rules"] == 0.0
    assert bd["cost"] == 0.0
    assert bd["size"] == 0.0
    assert bd["availability"] == 0.0
    assert bd["erc"] == 0.0
    assert bd["llm_critic"] == 0.0
    # Only the fixed schema_valid component remains.
    assert out["reward"] == round(bd["schema_valid"], 4)


# --------------------------------------------------------------------------- #
# ERC handling
# --------------------------------------------------------------------------- #
def test_erc_skipped_is_warning_not_fatal() -> None:
    """When ERC did not run, contribute 0 and add a warning (no fatal)."""
    out = _compute(model=_clean_model(), task=_task(), erc=None, erc_ran=False)
    assert out["breakdown"]["erc"] == 0.0
    assert out["passed"] is True  # ERC skip must not fail the design
    assert any("erc" in w.lower() for w in out["warnings"])


def test_critic_score_feeds_llm_component() -> None:
    """A critic score scales the llm_critic component by its weight."""
    model = _clean_model()
    obj = Objectives(llm_critic_weight=2.0)
    critic = CriticResult(score=0.5, would_fabricate=True, source="stub")
    out = _compute(model=model, task=_task(obj), critic=critic)
    # 2.0 * 0.5 == 1.0
    assert out["breakdown"]["llm_critic"] == 1.0


def test_critic_fatal_issue_propagates() -> None:
    """Critic fatal_issues must surface in the reward's fatal_errors + fail it."""
    model = _clean_model()
    critic = CriticResult(
        score=0.1,
        fatal_issues=["CC2 has no Rd pulldown"],
        would_fabricate=False,
        source="stub",
    )
    out = _compute(model=model, task=_task(), critic=critic)
    assert any("CC2" in msg for msg in out["fatal_errors"])
    assert out["passed"] is False


def test_no_critic_zero_llm_component() -> None:
    """With no critic the llm_critic component is exactly 0."""
    out = _compute(model=_clean_model(), task=_task(), critic=None)
    assert out["breakdown"]["llm_critic"] == 0.0
