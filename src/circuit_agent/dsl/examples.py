"""Hand-written reference circuits, as sandbox-safe ``build()`` programs.

Each entry in :data:`EXAMPLE_PROGRAMS` is a complete program *string* that defines
``build() -> Circuit`` using ONLY the injected builder API (no imports), so it runs
unchanged through :func:`circuit_agent.dsl.sandbox.run_program`. The same circuits
are also exposed as in-process callables in :data:`EXAMPLE_BUILDERS` (handy for
tests that want a :class:`Circuit` directly).

The circuits are designed to PASS the relevant validators:

* ``usb_c_5v_led`` -- 5.1k Rd pulldowns on BOTH CC1 and CC2 to GND.
* ``ldo_3v3``      -- input cap on VIN-GND and output cap on VOUT-GND.
* ``i2c_sensor_breakout`` -- pullups on SDA and SCL to +3V3.
* ``mcu_minimal``  -- a decoupling cap on the MCU VDD rail to GND.
"""

from __future__ import annotations

from typing import Callable

from circuit_agent.dsl.builder import Circuit

# --------------------------------------------------------------------------- #
# Program strings (sandbox-safe: no imports, builder API only).
# --------------------------------------------------------------------------- #

_LED_RESISTOR = '''
def build():
    c = Circuit("led_resistor", description="Current-limited LED")
    r1 = c.add_resistor("R1", "330")
    d1 = c.add_led("D1", "RED")
    c.net("VCC").connect(r1, "1")
    c.net("LED_A").connect(r1, "2").connect(d1, "A")
    c.net("GND").connect(d1, "K")
    return c
'''

_LDO_3V3 = '''
def build():
    c = Circuit("ldo_3v3", description="5V to 3.3V LDO with input/output caps")
    u1 = c.add_part(
        "U1",
        symbol="Regulator_Linear:AP2112K-3.3",
        footprint="Package_TO_SOT_SMD:SOT-23-5",
        value="AP2112K-3.3",
        role="ldo",
    )
    cin = c.add_capacitor("C1", "1u")
    cout = c.add_capacitor("C2", "1u")
    c.net("+5V").connect(u1, "1").connect(cin, "1")
    c.net("GND").connect(u1, "2").connect(cin, "2").connect(cout, "2")
    c.net("EN").connect(u1, "3").connect(u1, "1")
    c.net("+3V3").connect(u1, "5").connect(cout, "1")
    return c
'''

_USB_C_5V_LED = '''
def build():
    c = Circuit("usb_c_5v_led", description="USB-C 5V sink with power LED")
    j1 = c.add_part(
        "J1",
        symbol="Connector:USB_C_Receptacle_USB2.0",
        footprint="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
        value="USB-C",
    )
    rcc1 = c.add_resistor("R1", "5.1k", role="usb_cc_rd")
    rcc2 = c.add_resistor("R2", "5.1k", role="usb_cc_rd")
    rled = c.add_resistor("R3", "330")
    d1 = c.add_led("D1", "RED")

    c.net("VBUS").connect(j1, "A4").connect(j1, "B4").connect(j1, "A9").connect(j1, "B9").connect(rled, "1")
    c.net("GND").connect(j1, "A1").connect(j1, "A12").connect(j1, "B1").connect(j1, "B12")
    c.net("GND").connect(rcc1, "2").connect(rcc2, "2").connect(d1, "K")
    c.net("CC1").connect(j1, "A5").connect(rcc1, "1")
    c.net("CC2").connect(j1, "B5").connect(rcc2, "1")
    c.net("LED_A").connect(rled, "2").connect(d1, "A")
    return c
'''

_I2C_SENSOR_BREAKOUT = '''
def build():
    c = Circuit("i2c_sensor_breakout", description="Generic I2C sensor with SDA/SCL pullups")
    u1 = c.add_part(
        "U1",
        symbol="Sensor:GenericI2C",
        footprint="Package_TO_SOT_SMD:SOT-23-5",
        value="I2C-SENSOR",
    )
    cb = c.add_capacitor("C1", "100n")
    rsda = c.add_resistor("R1", "4.7k", role="i2c_pullup")
    rscl = c.add_resistor("R2", "4.7k", role="i2c_pullup")

    c.net("+3V3").connect(u1, "1").connect(cb, "1").connect(rsda, "1").connect(rscl, "1")
    c.net("GND").connect(u1, "2").connect(cb, "2").connect(u1, "5")
    c.net("SDA").connect(u1, "3").connect(rsda, "2")
    c.net("SCL").connect(u1, "4").connect(rscl, "2")
    return c
'''

_MCU_MINIMAL = '''
def build():
    c = Circuit("mcu_minimal", description="Minimal STM32 with decoupling and reset")
    u1 = c.add_part(
        "U1",
        symbol="MCU_ST_STM32F0:STM32F030F4Px",
        footprint="Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm",
        value="STM32F030F4",
    )
    cdec = c.add_capacitor("C1", "100n")
    crst = c.add_capacitor("C2", "100n")
    rrst = c.add_resistor("R1", "10k")

    c.net("+3V3").connect(u1, "16").connect(cdec, "1").connect(rrst, "1")
    c.net("GND").connect(u1, "15").connect(cdec, "2").connect(crst, "2").connect(u1, "1")
    c.net("NRST").connect(u1, "4").connect(rrst, "2").connect(crst, "1")
    return c
'''


EXAMPLE_PROGRAMS: dict[str, str] = {
    "led_resistor": _LED_RESISTOR.strip() + "\n",
    "ldo_3v3": _LDO_3V3.strip() + "\n",
    "usb_c_5v_led": _USB_C_5V_LED.strip() + "\n",
    "i2c_sensor_breakout": _I2C_SENSOR_BREAKOUT.strip() + "\n",
    "mcu_minimal": _MCU_MINIMAL.strip() + "\n",
}


def _build_from_program(code: str) -> Circuit:
    """Execute an example program string in-process and return its Circuit.

    The example programs are trusted, hand-written source (not model output), so
    they can be executed directly here for the in-process builder map.
    """
    namespace: dict = {"Circuit": Circuit}
    exec(compile(code, "<example>", "exec"), namespace)  # noqa: S102 - trusted source
    build = namespace["build"]
    return build()


def _make_builder(name: str) -> Callable[[], Circuit]:
    code = EXAMPLE_PROGRAMS[name]
    return lambda: _build_from_program(code)


EXAMPLE_BUILDERS: dict[str, Callable[[], Circuit]] = {
    name: _make_builder(name) for name in EXAMPLE_PROGRAMS
}


def get_example_program(name: str) -> str:
    """Return the program string for ``name`` (raises KeyError if unknown)."""
    return EXAMPLE_PROGRAMS[name]


def list_examples() -> list[str]:
    """Return the sorted list of example names."""
    return sorted(EXAMPLE_PROGRAMS)


__all__ = [
    "EXAMPLE_PROGRAMS",
    "EXAMPLE_BUILDERS",
    "get_example_program",
    "list_examples",
]
