"""Static symbol catalog — pin maps for the KiCad symbols we support.

Used by the validators (to verify referenced pins exist and to classify power
pins) and by the KiCad compiler (to emit generic rectangular symbols). The
catalog is intentionally a *subset* of the real KiCad libraries: enough to make
the supported reference circuits resolve.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PinDef:
    """A single pin on a symbol."""

    number: str
    name: str
    etype: str  # passive|power_in|power_out|input|output|bidirectional|no_connect|unspecified


@dataclass(frozen=True)
class SymbolDef:
    """A symbol definition: its lib id, pins and a default footprint."""

    lib_id: str
    pins: tuple[PinDef, ...]
    default_footprint: Optional[str]
    description: str


def _p(number: str, name: str, etype: str = "passive") -> PinDef:
    return PinDef(number=number, name=name, etype=etype)


SYMBOLS: dict[str, SymbolDef] = {
    "Device:R": SymbolDef(
        "Device:R", (_p("1", "~"), _p("2", "~")), "Resistor_SMD:R_0603_1608Metric", "Resistor"
    ),
    "Device:R_Small": SymbolDef(
        "Device:R_Small", (_p("1", "~"), _p("2", "~")), "Resistor_SMD:R_0603_1608Metric", "Resistor (small)"
    ),
    "Device:C": SymbolDef(
        "Device:C", (_p("1", "~"), _p("2", "~")), "Capacitor_SMD:C_0603_1608Metric", "Capacitor"
    ),
    "Device:C_Small": SymbolDef(
        "Device:C_Small", (_p("1", "~"), _p("2", "~")), "Capacitor_SMD:C_0603_1608Metric", "Capacitor (small)"
    ),
    "Device:C_Polarized": SymbolDef(
        "Device:C_Polarized", (_p("1", "+"), _p("2", "-")), "Capacitor_SMD:C_0805_2012Metric", "Polarized capacitor"
    ),
    "Device:LED": SymbolDef(
        "Device:LED", (_p("A", "A"), _p("K", "K")), "LED_SMD:LED_0603_1608Metric", "Light-emitting diode"
    ),
    "Connector:TestPoint": SymbolDef(
        "Connector:TestPoint", (_p("1", "1"),), "TestPoint:TestPoint_Pad_D1.0mm", "Test point"
    ),
    "power:GND": SymbolDef("power:GND", (_p("1", "GND", "power_in"),), None, "Ground"),
    "power:+5V": SymbolDef("power:+5V", (_p("1", "+5V", "power_in"),), None, "+5V rail"),
    "power:+3V3": SymbolDef("power:+3V3", (_p("1", "+3V3", "power_in"),), None, "+3V3 rail"),
    "power:VBUS": SymbolDef("power:VBUS", (_p("1", "VBUS", "power_in"),), None, "VBUS rail"),
    "power:PWR_FLAG": SymbolDef("power:PWR_FLAG", (_p("1", "pwr", "power_out"),), None, "Power flag"),
    "Connector:USB_C_Receptacle_USB2.0": SymbolDef(
        "Connector:USB_C_Receptacle_USB2.0",
        (
            _p("A1", "GND", "power_in"),
            _p("A4", "VBUS", "power_in"),
            _p("A5", "CC1", "bidirectional"),
            _p("A6", "D+", "bidirectional"),
            _p("A7", "D-", "bidirectional"),
            _p("A8", "SBU1", "bidirectional"),
            _p("A9", "VBUS", "power_in"),
            _p("A12", "GND", "power_in"),
            _p("B1", "GND", "power_in"),
            _p("B4", "VBUS", "power_in"),
            _p("B5", "CC2", "bidirectional"),
            _p("B6", "D+", "bidirectional"),
            _p("B7", "D-", "bidirectional"),
            _p("B8", "SBU2", "bidirectional"),
            _p("B9", "VBUS", "power_in"),
            _p("B12", "GND", "power_in"),
            _p("S1", "SHIELD", "passive"),
        ),
        "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
        "USB 2.0 Type-C receptacle",
    ),
    "Regulator_Linear:AP2112K-3.3": SymbolDef(
        "Regulator_Linear:AP2112K-3.3",
        (
            _p("1", "VIN", "power_in"),
            _p("2", "GND", "power_in"),
            _p("3", "EN", "input"),
            _p("4", "NC", "no_connect"),
            _p("5", "VOUT", "power_out"),
        ),
        "Package_TO_SOT_SMD:SOT-23-5",
        "AP2112K-3.3 LDO regulator",
    ),
    "MCU_RaspberryPi:RP2040": SymbolDef(
        "MCU_RaspberryPi:RP2040",
        (
            _p("1", "IOVDD", "power_in"),
            _p("10", "DVDD", "power_in"),
            _p("19", "USB_DM", "bidirectional"),
            _p("20", "USB_DP", "bidirectional"),
            _p("21", "GND", "power_in"),
            _p("44", "QSPI_SCLK", "bidirectional"),
            _p("45", "QSPI_SD0", "bidirectional"),
            _p("56", "GPIO0", "bidirectional"),
        ),
        "Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm",
        "RP2040 microcontroller",
    ),
    "RF_Module:ESP32-WROOM-32": SymbolDef(
        "RF_Module:ESP32-WROOM-32",
        (
            _p("2", "3V3", "power_in"),
            _p("1", "GND", "power_in"),
            _p("3", "EN", "input"),
            _p("25", "IO0", "bidirectional"),
            _p("34", "TXD0", "bidirectional"),
            _p("35", "RXD0", "bidirectional"),
        ),
        "RF_Module:ESP32-WROOM-32",
        "ESP32-WROOM-32 module",
    ),
    "MCU_ST_STM32F0:STM32F030F4Px": SymbolDef(
        "MCU_ST_STM32F0:STM32F030F4Px",
        (
            _p("16", "VDD", "power_in"),
            _p("15", "VSS", "power_in"),
            _p("4", "NRST", "input"),
            _p("1", "BOOT0", "input"),
            _p("6", "PA0", "bidirectional"),
            _p("7", "PA1", "bidirectional"),
        ),
        "Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm",
        "STM32F030F4 microcontroller",
    ),
    "Sensor:GenericI2C": SymbolDef(
        "Sensor:GenericI2C",
        (
            _p("1", "VDD", "power_in"),
            _p("2", "GND", "power_in"),
            _p("3", "SDA", "bidirectional"),
            _p("4", "SCL", "input"),
            _p("5", "ADDR", "input"),
        ),
        "Package_TO_SOT_SMD:SOT-23-5",
        "Generic I2C sensor",
    ),
    "Driver_Motor:DRV8833": SymbolDef(
        "Driver_Motor:DRV8833",
        (
            _p("1", "VM", "power_in"),
            _p("9", "GND", "power_in"),
            _p("2", "AIN1", "input"),
            _p("3", "AIN2", "input"),
            _p("4", "BIN1", "input"),
            _p("5", "BIN2", "input"),
            _p("15", "AOUT1", "output"),
            _p("16", "AOUT2", "output"),
            _p("11", "BOUT1", "output"),
            _p("12", "BOUT2", "output"),
            _p("8", "nSLEEP", "input"),
        ),
        "Package_SO:TSSOP-16_4.4x5mm_P0.65mm",
        "DRV8833 dual H-bridge motor driver",
    ),
}


def get_symbol(lib_id: str) -> Optional[SymbolDef]:
    """Return the :class:`SymbolDef` for ``lib_id`` or ``None`` if unknown."""
    return SYMBOLS.get(lib_id)


def symbol_pins(lib_id: str) -> tuple[PinDef, ...]:
    """Return the pins for ``lib_id`` (empty tuple if unknown)."""
    sym = SYMBOLS.get(lib_id)
    return sym.pins if sym else ()


def pin_numbers(lib_id: str) -> set[str]:
    """Return the set of pin numbers/names for ``lib_id`` (empty if unknown)."""
    return {p.number for p in symbol_pins(lib_id)}


def has_symbol(lib_id: str) -> bool:
    """Return ``True`` if ``lib_id`` is in the catalog."""
    return lib_id in SYMBOLS
