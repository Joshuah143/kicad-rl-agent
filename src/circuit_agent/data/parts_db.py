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
        PackageType.SMD, 0.0015, 0.97, (1.0, 0.5),
    ),
    "resistor_0603": _spec(
        "resistor_0603", "Device:R", "Resistor_SMD:R_0603_1608Metric", None,
        PackageType.SMD, 0.002, 0.99, (1.6, 0.8),
    ),
    "resistor_0805": _spec(
        "resistor_0805", "Device:R", "Resistor_SMD:R_0805_2012Metric", None,
        PackageType.SMD, 0.0025, 0.98, (2.0, 1.25),
    ),
    "led_0603": _spec(
        "led_0603", "Device:LED", "LED_SMD:LED_0603_1608Metric", "LED",
        PackageType.SMD, 0.04, 0.95, (1.6, 0.8),
    ),
    "led_0805": _spec(
        "led_0805", "Device:LED", "LED_SMD:LED_0805_2012Metric", "LED",
        PackageType.SMD, 0.045, 0.94, (2.0, 1.25),
    ),
    "cap_0603_100n": _spec(
        "cap_0603_100n", "Device:C", "Capacitor_SMD:C_0603_1608Metric", "100n",
        PackageType.SMD, 0.003, 0.99, (1.6, 0.8),
    ),
    "cap_0805_1u": _spec(
        "cap_0805_1u", "Device:C", "Capacitor_SMD:C_0805_2012Metric", "1u",
        PackageType.SMD, 0.006, 0.97, (2.0, 1.25),
    ),
    "cap_0805_10u": _spec(
        "cap_0805_10u", "Device:C", "Capacitor_SMD:C_0805_2012Metric", "10u",
        PackageType.SMD, 0.02, 0.96, (2.0, 1.25),
    ),
    "usb_c_receptacle_hro": _spec(
        "usb_c_receptacle_hro", "Connector:USB_C_Receptacle_USB2.0",
        "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", "USB-C",
        PackageType.SMD, 0.55, 0.9, (9.0, 7.0),
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
        PackageType.THT, 0.01, 0.97, (10.16, 2.5),
    ),
    "led_tht": _spec(
        "led_tht", "Device:LED", "LED_THT:LED_D5.0mm", "LED",
        PackageType.THT, 0.05, 0.95, (5.0, 5.0),
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
