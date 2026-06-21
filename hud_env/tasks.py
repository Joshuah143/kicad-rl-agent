"""Tasks for the kicad-schematics environment.

Run a local eval with, e.g.:

    hud eval tasks.py claude --task-ids usb-c-5v-led --group 3

``hud eval`` scans this module for public ``Task`` objects. We mint one Task per
shipped circuit-design task by *calling* the ``kicad_design`` template, and give
each a stable ``slug`` plus a ``columns`` mapping (handy for the HUD UI / API).

Underscore-prefixed intermediates are skipped by the scanner; only the public
``tasks`` list (and the re-exported ``env``) is collected.

The taskset covers ALL shipped tasks (the original 5 + the expanded set). Each
task is tagged with an ``archetype`` column (size|cost|avail|handsolder|power|
usb|signal|mcu|motor) describing what component-choice lever it stresses.
"""

from __future__ import annotations

from env import env, kicad_design  # noqa: F401 - env MUST be importable/re-exported

# Map each task base name -> archetype. The list is the authoritative taskset.
_TASK_ARCHETYPES: dict[str, str] = {
    # original 5
    "usb_c_5v_led": "usb",
    "led_resistor": "signal",
    "ldo_3v3": "power",
    "i2c_sensor_breakout": "signal",
    "mcu_minimal": "mcu",
    # size-stressed
    "led_blinky_tiny": "size",
    "decoupling_tiny": "size",
    # cost-stressed
    "ldo_3v3_lowcost": "cost",
    "cost_capped_sensor": "cost",
    # availability-stressed
    "ldo_3v3_highavail": "avail",
    "jellybean_only_led": "avail",
    # hand-solder / THT
    "handsolder_led": "handsolder",
    "thru_hole_psu": "handsolder",
    # power
    "ldo_3v3_tiny": "power",
    "ldo_3v3_highcurrent": "power",
    "reverse_polarity_protection": "power",
    "load_switch_pmos": "power",
    "buck_converter_support": "power",
    # usb
    "usb_c_sink_basic": "usb",
    "usb_c_power_input": "usb",
    # signal
    "i2c_dual_sensor": "signal",
    "button_debounce": "signal",
    "uart_header": "signal",
    "rc_lowpass_filter": "signal",
    "resistor_divider": "signal",
    # mcu
    "rp2040_minimal": "mcu",
    "esp32_minimal": "mcu",
    "stm32_minimal_swd": "mcu",
    # motor
    "motor_driver_support": "motor",
}


def _slug(name: str) -> str:
    """Turn a task base name into a stable URL-safe slug."""
    return name.replace("_", "-")


def _mint(name: str, archetype: str):
    """Mint a single hud.Task for ``name`` with slug + columns set."""
    task = kicad_design(task_name=name)
    task.slug = _slug(name)
    task.columns = {"task": name, "archetype": archetype}
    return task


# Public taskset: every shipped task, one Task each.
tasks = [_mint(name, archetype) for name, archetype in _TASK_ARCHETYPES.items()]

__all__ = ["env", "kicad_design", "tasks"]
