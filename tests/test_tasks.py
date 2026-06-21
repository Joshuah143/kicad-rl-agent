"""Task-spec sanity tests over every shipped tasks/*.yaml.

Pins the contract that makes the taskset trainable:

* Every YAML loads as a :class:`TaskSpec`.
* Every ``allowed_parts`` key is a real catalog key (allowed_parts subset PARTS).
* Every task offers at least one role with >= 2 allowed alternatives, so the
  policy must actually CHOOSE a part rather than have it forced.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from circuit_agent.data import parts_db
from circuit_agent.task import TaskSpec, load_task

_TASKS_DIR = Path(__file__).resolve().parent.parent / "tasks"


def _task_files() -> list[Path]:
    return sorted(_TASKS_DIR.glob("*.yaml"))


def test_tasks_dir_nonempty() -> None:
    files = _task_files()
    # The original 5 plus the expanded set.
    assert len(files) >= 25, f"expected many tasks, found {len(files)}"


@pytest.mark.parametrize("path", _task_files(), ids=lambda p: p.stem)
def test_task_loads_as_taskspec(path: Path) -> None:
    task = load_task(path)
    assert isinstance(task, TaskSpec)
    assert task.name


@pytest.mark.parametrize("path", _task_files(), ids=lambda p: p.stem)
def test_allowed_parts_subset_of_parts(path: Path) -> None:
    task = load_task(path)
    for key in task.allowed_parts:
        assert key in parts_db.PARTS, f"{path.stem}: allowed part {key!r} not in PARTS"


@pytest.mark.parametrize("path", _task_files(), ids=lambda p: p.stem)
def test_task_has_a_role_with_two_alternatives(path: Path) -> None:
    task = load_task(path)
    roles = Counter(
        parts_db.PARTS[k].role for k in task.allowed_parts if parts_db.PARTS[k].role
    )
    assert any(count >= 2 for count in roles.values()), (
        f"{path.stem}: no role with >=2 allowed alternatives (roles={dict(roles)})"
    )


def test_original_five_tasks_present() -> None:
    names = {p.stem for p in _task_files()}
    for original in ("usb_c_5v_led", "led_resistor", "ldo_3v3", "i2c_sensor_breakout", "mcu_minimal"):
        assert original in names, f"original task {original} missing"
