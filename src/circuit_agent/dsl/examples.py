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


# --------------------------------------------------------------------------- #
# Additional reference programs for the expanded task set. Each is sandbox-safe
# (no imports, builder API only) and chooses a sensible part to score well.
# --------------------------------------------------------------------------- #

_LED_BLINKY_TINY = '''
def build():
    c = Circuit("led_blinky_tiny", description="Smallest current-limited LED")
    r1 = c.add_part_from_db("R1", "resistor_0402", value="330")
    d1 = c.add_part_from_db("D1", "led_0402", value="RED")
    c.net("VCC").connect(r1, "1")
    c.net("LED_A").connect(r1, "2").connect(d1, "A")
    c.net("GND").connect(d1, "K")
    return c
'''

_HANDSOLDER_LED = '''
def build():
    c = Circuit("handsolder_led", description="Hand-solderable (>=0805) LED")
    r1 = c.add_part_from_db("R1", "resistor_0805", value="330")
    d1 = c.add_part_from_db("D1", "led_0805", value="RED")
    c.net("VCC").connect(r1, "1")
    c.net("LED_A").connect(r1, "2").connect(d1, "A")
    c.net("GND").connect(d1, "K")
    return c
'''

_LDO_3V3_LOWCOST = '''
def build():
    c = Circuit("ldo_3v3_lowcost", description="Cheapest 3.3V LDO with caps")
    u1 = c.add_part_from_db("U1", "ldo_3v3_xc6206")
    cin = c.add_part_from_db("C1", "cap_0603_1u", value="1u")
    cout = c.add_part_from_db("C2", "cap_0603_1u", value="1u")
    c.net("+5V").connect(u1, "1").connect(cin, "1")
    c.net("GND").connect(u1, "2").connect(cin, "2").connect(cout, "2")
    c.net("+3V3").connect(u1, "3").connect(cout, "1")
    return c
'''

_REVERSE_POLARITY = '''
def build():
    c = Circuit("reverse_polarity_protection", description="Series Schottky RPP")
    j1 = c.add_part_from_db("J1", "barrel_jack_dc")
    d1 = c.add_part_from_db("D1", "diode_schottky_sma", value="SS34")
    cb = c.add_part_from_db("C1", "cap_1206_10u", value="10u")
    c.net("VIN").connect(j1, "1").connect(d1, "2")
    c.net("VRAIL").connect(d1, "1").connect(cb, "1")
    c.net("GND").connect(j1, "2").connect(cb, "2")
    return c
'''

_BUTTON_DEBOUNCE = '''
def build():
    c = Circuit("button_debounce", description="Push button with RC debounce + pullup")
    sw = c.add_part_from_db("SW1", "button_smd_4p")
    rpu = c.add_part_from_db("R1", "resistor_0603", value="10k")
    cd = c.add_part_from_db("C1", "cap_0603_100n", value="100n")
    c.net("+3V3").connect(rpu, "1")
    c.net("BTN").connect(rpu, "2").connect(sw, "1").connect(cd, "1")
    c.net("GND").connect(sw, "2").connect(cd, "2")
    return c
'''

_RESISTOR_DIVIDER = '''
def build():
    c = Circuit("resistor_divider", description="Two-resistor voltage divider")
    rtop = c.add_part_from_db("R1", "resistor_0402", value="10k")
    rbot = c.add_part_from_db("R2", "resistor_0402", value="10k")
    c.net("VIN").connect(rtop, "1")
    c.net("VSENSE").connect(rtop, "2").connect(rbot, "1")
    c.net("GND").connect(rbot, "2")
    return c
'''

_MOTOR_DRIVER_SUPPORT = '''
def build():
    c = Circuit("motor_driver_support", description="DRV8833 with decoupling + bulk + flyback")
    u1 = c.add_part_from_db("U1", "motor_driver_drv8833")
    cdec = c.add_part_from_db("C1", "cap_0603_100n", value="100n")
    cbulk = c.add_part_from_db("C2", "cap_0805_10u", value="10u")
    d1 = c.add_part_from_db("D1", "diode_schottky_sma", value="SS34")
    c.net("VM").connect(u1, "1").connect(cdec, "1").connect(cbulk, "1").connect(d1, "1")
    c.net("GND").connect(u1, "9").connect(cdec, "2").connect(cbulk, "2").connect(d1, "2")
    return c
'''


