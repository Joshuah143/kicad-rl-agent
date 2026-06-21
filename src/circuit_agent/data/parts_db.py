"""Parts database — curated part specs keyed by friendly names.

Tasks reference these keys in ``allowed_parts``; the builder's convenience
methods (``add_resistor``/``add_capacitor``/``add_led``/``add_part_from_db``)
pull sensible defaults (symbol, footprint, cost, availability, dimensions) from
here. ``resolve_part`` returns kwargs ready for ``Circuit.add_part``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from circuit_agent.dsl.schema import PackageType


@dataclass(frozen=True)
class PartSpec:
    """A curated catalog entry for a part."""

    key: str
    symbol: str
    footprint: Optional[str]
    value: Optional[str]
    package_type: PackageType
    unit_cost_usd: float
    availability_score: float
    package_dims_mm: Optional[tuple[float, float]]
    role: Optional[str] = None
    pin_aliases: dict = field(default_factory=dict)


def _spec(
    key: str,
    symbol: str,
    footprint: Optional[str],
    value: Optional[str],
    package_type: PackageType,
    unit_cost_usd: float,
    availability_score: float,
    dims: Optional[tuple[float, float]],
    role: Optional[str] = None,
) -> PartSpec:
    return PartSpec(
        key=key,
        symbol=symbol,
        footprint=footprint,
        value=value,
        package_type=package_type,
        unit_cost_usd=unit_cost_usd,
        availability_score=availability_score,
        package_dims_mm=dims,
        role=role,
    )


PARTS: dict[str, PartSpec] = {
    "resistor_0402": _spec(
        "resistor_0402", "Device:R", "Resistor_SMD:R_0402_1005Metric", None,
        PackageType.SMD, 0.0015, 0.97, (1.0, 0.5), role="resistor",
    ),
    "resistor_0603": _spec(
        "resistor_0603", "Device:R", "Resistor_SMD:R_0603_1608Metric", None,
        PackageType.SMD, 0.002, 0.99, (1.6, 0.8), role="resistor",
    ),
    "resistor_0805": _spec(
        "resistor_0805", "Device:R", "Resistor_SMD:R_0805_2012Metric", None,
        PackageType.SMD, 0.0025, 0.98, (2.0, 1.25), role="resistor",
    ),
    "led_0603": _spec(
        "led_0603", "Device:LED", "LED_SMD:LED_0603_1608Metric", "LED",
        PackageType.SMD, 0.04, 0.95, (1.6, 0.8), role="led",
    ),
    "led_0805": _spec(
        "led_0805", "Device:LED", "LED_SMD:LED_0805_2012Metric", "LED",
        PackageType.SMD, 0.045, 0.94, (2.0, 1.25), role="led",
    ),
    "cap_0603_100n": _spec(
        "cap_0603_100n", "Device:C", "Capacitor_SMD:C_0603_1608Metric", "100n",
        PackageType.SMD, 0.003, 0.99, (1.6, 0.8), role="cap",
    ),
    "cap_0805_1u": _spec(
        "cap_0805_1u", "Device:C", "Capacitor_SMD:C_0805_2012Metric", "1u",
        PackageType.SMD, 0.006, 0.97, (2.0, 1.25), role="cap",
    ),
    "cap_0805_10u": _spec(
        "cap_0805_10u", "Device:C", "Capacitor_SMD:C_0805_2012Metric", "10u",
        PackageType.SMD, 0.02, 0.96, (2.0, 1.25), role="cap",
    ),
    "usb_c_receptacle_hro": _spec(
        "usb_c_receptacle_hro", "Connector:USB_C_Receptacle_USB2.0",
        "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", "USB-C",
        PackageType.SMD, 0.55, 0.9, (9.0, 7.0), role="usb_c",
    ),
    "ldo_3v3_ap2112": _spec(
        "ldo_3v3_ap2112", "Regulator_Linear:AP2112K-3.3",
        "Package_TO_SOT_SMD:SOT-23-5", "AP2112K-3.3",
        PackageType.SMD, 0.18, 0.92, (2.9, 2.8), role="ldo",
    ),
    "test_point_smd": _spec(
        "test_point_smd", "Connector:TestPoint", "TestPoint:TestPoint_Pad_D1.0mm", "TP",
        PackageType.VIRTUAL, 0.0, 0.99, (1.0, 1.0),
    ),
    "mcu_rp2040": _spec(
        "mcu_rp2040", "MCU_RaspberryPi:RP2040",
        "Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm", "RP2040",
        PackageType.SMD, 0.80, 0.9, (7.0, 7.0),
    ),
    "mcu_esp32": _spec(
        "mcu_esp32", "RF_Module:ESP32-WROOM-32", "RF_Module:ESP32-WROOM-32", "ESP32-WROOM-32",
        PackageType.SMD, 2.2, 0.88, (18.0, 25.5),
    ),
    "mcu_stm32": _spec(
        "mcu_stm32", "MCU_ST_STM32F0:STM32F030F4Px",
        "Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm", "STM32F030F4",
        PackageType.SMD, 0.95, 0.85, (6.5, 6.4),
    ),
    "i2c_sensor_generic": _spec(
        "i2c_sensor_generic", "Sensor:GenericI2C", "Package_TO_SOT_SMD:SOT-23-5", "I2C-SENSOR",
        PackageType.SMD, 0.65, 0.86, (2.9, 2.8),
    ),
    "motor_driver_drv8833": _spec(
        "motor_driver_drv8833", "Driver_Motor:DRV8833",
        "Package_SO:TSSOP-16_4.4x5mm_P0.65mm", "DRV8833",
        PackageType.SMD, 0.90, 0.9, (5.0, 6.4),
    ),
    "resistor_tht": _spec(
        "resistor_tht", "Device:R",
        "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal", None,
        PackageType.THT, 0.01, 0.97, (10.16, 2.5), role="resistor",
    ),
    "led_tht": _spec(
        "led_tht", "Device:LED", "LED_THT:LED_D5.0mm", "LED",
        PackageType.THT, 0.05, 0.95, (5.0, 5.0), role="led",
    ),
    # ================================================================== #
    # Expanded catalog: multiple ALTERNATIVES per function so component
    # choice is a real lever. Differentiation principles:
    #   smaller package -> smaller area, cheaper, but 0402/fine-pitch is
    #   NOT hand-solderable; bigger/jellybean parts have higher availability;
    #   specialty parts: lower availability / higher cost.
    # ================================================================== #
    # --- Resistors ----------------------------------------------------- #
    "resistor_1206": _spec(
        "resistor_1206", "Device:R", "Resistor_SMD:R_1206_3216Metric", None,
        PackageType.SMD, 0.003, 0.97, (3.2, 1.6), role="resistor",
    ),
    # --- Ceramic capacitors ------------------------------------------- #
    "cap_0402_100n": _spec(
        "cap_0402_100n", "Device:C", "Capacitor_SMD:C_0402_1005Metric", "100n",
        PackageType.SMD, 0.0025, 0.97, (1.0, 0.5), role="cap",
    ),
    "cap_0603_1u": _spec(
        "cap_0603_1u", "Device:C", "Capacitor_SMD:C_0603_1608Metric", "1u",
        PackageType.SMD, 0.005, 0.98, (1.6, 0.8), role="cap",
    ),
    "cap_1206_10u": _spec(
        "cap_1206_10u", "Device:C", "Capacitor_SMD:C_1206_3216Metric", "10u",
        PackageType.SMD, 0.03, 0.96, (3.2, 1.6), role="cap",
    ),
    # --- Bulk capacitors ---------------------------------------------- #
    "cap_tant_10u": _spec(
        "cap_tant_10u", "Device:C_Polarized",
        "Capacitor_Tantalum_SMD:CP_EIA-3528-21_Kemet-B", "10u",
        PackageType.SMD, 0.18, 0.85, (3.5, 2.8), role="bulk_cap",
    ),
    "cap_elec_47u_smd": _spec(
        "cap_elec_47u_smd", "Device:C_Polarized",
        "Capacitor_SMD:CP_Elec_6.3x5.4", "47u",
        PackageType.SMD, 0.12, 0.9, (6.6, 6.6), role="bulk_cap",
    ),
    "cap_elec_100u_tht": _spec(
        "cap_elec_100u_tht", "Device:C_Polarized",
        "Capacitor_THT:CP_Radial_D8.0mm_P3.50mm", "100u",
        PackageType.THT, 0.10, 0.93, (8.0, 8.0), role="bulk_cap",
    ),
    # --- LEDs ---------------------------------------------------------- #
    "led_0402": _spec(
        "led_0402", "Device:LED", "LED_SMD:LED_0402_1005Metric", "LED",
        PackageType.SMD, 0.038, 0.93, (1.0, 0.5), role="led",
    ),
    "led_1206": _spec(
        "led_1206", "Device:LED", "LED_SMD:LED_1206_3216Metric", "LED",
        PackageType.SMD, 0.05, 0.95, (3.2, 1.6), role="led",
    ),
    "led_3mm_tht": _spec(
        "led_3mm_tht", "Device:LED", "LED_THT:LED_D3.0mm", "LED",
        PackageType.THT, 0.045, 0.96, (3.0, 3.0), role="led",
    ),
    "led_5mm_tht": _spec(
        "led_5mm_tht", "Device:LED", "LED_THT:LED_D5.0mm", "LED",
        PackageType.THT, 0.05, 0.96, (5.0, 5.0), role="led",
    ),
    # --- Diodes -------------------------------------------------------- #
    "diode_schottky_sod123": _spec(
        "diode_schottky_sod123", "Device:D_Schottky", "Diode_SMD:D_SOD-123", "B5819W",
        PackageType.SMD, 0.04, 0.94, (3.68, 1.6), role="diode",
    ),
    "diode_schottky_sma": _spec(
        "diode_schottky_sma", "Device:D_Schottky", "Diode_SMD:D_SMA", "SS34",
        PackageType.SMD, 0.08, 0.93, (5.2, 2.6), role="diode",
    ),
    "diode_1n4148_sod123": _spec(
        "diode_1n4148_sod123", "Device:D", "Diode_SMD:D_SOD-123", "1N4148W",
        PackageType.SMD, 0.02, 0.97, (3.68, 1.6), role="diode",
    ),
    "tvs_sod323": _spec(
        "tvs_sod323", "Device:D_TVS", "Diode_SMD:D_SOD-323", "PESD5V0",
        PackageType.SMD, 0.06, 0.9, (2.5, 1.25), role="tvs",
    ),
    # --- LDOs (3v3 alternatives that TRADE OFF) ----------------------- #
    "ldo_3v3_mcp1700": _spec(
        "ldo_3v3_mcp1700", "Regulator_Linear:MCP1700-3302_SOT23",
        "Package_TO_SOT_SMD:SOT-23", "MCP1700-3.3",
        PackageType.SMD, 0.30, 0.85, (2.9, 2.4), role="ldo",
    ),
    "ldo_3v3_xc6206": _spec(
        "ldo_3v3_xc6206", "Regulator_Linear:XC6206P332MR",
        "Package_TO_SOT_SMD:SOT-23", "XC6206P332",
        PackageType.SMD, 0.05, 0.97, (2.9, 2.4), role="ldo",
    ),
    "ldo_3v3_sot223": _spec(
        "ldo_3v3_sot223", "Regulator_Linear:AP1117-33",
        "Package_TO_SOT_SMD:SOT-223-3_TabPin2", "AP1117-3.3",
        PackageType.SMD, 0.40, 0.8, (6.5, 7.0), role="ldo",
    ),
    "ldo_5v_7805_tht": _spec(
        "ldo_5v_7805_tht", "Regulator_Linear:LM7805_TO220",
        "Package_TO_SOT_THT:TO-220-3_Vertical", "LM7805",
        PackageType.THT, 0.45, 0.9, (10.0, 4.5), role="ldo_5v",
    ),
    "ldo_1v8_xc6206": _spec(
        "ldo_1v8_xc6206", "Regulator_Linear:XC6206P182MR",
        "Package_TO_SOT_SMD:SOT-23", "XC6206P182",
        PackageType.SMD, 0.06, 0.95, (2.9, 2.4), role="ldo_1v8",
    ),
    # --- MOSFETs ------------------------------------------------------- #
    "mosfet_n_2n7002_sot23": _spec(
        "mosfet_n_2n7002_sot23", "Device:Q_NMOS_GSD", "Package_TO_SOT_SMD:SOT-23", "2N7002",
        PackageType.SMD, 0.03, 0.96, (2.9, 2.4), role="mosfet_n",
    ),
    "mosfet_n_ao3400_sot23": _spec(
        "mosfet_n_ao3400_sot23", "Device:Q_NMOS_GSD", "Package_TO_SOT_SMD:SOT-23", "AO3400",
        PackageType.SMD, 0.06, 0.93, (2.9, 2.4), role="mosfet_n",
    ),
    "mosfet_p_ao3401_sot23": _spec(
        "mosfet_p_ao3401_sot23", "Device:Q_PMOS_GSD", "Package_TO_SOT_SMD:SOT-23", "AO3401",
        PackageType.SMD, 0.07, 0.92, (2.9, 2.4), role="mosfet_p",
    ),
    "mosfet_n_dpak": _spec(
        "mosfet_n_dpak", "Device:Q_NMOS_GSD", "Package_TO_SOT_SMD:TO-252-2", "IRLR8259",
        PackageType.SMD, 0.35, 0.88, (6.6, 6.1), role="mosfet_n",
    ),
    # --- Connectors ---------------------------------------------------- #
    "usb_c_receptacle_gct": _spec(
        "usb_c_receptacle_gct", "Connector:USB_C_Receptacle_USB2.0_GCT",
        "Connector_USB:USB_C_Receptacle_GCT_USB4085", "USB-C",
        PackageType.SMD, 0.85, 0.85, (8.9, 6.5), role="usb_c",
    ),
    "usb_micro_b": _spec(
        "usb_micro_b", "Connector:USB_B_Micro",
        "Connector_USB:USB_Micro-B_Molex-105017-0001", "USB-Micro",
        PackageType.SMD, 0.35, 0.92, (7.5, 5.0), role="usb_micro",
    ),
    "header_1x4_254": _spec(
        "header_1x4_254", "Connector_Generic:Conn_01x04",
        "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", "1x4",
        PackageType.THT, 0.08, 0.98, (10.16, 2.54), role="header",
    ),
    "header_swd_2x5_127": _spec(
        "header_swd_2x5_127", "Connector_Generic:Conn_02x05_Odd_Even",
        "Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical", "SWD",
        PackageType.THT, 0.20, 0.9, (8.0, 5.0), role="header_swd",
    ),
    "screw_terminal_2_508": _spec(
        "screw_terminal_2_508", "Connector_Generic:Conn_01x02",
        "TerminalBlock:TerminalBlock_bornier-2_P5.08mm", "2P",
        PackageType.THT, 0.25, 0.94, (10.16, 8.0), role="terminal",
    ),
    "barrel_jack_dc": _spec(
        "barrel_jack_dc", "Connector:Barrel_Jack",
        "Connector_BarrelJack:BarrelJack_Horizontal", "DC-JACK",
        PackageType.THT, 0.40, 0.92, (14.5, 9.0), role="power_input",
    ),
    # --- Crystals / inductors / protection ----------------------------- #
    "crystal_12mhz_smd": _spec(
        "crystal_12mhz_smd", "Device:Crystal", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", "12MHz",
        PackageType.SMD, 0.20, 0.9, (3.2, 2.5), role="crystal",
    ),
    "crystal_32k768": _spec(
        "crystal_32k768", "Device:Crystal", "Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm", "32.768kHz",
        PackageType.SMD, 0.15, 0.9, (3.2, 1.5), role="crystal",
    ),
    "inductor_10uh_power": _spec(
        "inductor_10uh_power", "Device:L", "Inductor_SMD:L_Bourns-SRR1260", "10uH",
        PackageType.SMD, 0.30, 0.88, (12.5, 12.5), role="inductor",
    ),
    "ferrite_bead_0603": _spec(
        "ferrite_bead_0603", "Device:FerriteBead", "Inductor_SMD:L_0603_1608Metric", "FB",
        PackageType.SMD, 0.02, 0.95, (1.6, 0.8), role="ferrite",
    ),
    "polyfuse_1206": _spec(
        "polyfuse_1206", "Device:Polyfuse", "Resistor_SMD:R_1206_3216Metric_Polyfuse", "500mA",
        PackageType.SMD, 0.12, 0.91, (3.2, 1.6), role="fuse",
    ),
    # --- Buttons ------------------------------------------------------- #
    "button_smd_4p": _spec(
        "button_smd_4p", "Switch:SW_Push", "Button_Switch_SMD:SW_SPST_PTS645", "SW",
        PackageType.SMD, 0.08, 0.93, (4.5, 4.5), role="button",
    ),
    "button_tht_6mm": _spec(
        "button_tht_6mm", "Switch:SW_Push", "Button_Switch_THT:SW_PUSH_6mm", "SW",
        PackageType.THT, 0.06, 0.95, (6.0, 6.0), role="button",
    ),
    # --- ICs: flash / sensors / motor ---------------------------------- #
    "qspi_flash_w25q": _spec(
        "qspi_flash_w25q", "Memory_Flash:W25Q128JVS", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", "W25Q128",
        PackageType.SMD, 0.55, 0.88, (3.9, 4.9), role="flash",
    ),
    "i2c_sensor_bme280": _spec(
        "i2c_sensor_bme280", "Sensor:BME280", "Package_LGA:LGA-8_2.5x2.5mm_P0.65mm", "BME280",
        PackageType.SMD, 3.20, 0.8, (2.5, 2.5), role="sensor",
    ),
    "motor_driver_drv8871": _spec(
        "motor_driver_drv8871", "Driver_Motor:DRV8871",
        "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm_DRV8871", "DRV8871",
        PackageType.SMD, 1.20, 0.87, (3.9, 4.9), role="motor_driver",
    ),
    # --- Misc ---------------------------------------------------------- #
    "mounting_hole_m2": _spec(
        "mounting_hole_m2", "Mechanical:MountingHole", "MountingHole:MountingHole_2.2mm_M2", "M2",
        PackageType.VIRTUAL, 0.0, 0.99, (4.0, 4.0), role="mounting",
    ),
}


def get_part(key: str) -> Optional[PartSpec]:
    """Return the :class:`PartSpec` for ``key`` or ``None``."""
    return PARTS.get(key)


def resolve_part(key: str) -> dict:
    """Return ``Circuit.add_part`` kwargs for ``key`` (``{}`` if unknown).

    ``package_type`` is returned as its string value so it can be passed
    directly to the builder, which coerces it back to the enum.
    """
    spec = PARTS.get(key)
    if spec is None:
        return {}
    return {
        "symbol": spec.symbol,
        "footprint": spec.footprint,
        "value": spec.value,
        "package_type": spec.package_type.value,
        "unit_cost_usd": spec.unit_cost_usd,
        "availability_score": spec.availability_score,
        "package_dims_mm": spec.package_dims_mm,
        "role": spec.role,
    }


def all_parts() -> dict:
    """Return the full parts catalog."""
    return dict(PARTS)


def parts_by_role(role: str) -> list[str]:
    """Return the sorted catalog keys whose :attr:`PartSpec.role` equals ``role``.

    Lets task authors / tests discover the available *alternatives* for a
    function (e.g. ``parts_by_role("ldo")`` -> the 3.3V LDO family).
    """
    return sorted(key for key, spec in PARTS.items() if spec.role == role)


def parts_with_symbol(symbol: str) -> list[str]:
    """Return the sorted catalog keys that use the given KiCad ``symbol``."""
    return sorted(key for key, spec in PARTS.items() if spec.symbol == symbol)


def roles() -> list[str]:
    """Return the sorted set of distinct (non-None) roles in the catalog."""
    return sorted({spec.role for spec in PARTS.values() if spec.role is not None})
