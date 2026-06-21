"""Tasks for the kicad-schematics environment.

Run a local eval with, e.g.:

    hud eval tasks.py claude --task-ids usb-c-5v-led --group 3

``hud eval`` scans this module for public ``Task`` objects. We mint one Task per
shipped circuit-design task by *calling* the ``kicad_design`` template, and give
each a stable ``slug`` plus a ``columns`` mapping (handy for the HUD UI / API).

Underscore-prefixed intermediates are skipped by the scanner; only the public
``tasks`` list (and the re-exported ``env``) is collected.
"""

from __future__ import annotations

from env import env, kicad_design  # noqa: F401 - env MUST be importable/re-exported

# Verified against hud-python 0.6.6: calling the template returns a hud.Task
# whose ``.slug`` and ``.columns`` are plain settable fields.
_usb = kicad_design(task_name="usb_c_5v_led")
_usb.slug = "usb-c-5v-led"
_usb.columns = {"task": "usb_c_5v_led"}

_led = kicad_design(task_name="led_resistor")
_led.slug = "led-resistor"
_led.columns = {"task": "led_resistor"}

_ldo = kicad_design(task_name="ldo_3v3")
_ldo.slug = "ldo-3v3"
_ldo.columns = {"task": "ldo_3v3"}

_i2c = kicad_design(task_name="i2c_sensor_breakout")
_i2c.slug = "i2c-sensor-breakout"
_i2c.columns = {"task": "i2c_sensor_breakout"}

_mcu = kicad_design(task_name="mcu_minimal")
_mcu.slug = "mcu-minimal"
_mcu.columns = {"task": "mcu_minimal"}

tasks = [_usb, _led, _ldo, _i2c, _mcu]
