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
    # --- additional power symbols --------------------------------------- #
    "power:+1V8": SymbolDef("power:+1V8", (_p("1", "+1V8", "power_in"),), None, "+1V8 rail"),
    "power:VM": SymbolDef("power:VM", (_p("1", "VM", "power_in"),), None, "Motor supply rail"),
    # --- inductor / ferrite / fuse (2-pin passives) --------------------- #
    "Device:L": SymbolDef(
        "Device:L", (_p("1", "~"), _p("2", "~")), "Inductor_SMD:L_Bourns-SRR1260", "Inductor"
    ),
    "Device:L_Small": SymbolDef(
        "Device:L_Small", (_p("1", "~"), _p("2", "~")), "Inductor_SMD:L_0603_1608Metric", "Inductor (small)"
    ),
    "Device:FerriteBead": SymbolDef(
        "Device:FerriteBead", (_p("1", "~"), _p("2", "~")), "Inductor_SMD:L_0603_1608Metric", "Ferrite bead"
    ),
    "Device:Polyfuse": SymbolDef(
        "Device:Polyfuse",
        (_p("1", "~"), _p("2", "~")),
        "Resistor_SMD:R_1206_3216Metric_Polyfuse",
        "Resettable polyfuse",
    ),
    # --- diodes (A/K passive) ------------------------------------------- #
    "Device:D_Schottky": SymbolDef(
        "Device:D_Schottky", (_p("1", "K"), _p("2", "A")), "Diode_SMD:D_SOD-123", "Schottky diode"
    ),
    "Device:D": SymbolDef(
        "Device:D", (_p("1", "K"), _p("2", "A")), "Diode_SMD:D_SOD-123", "Diode"
    ),
    "Device:D_TVS": SymbolDef(
        "Device:D_TVS", (_p("1", "A1"), _p("2", "A2")), "Diode_SMD:D_SOD-323", "Bidirectional TVS diode"
    ),
    # --- crystals (2-pin passive) --------------------------------------- #
    "Device:Crystal": SymbolDef(
        "Device:Crystal",
        (_p("1", "1"), _p("2", "2")),
        "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
        "Crystal resonator",
    ),
    "Device:Crystal_GND24": SymbolDef(
        "Device:Crystal_GND24",
        (_p("1", "1"), _p("2", "2"), _p("3", "GND"), _p("4", "GND")),
        "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
        "Crystal with grounded case",
    ),
    # --- MOSFETs (G input, D/S passive) --------------------------------- #
    "Device:Q_NMOS_GSD": SymbolDef(
        "Device:Q_NMOS_GSD",
        (_p("1", "G", "input"), _p("2", "S"), _p("3", "D")),
        "Package_TO_SOT_SMD:SOT-23",
        "N-channel MOSFET (G/S/D)",
    ),
    "Device:Q_PMOS_GSD": SymbolDef(
        "Device:Q_PMOS_GSD",
        (_p("1", "G", "input"), _p("2", "S"), _p("3", "D")),
        "Package_TO_SOT_SMD:SOT-23",
        "P-channel MOSFET (G/S/D)",
    ),
    # --- LDO regulators (VIN/GND/EN/VOUT) ------------------------------- #
    "Regulator_Linear:MCP1700-3302_SOT23": SymbolDef(
        "Regulator_Linear:MCP1700-3302_SOT23",
        (
            _p("1", "GND", "power_in"),
            _p("2", "VIN", "power_in"),
            _p("3", "VOUT", "power_out"),
        ),
        "Package_TO_SOT_SMD:SOT-23",
        "MCP1700 3.3V LDO (SOT-23)",
    ),
    "Regulator_Linear:XC6206P332MR": SymbolDef(
        "Regulator_Linear:XC6206P332MR",
        (
            _p("1", "VIN", "power_in"),
            _p("2", "GND", "power_in"),
            _p("3", "VOUT", "power_out"),
        ),
        "Package_TO_SOT_SMD:SOT-23",
        "XC6206 3.3V LDO (SOT-23)",
    ),
    "Regulator_Linear:XC6206P182MR": SymbolDef(
        "Regulator_Linear:XC6206P182MR",
        (
            _p("1", "VIN", "power_in"),
            _p("2", "GND", "power_in"),
            _p("3", "VOUT", "power_out"),
        ),
        "Package_TO_SOT_SMD:SOT-23",
        "XC6206 1.8V LDO (SOT-23)",
    ),
    "Regulator_Linear:AP1117-33": SymbolDef(
        "Regulator_Linear:AP1117-33",
        (
            _p("1", "GND", "power_in"),
            _p("2", "VOUT", "power_out"),
            _p("3", "VIN", "power_in"),
        ),
        "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        "AP1117-3.3 1A LDO (SOT-223)",
    ),
    "Regulator_Linear:LM7805_TO220": SymbolDef(
        "Regulator_Linear:LM7805_TO220",
        (
            _p("1", "VIN", "power_in"),
            _p("2", "GND", "power_in"),
            _p("3", "VOUT", "power_out"),
        ),
        "Package_TO_SOT_THT:TO-220-3_Vertical",
        "LM7805 5V regulator (TO-220)",
    ),
    # --- connectors ------------------------------------------------------ #
    "Connector:USB_C_Receptacle_USB2.0_GCT": SymbolDef(
        "Connector:USB_C_Receptacle_USB2.0_GCT",
        (
            _p("A1", "GND", "power_in"),
            _p("A4", "VBUS", "power_in"),
            _p("A5", "CC1", "bidirectional"),
            _p("A6", "D+", "bidirectional"),
            _p("A7", "D-", "bidirectional"),
            _p("A9", "VBUS", "power_in"),
            _p("A12", "GND", "power_in"),
            _p("B1", "GND", "power_in"),
            _p("B4", "VBUS", "power_in"),
            _p("B5", "CC2", "bidirectional"),
            _p("B6", "D+", "bidirectional"),
            _p("B7", "D-", "bidirectional"),
            _p("B9", "VBUS", "power_in"),
            _p("B12", "GND", "power_in"),
            _p("S1", "SHIELD", "passive"),
        ),
        "Connector_USB:USB_C_Receptacle_GCT_USB4085",
        "USB 2.0 Type-C receptacle (GCT)",
    ),
    "Connector:USB_B_Micro": SymbolDef(
        "Connector:USB_B_Micro",
        (
            _p("1", "VBUS", "power_in"),
            _p("2", "D-", "bidirectional"),
            _p("3", "D+", "bidirectional"),
            _p("4", "ID", "passive"),
            _p("5", "GND", "power_in"),
            _p("6", "SHIELD", "passive"),
        ),
        "Connector_USB:USB_Micro-B_Molex-105017-0001",
        "USB Micro-B receptacle",
    ),
    "Connector_Generic:Conn_01x04": SymbolDef(
        "Connector_Generic:Conn_01x04",
        (_p("1", "1"), _p("2", "2"), _p("3", "3"), _p("4", "4")),
        "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
        "1x4 pin header",
    ),
    "Connector_Generic:Conn_02x05_Odd_Even": SymbolDef(
        "Connector_Generic:Conn_02x05_Odd_Even",
        tuple(_p(str(i), str(i)) for i in range(1, 11)),
        "Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical",
        "2x5 1.27mm header (SWD)",
    ),
    "Connector_Generic:Conn_01x02": SymbolDef(
        "Connector_Generic:Conn_01x02",
        (_p("1", "1"), _p("2", "2")),
        "TerminalBlock:TerminalBlock_bornier-2_P5.08mm",
        "1x2 terminal/connector",
    ),
    "Connector:Barrel_Jack": SymbolDef(
        "Connector:Barrel_Jack",
        (_p("1", "VCC", "passive"), _p("2", "GND", "passive"), _p("3", "SW", "passive")),
        "Connector_BarrelJack:BarrelJack_Horizontal",
        "DC barrel jack",
    ),
    # --- buttons --------------------------------------------------------- #
    "Switch:SW_Push": SymbolDef(
        "Switch:SW_Push",
        (_p("1", "1"), _p("2", "2")),
        "Button_Switch_SMD:SW_SPST_PTS645",
        "Momentary push button",
    ),
    # --- ICs: flash / sensors ------------------------------------------- #
    "Memory_Flash:W25Q128JVS": SymbolDef(
        "Memory_Flash:W25Q128JVS",
        (
            _p("1", "CS", "input"),
            _p("2", "DO", "output"),
            _p("3", "WP", "input"),
            _p("4", "GND", "power_in"),
            _p("5", "DI", "input"),
            _p("6", "CLK", "input"),
            _p("7", "HOLD", "input"),
            _p("8", "VCC", "power_in"),
        ),
        "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        "W25Q QSPI flash (SOIC-8)",
    ),
    "Sensor:BME280": SymbolDef(
        "Sensor:BME280",
        (
            _p("1", "GND", "power_in"),
            _p("2", "CSB", "input"),
            _p("3", "SDI", "bidirectional"),
            _p("4", "SCK", "input"),
            _p("5", "SDO", "bidirectional"),
            _p("6", "VDDIO", "power_in"),
            _p("7", "GND", "power_in"),
            _p("8", "VDD", "power_in"),
        ),
        "Package_LGA:LGA-8_2.5x2.5mm_P0.65mm",
        "BME280 environmental sensor (LGA-8)",
    ),
    "Driver_Motor:DRV8871": SymbolDef(
        "Driver_Motor:DRV8871",
        (
            _p("1", "GND", "power_in"),
            _p("2", "IN1", "input"),
            _p("3", "IN2", "input"),
            _p("4", "VM", "power_in"),
            _p("5", "OUT1", "output"),
            _p("8", "OUT2", "output"),
        ),
        "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm_DRV8871",
        "DRV8871 single H-bridge motor driver",
    ),
    # --- misc ------------------------------------------------------------ #
    "Mechanical:MountingHole": SymbolDef(
        "Mechanical:MountingHole", (_p("1", "1"),), "MountingHole:MountingHole_2.2mm_M2", "Mounting hole"
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