_LDO_3V3_TINY = '''
def build():
    c = Circuit("ldo_3v3_tiny", description="Smallest-footprint 3.3V LDO with caps")
    u1 = c.add_part_from_db("U1", "ldo_3v3_xc6206")
    cin = c.add_part_from_db("C1", "cap_0402_100n", value="100n")
    cout = c.add_part_from_db("C2", "cap_0402_100n", value="100n")
    c.net("+5V").connect(u1, "1").connect(cin, "1")
    c.net("GND").connect(u1, "2").connect(cin, "2").connect(cout, "2")
    c.net("+3V3").connect(u1, "3").connect(cout, "1")
    return c
'''

_LDO_3V3_HIGHAVAIL = '''
def build():
    c = Circuit("ldo_3v3_highavail", description="Most-available 3.3V LDO with caps")
    u1 = c.add_part_from_db("U1", "ldo_3v3_xc6206")
    cin = c.add_part_from_db("C1", "cap_0603_1u", value="1u")
    cout = c.add_part_from_db("C2", "cap_0603_1u", value="1u")
    c.net("+5V").connect(u1, "1").connect(cin, "1")
    c.net("GND").connect(u1, "2").connect(cin, "2").connect(cout, "2")
    c.net("+3V3").connect(u1, "3").connect(cout, "1")
    return c
'''

_LDO_3V3_HIGHCURRENT = '''
def build():
    c = Circuit("ldo_3v3_highcurrent", description="1A SOT-223 3.3V LDO with bulk caps")
    u1 = c.add_part_from_db("U1", "ldo_3v3_sot223")
    cin = c.add_part_from_db("C1", "cap_0805_10u", value="10u")
    cout = c.add_part_from_db("C2", "cap_0805_10u", value="10u")
    c.net("GND").connect(u1, "1").connect(cin, "2").connect(cout, "2")
    c.net("+3V3").connect(u1, "2").connect(cout, "1")
    c.net("+5V").connect(u1, "3").connect(cin, "1")
    return c
'''

_DECOUPLING_TINY = '''
def build():
    c = Circuit("decoupling_tiny", description="Two tiny 100nF decoupling caps")
    c1 = c.add_part_from_db("C1", "cap_0402_100n", value="100n")
    c2 = c.add_part_from_db("C2", "cap_0402_100n", value="100n")
    c.net("+3V3").connect(c1, "1").connect(c2, "1")
    c.net("GND").connect(c1, "2").connect(c2, "2")
    return c
'''

_RC_LOWPASS_FILTER = '''
def build():
    c = Circuit("rc_lowpass_filter", description="Single-pole RC low-pass on a signal")
    r1 = c.add_part_from_db("R1", "resistor_0402", value="1k")
    c1 = c.add_part_from_db("C1", "cap_0402_100n", value="100n")
    c.net("SIG_IN").connect(r1, "1")
    c.net("SIG_OUT").connect(r1, "2").connect(c1, "1")
    c.net("GND").connect(c1, "2")
    return c
'''

_UART_HEADER = '''
def build():
    c = Circuit("uart_header", description="UART breakout header with series resistors")
    j1 = c.add_part_from_db("J1", "header_1x4_254", value="UART")
    rtx = c.add_part_from_db("R1", "resistor_tht", value="100")
    rrx = c.add_part_from_db("R2", "resistor_tht", value="100")
    c.net("GND").connect(j1, "1")
    c.net("+3V3").connect(j1, "2")
    c.net("TX").connect(j1, "3").connect(rtx, "1")
    c.net("TX_MCU").connect(rtx, "2")
    c.net("RX").connect(j1, "4").connect(rrx, "1")
    c.net("RX_MCU").connect(rrx, "2")
    return c
'''

