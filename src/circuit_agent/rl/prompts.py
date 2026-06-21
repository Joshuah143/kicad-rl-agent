"""Prompt construction for the policy model.

Builds the system + user prompts that instruct a Fireworks-served model to emit a
``build() -> Circuit`` program in the constrained DSL. Kept dependency-free
(stdlib only) so the offline path imports cleanly.
"""

from __future__ import annotations

from typing import Optional

from circuit_agent.task import TaskSpec

SYSTEM_PROMPT = (
    "You are a hardware design assistant. You generate a single circuit using a "
    "constrained Python builder API called `Circuit`.\n\n"
    "Output ONLY Python source code that defines a function `build()` returning a "
    "`Circuit`. Do not write anything else: no prose, no markdown outside a single "
    "optional ```python fenced block, no explanations.\n\n"
    "HARD CONSTRAINTS (your code is run in a sandbox):\n"
    "- NO imports of any kind.\n"
    "- NO file IO, network, shell, eval/exec, or dunder attribute access.\n"
    "- Use ONLY the injected `Circuit` builder API.\n"
    "- Every component ref must be unique.\n"
    "- Provide a ground net named 'GND' and connect all grounds to it.\n"
    "- Honour the task requirements, preferences and allowed parts."
)


def builder_api_reference() -> str:
    """Return a concise reference for the builder methods available in the sandbox."""
    return (
        "Builder API (the only API available; no imports):\n"
        "  c = Circuit(name, description=None, design_intent=None)\n"
        "  h = c.add_part(ref, symbol, footprint=None, value=None, role=None,\n"
        "                 package_type='SMD', unit_cost_usd=None, availability_score=None,\n"
        "                 package_dims_mm=None, pins=None, **attributes)  # -> part handle\n"
        "  h = c.add_resistor(ref, value, footprint=None, role=None)     # symbol Device:R\n"
        "  h = c.add_capacitor(ref, value, footprint=None, role=None)    # symbol Device:C\n"
        "  h = c.add_led(ref, value='LED', footprint=None, role=None)    # symbol Device:LED\n"
        "  h = c.add_part_from_db(ref, key, **overrides)                 # use a catalog key\n"
        "  c.add_constraint(type, **params)\n"
        "  c.net(name).connect(part_or_ref, pin).connect(...)            # chainable\n"
        "  c.connect(net_name, 'REF.PIN', 'REF.PIN', ...)                # chainable\n"
        "  return c   # from build()\n"
    )


def allowed_parts_block(task: TaskSpec) -> str:
    """Render the task's allowed parts with their catalog specs."""
    if not task.allowed_parts:
        return "Allowed parts: (no restriction; use sensible standard parts)."
    from circuit_agent.data import parts_db

    lines = ["Allowed parts (catalog key -> spec):"]
    for key in task.allowed_parts:
        spec = parts_db.resolve_part(key)
        if spec:
            lines.append(
                f"  - {key}: symbol={spec.get('symbol')} footprint={spec.get('footprint')} "
                f"value={spec.get('value')} pkg={spec.get('package_type')}"
            )
        else:
            lines.append(f"  - {key}: (unknown key; use a sensible equivalent)")
    return "\n".join(lines)


def build_user_prompt(
    task: TaskSpec,
    *,
    examples: Optional[list[str]] = None,
    max_examples: int = 1,
) -> str:
    """Assemble the user prompt from the task spec (and optional examples)."""
    obj = task.objectives
    prefs = task.preferences

    lines: list[str] = []
    lines.append(f"TASK: {task.name}")
    if task.description:
        lines.append(f"DESCRIPTION: {task.description}")

    if task.requirements:
        lines.append("\nREQUIREMENTS:")
        for r in task.requirements:
            lines.append(f"  - {r}")

    lines.append("\nPREFERENCES:")
    lines.append(f"  package_type={prefs.package_type} min_hand_solderable={prefs.min_hand_solderable}")
    lines.append(
        f"  max_bom_cost_usd={prefs.max_bom_cost_usd} max_area_mm2={prefs.max_area_mm2} "
        f"min_availability={prefs.min_availability}"
    )

    lines.append("\nOBJECTIVE WEIGHTS (higher = more important):")
    lines.append(
        f"  erc={obj.erc_weight} graph={obj.graph_rule_weight} electrical={obj.electrical_rule_weight} "
        f"cost={obj.cost_weight} size={obj.size_weight} availability={obj.availability_weight} "
        f"critic={obj.llm_critic_weight}"
    )

    lines.append("\n" + allowed_parts_block(task))
    lines.append("\n" + builder_api_reference())

    if examples:
        lines.append("\nREFERENCE EXAMPLE(S):")
        for ex in examples[:max_examples]:
            lines.append("```python")
            lines.append(ex.strip())
            lines.append("```")

    lines.append(
        "\nOUTPUT FORMAT: return ONLY the Python code defining build() -> Circuit. "
        "No prose. A single optional ```python code fence is allowed."
    )
    return "\n".join(lines)


def build_prompt(task: TaskSpec, **kw) -> str:
    """Convenience: combine the system + user prompts into one string."""
    return SYSTEM_PROMPT + "\n\n" + build_user_prompt(task, **kw)


def build_repair_prompt(task: TaskSpec, prev_code: str, errors: list[str]) -> str:
    """Build a prompt asking the model to fix a previously-failing program."""
    err_block = "\n".join(f"  - {e}" for e in errors) or "  - (no specific errors captured)"
    return (
        SYSTEM_PROMPT
        + "\n\n"
        + build_user_prompt(task)
        + "\n\nYOUR PREVIOUS ATTEMPT FAILED. Code:\n```python\n"
        + prev_code.strip()
        + "\n```\n\nERRORS:\n"
        + err_block
        + "\n\nReturn a CORRECTED build() -> Circuit program. Output ONLY the code."
    )


__all__ = [
    "SYSTEM_PROMPT",
    "builder_api_reference",
    "allowed_parts_block",
    "build_user_prompt",
    "build_prompt",
    "build_repair_prompt",
]