_LOAD_SWITCH_PMOS = '''
def build():
    c = Circuit("load_switch_pmos", description="High-side P-MOSFET load switch")
    q1 = c.add_part_from_db("Q1", "mosfet_p_ao3401_sot23")
    rg = c.add_part_from_db("R1", "resistor_0402", value="100")
    rpd = c.add_part_from_db("R2", "resistor_0402", value="100k")
    cout = c.add_part_from_db("C1", "cap_0603_1u", value="1u")
    c.net("+5V").connect(q1, "2").connect(rpd, "1")
    c.net("GATE").connect(q1, "1").connect(rg, "2").connect(rpd, "2")
    c.net("EN").connect(rg, "1")
    c.net("VOUT").connect(q1, "3").connect(cout, "1")
    c.net("GND").connect(cout, "2")
    return c
'''

_USB_C_SINK_BASIC = '''
def build():
    c = Circuit("usb_c_sink_basic", description="USB-C 5V sink with CC pulldowns + bulk cap")
    j1 = c.add_part_from_db("J1", "usb_c_receptacle_hro", value="USB-C")
    rcc1 = c.add_part_from_db("R1", "resistor_0402", value="5.1k", role="usb_cc_rd")
    rcc2 = c.add_part_from_db("R2", "resistor_0402", value="5.1k", role="usb_cc_rd")
    cb = c.add_part_from_db("C1", "cap_0805_10u", value="10u")
    c.net("VBUS").connect(j1, "A4").connect(j1, "B4").connect(j1, "A9").connect(j1, "B9").connect(cb, "1")
    c.net("GND").connect(j1, "A1").connect(j1, "A12").connect(j1, "B1").connect(j1, "B12")
    c.net("GND").connect(rcc1, "2").connect(rcc2, "2").connect(cb, "2")
    c.net("CC1").connect(j1, "A5").connect(rcc1, "1")
    c.net("CC2").connect(j1, "B5").connect(rcc2, "1")
    return c
'''

_COST_CAPPED_SENSOR = '''
def build():
    c = Circuit("cost_capped_sensor", description="Lowest-cost I2C sensor breakout")
    u1 = c.add_part_from_db("U1", "i2c_sensor_generic")
    cb = c.add_part_from_db("C1", "cap_0402_100n", value="100n")
    rsda = c.add_part_from_db("R1", "resistor_0402", value="4.7k", role="i2c_pullup")
    rscl = c.add_part_from_db("R2", "resistor_0402", value="4.7k", role="i2c_pullup")
    c.net("+3V3").connect(u1, "1").connect(cb, "1").connect(rsda, "1").connect(rscl, "1")
    c.net("GND").connect(u1, "2").connect(cb, "2")
    c.net("SDA").connect(u1, "3").connect(rsda, "2")
    c.net("SCL").connect(u1, "4").connect(rscl, "2")
    return c
'''


_BUCK_3V3 = '''
def build():
    c = Circuit("buck_3v3", description="12V to 3.3V non-synchronous buck converter")
    u1 = c.add_part_from_db("U1", "buck_mp1584")
    cin = c.add_part_from_db("C1", "cap_0805_10u", value="10u")
    cout = c.add_part_from_db("C2", "cap_0805_10u", value="10u")
    l1 = c.add_part_from_db("L1", "inductor_10uh_power", value="10uH")
    d1 = c.add_part_from_db("D1", "diode_schottky_sma", value="SS34")
    rtop = c.add_part_from_db("R1", "resistor_0603", value="68k")
    rbot = c.add_part_from_db("R2", "resistor_0603", value="10k")
    # VIN: controller VIN + input cap + EN (always enabled)
    c.net("VIN").connect(u1, "1").connect(cin, "1").connect(u1, "5")
    # SW node: controller SW, inductor near end, catch diode cathode (pin1=K)
    c.net("SW").connect(u1, "2").connect(l1, "1").connect(d1, "1")
    # Output 3.3V rail: inductor far end, output cap, divider top
    c.net("+3V3").connect(l1, "2").connect(cout, "1").connect(rtop, "1")
    # Feedback: divider midpoint to FB
    c.net("FB").connect(u1, "4").connect(rtop, "2").connect(rbot, "1")
    # Ground: controller GND, input/output caps, catch diode anode (pin2=A), divider bottom
    c.net("GND").connect(u1, "3").connect(cin, "2").connect(cout, "2").connect(d1, "2").connect(rbot, "2")
    return c
'''

_BOOST_5V = '''
def build():
    c = Circuit("boost_5v", description="3.3V to 5V boost converter")
    u1 = c.add_part_from_db("U1", "boost_tps61023")
    cin = c.add_part_from_db("C1", "cap_0805_10u", value="10u")
    cout = c.add_part_from_db("C2", "cap_0805_10u", value="10u")
    l1 = c.add_part_from_db("L1", "inductor_4u7_power", value="4.7uH")
    d1 = c.add_part_from_db("D1", "diode_schottky_sma", value="SS34")
    rtop = c.add_part_from_db("R1", "resistor_0603", value="100k")
    rbot = c.add_part_from_db("R2", "resistor_0603", value="33k")
    # VIN: controller VIN + input cap + EN (always enabled)
    c.net("VIN").connect(u1, "5").connect(cin, "1").connect(u1, "4").connect(l1, "1")
    # SW node: controller SW, inductor far end, rectifier diode anode (pin2=A)
    c.net("SW").connect(u1, "1").connect(l1, "2").connect(d1, "2")
    # Output 5V rail: controller VOUT, rectifier cathode (pin1=K), output cap, divider top
    c.net("+5V").connect(u1, "6").connect(d1, "1").connect(cout, "1").connect(rtop, "1")
    # Feedback: divider midpoint to FB
    c.net("FB").connect(u1, "3").connect(rtop, "2").connect(rbot, "1")
    # Ground: controller GND, input/output caps, divider bottom
    c.net("GND").connect(u1, "2").connect(cin, "2").connect(cout, "2").connect(rbot, "2")
    return c
'''


EXAMPLE_PROGRAMS: dict[str, str] = {
    "led_resistor": _LED_RESISTOR.strip() + "\n",
    "ldo_3v3": _LDO_3V3.strip() + "\n",
    "usb_c_5v_led": _USB_C_5V_LED.strip() + "\n",
    "i2c_sensor_breakout": _I2C_SENSOR_BREAKOUT.strip() + "\n",
    "mcu_minimal": _MCU_MINIMAL.strip() + "\n",
    "led_blinky_tiny": _LED_BLINKY_TINY.strip() + "\n",
    "handsolder_led": _HANDSOLDER_LED.strip() + "\n",
    "ldo_3v3_lowcost": _LDO_3V3_LOWCOST.strip() + "\n",
    "reverse_polarity_protection": _REVERSE_POLARITY.strip() + "\n",
    "button_debounce": _BUTTON_DEBOUNCE.strip() + "\n",
    "resistor_divider": _RESISTOR_DIVIDER.strip() + "\n",
    "motor_driver_support": _MOTOR_DRIVER_SUPPORT.strip() + "\n",
    "ldo_3v3_tiny": _LDO_3V3_TINY.strip() + "\n",
    "ldo_3v3_highavail": _LDO_3V3_HIGHAVAIL.strip() + "\n",
    "ldo_3v3_highcurrent": _LDO_3V3_HIGHCURRENT.strip() + "\n",
    "decoupling_tiny": _DECOUPLING_TINY.strip() + "\n",
    "rc_lowpass_filter": _RC_LOWPASS_FILTER.strip() + "\n",
    "uart_header": _UART_HEADER.strip() + "\n",
    "load_switch_pmos": _LOAD_SWITCH_PMOS.strip() + "\n",
    "usb_c_sink_basic": _USB_C_SINK_BASIC.strip() + "\n",
    "cost_capped_sensor": _COST_CAPPED_SENSOR.strip() + "\n",
    "buck_3v3": _BUCK_3V3.strip() + "\n",
    "boost_5v": _BOOST_5V.strip() + "\n",
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
