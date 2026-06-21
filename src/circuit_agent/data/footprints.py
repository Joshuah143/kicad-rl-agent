"""Static footprint catalog — physical dimensions and solderability.

Used by the package-size validator and the size component of the reward, and to
provide sensible defaults for the parts database. ``area_mm2`` is the product of
the two dimensions (a coarse bounding-box approximation).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from circuit_agent.dsl.schema import PackageType


@dataclass(frozen=True)
class FootprintDef:
    """A footprint definition with its dimensions and solderability."""

    fp_id: str
    package_type: PackageType
    dims_mm: tuple[float, float]
    area_mm2: float
    hand_solderable: bool
    size_class: Optional[str]


def _fp(
    fp_id: str,
    package_type: PackageType,
    dims: tuple[float, float],
    hand_solderable: bool,
    size_class: Optional[str],
) -> FootprintDef:
    return FootprintDef(
        fp_id=fp_id,
        package_type=package_type,
        dims_mm=dims,
        area_mm2=round(dims[0] * dims[1], 4),
        hand_solderable=hand_solderable,
        size_class=size_class,
    )


FOOTPRINTS: dict[str, FootprintDef] = {
    "Resistor_SMD:R_0402_1005Metric": _fp(
        "Resistor_SMD:R_0402_1005Metric", PackageType.SMD, (1.0, 0.5), False, "0402"
    ),
    "Resistor_SMD:R_0603_1608Metric": _fp(
        "Resistor_SMD:R_0603_1608Metric", PackageType.SMD, (1.6, 0.8), True, "0603"
    ),
    "Resistor_SMD:R_0805_2012Metric": _fp(
        "Resistor_SMD:R_0805_2012Metric", PackageType.SMD, (2.0, 1.25), True, "0805"
    ),
    "Capacitor_SMD:C_0402_1005Metric": _fp(
        "Capacitor_SMD:C_0402_1005Metric", PackageType.SMD, (1.0, 0.5), False, "0402"
    ),
    "Capacitor_SMD:C_0603_1608Metric": _fp(
        "Capacitor_SMD:C_0603_1608Metric", PackageType.SMD, (1.6, 0.8), True, "0603"
    ),
    "Capacitor_SMD:C_0805_2012Metric": _fp(
        "Capacitor_SMD:C_0805_2012Metric", PackageType.SMD, (2.0, 1.25), True, "0805"
    ),
    "LED_SMD:LED_0603_1608Metric": _fp(
        "LED_SMD:LED_0603_1608Metric", PackageType.SMD, (1.6, 0.8), True, "0603"
    ),
    "LED_SMD:LED_0805_2012Metric": _fp(
        "LED_SMD:LED_0805_2012Metric", PackageType.SMD, (2.0, 1.25), True, "0805"
    ),
    "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12": _fp(
        "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", PackageType.SMD, (9.0, 7.0), True, "usb_c"
    ),
    "Package_TO_SOT_SMD:SOT-23-5": _fp(
        "Package_TO_SOT_SMD:SOT-23-5", PackageType.SMD, (2.9, 2.8), True, "sot23"
    ),
    "Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm": _fp(
        "Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm", PackageType.SMD, (7.0, 7.0), False, "qfn56"
    ),
    "RF_Module:ESP32-WROOM-32": _fp(
        "RF_Module:ESP32-WROOM-32", PackageType.SMD, (18.0, 25.5), True, "module"
    ),
    "Package_SO:TSSOP-16_4.4x5mm_P0.65mm": _fp(
        "Package_SO:TSSOP-16_4.4x5mm_P0.65mm", PackageType.SMD, (5.0, 6.4), True, "tssop16"
    ),
    "Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm": _fp(
        "Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm", PackageType.SMD, (6.5, 6.4), True, "tssop20"
    ),
    "TestPoint:TestPoint_Pad_D1.0mm": _fp(
        "TestPoint:TestPoint_Pad_D1.0mm", PackageType.VIRTUAL, (1.0, 1.0), True, "testpoint"
    ),
    "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal": _fp(
        "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal",
        PackageType.THT,
        (10.16, 2.5),
        True,
        "tht_axial",
    ),
    "LED_THT:LED_D5.0mm": _fp(
        "LED_THT:LED_D5.0mm", PackageType.THT, (5.0, 5.0), True, "tht_led"
    ),
    # --- additional passives: resistors / capacitors / LEDs -------------- #
    "Resistor_SMD:R_1206_3216Metric": _fp(
        "Resistor_SMD:R_1206_3216Metric", PackageType.SMD, (3.2, 1.6), True, "1206"
    ),
    "Capacitor_SMD:C_1206_3216Metric": _fp(
        "Capacitor_SMD:C_1206_3216Metric", PackageType.SMD, (3.2, 1.6), True, "1206"
    ),
    "LED_SMD:LED_0402_1005Metric": _fp(
        "LED_SMD:LED_0402_1005Metric", PackageType.SMD, (1.0, 0.5), False, "0402"
    ),
    "LED_SMD:LED_1206_3216Metric": _fp(
        "LED_SMD:LED_1206_3216Metric", PackageType.SMD, (3.2, 1.6), True, "1206"
    ),
    "LED_THT:LED_D3.0mm": _fp(
        "LED_THT:LED_D3.0mm", PackageType.THT, (3.0, 3.0), True, "tht_led"
    ),
    # --- bulk / electrolytic / tantalum caps ----------------------------- #
    "Capacitor_Tantalum_SMD:CP_EIA-3528-21_Kemet-B": _fp(
        "Capacitor_Tantalum_SMD:CP_EIA-3528-21_Kemet-B",
        PackageType.SMD, (3.5, 2.8), True, "tant_b",
    ),
    "Capacitor_SMD:CP_Elec_6.3x5.4": _fp(
        "Capacitor_SMD:CP_Elec_6.3x5.4", PackageType.SMD, (6.6, 6.6), True, "elec_smd"
    ),
    "Capacitor_THT:CP_Radial_D8.0mm_P3.50mm": _fp(
        "Capacitor_THT:CP_Radial_D8.0mm_P3.50mm",
        PackageType.THT, (8.0, 8.0), True, "tht_radial",
    ),
    # --- diodes ---------------------------------------------------------- #
    "Diode_SMD:D_SOD-123": _fp(
        "Diode_SMD:D_SOD-123", PackageType.SMD, (3.68, 1.6), True, "sod123"
    ),
    "Diode_SMD:D_SMA": _fp(
        "Diode_SMD:D_SMA", PackageType.SMD, (5.2, 2.6), True, "sma"
    ),
    "Diode_SMD:D_SOD-323": _fp(
        "Diode_SMD:D_SOD-323", PackageType.SMD, (2.5, 1.25), True, "sod323"
    ),
    # --- transistor / regulator packages --------------------------------- #
    "Package_TO_SOT_SMD:SOT-23": _fp(
        "Package_TO_SOT_SMD:SOT-23", PackageType.SMD, (2.9, 2.4), True, "sot23"
    ),
    "Package_TO_SOT_SMD:SOT-223-3_TabPin2": _fp(
        "Package_TO_SOT_SMD:SOT-223-3_TabPin2", PackageType.SMD, (6.5, 7.0), True, "sot223"
    ),
    "Package_TO_SOT_SMD:SOT-23-6": _fp(
        "Package_TO_SOT_SMD:SOT-23-6", PackageType.SMD, (2.9, 2.8), True, "sot23-6"
    ),
    "Package_TO_SOT_THT:TO-220-5_Vertical": _fp(
        "Package_TO_SOT_THT:TO-220-5_Vertical", PackageType.THT, (10.0, 4.5), True, "to220-5"
    ),
    "Package_TO_SOT_SMD:TO-252-2": _fp(
        "Package_TO_SOT_SMD:TO-252-2", PackageType.SMD, (6.6, 6.1), True, "dpak"
    ),
    "Package_TO_SOT_THT:TO-220-3_Vertical": _fp(
        "Package_TO_SOT_THT:TO-220-3_Vertical", PackageType.THT, (10.0, 4.5), True, "to220"
    ),
    # --- connectors ------------------------------------------------------ #
    "Connector_USB:USB_C_Receptacle_GCT_USB4085": _fp(
        "Connector_USB:USB_C_Receptacle_GCT_USB4085", PackageType.SMD, (8.9, 6.5), True, "usb_c"
    ),
    "Connector_USB:USB_Micro-B_Molex-105017-0001": _fp(
        "Connector_USB:USB_Micro-B_Molex-105017-0001", PackageType.SMD, (7.5, 5.0), True, "usb_micro"
    ),
    "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical": _fp(
        "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
        PackageType.THT, (10.16, 2.54), True, "tht_header",
    ),
    "Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical": _fp(
        "Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical",
        PackageType.THT, (8.0, 5.0), True, "swd_header",
    ),
    "TerminalBlock:TerminalBlock_bornier-2_P5.08mm": _fp(
        "TerminalBlock:TerminalBlock_bornier-2_P5.08mm",
        PackageType.THT, (10.16, 8.0), True, "screw_terminal",
    ),
    "Connector_BarrelJack:BarrelJack_Horizontal": _fp(
        "Connector_BarrelJack:BarrelJack_Horizontal",
        PackageType.THT, (14.5, 9.0), True, "barrel_jack",
    ),
    # --- crystals / inductors / protection ------------------------------- #
    "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm": _fp(
        "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", PackageType.SMD, (3.2, 2.5), True, "crystal_smd"
    ),
    "Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm": _fp(
        "Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm", PackageType.SMD, (3.2, 1.5), True, "crystal_smd"
    ),
    "Inductor_SMD:L_Bourns-SRR1260": _fp(
        "Inductor_SMD:L_Bourns-SRR1260", PackageType.SMD, (12.5, 12.5), True, "power_inductor"
    ),
    "Inductor_SMD:L_0603_1608Metric": _fp(
        "Inductor_SMD:L_0603_1608Metric", PackageType.SMD, (1.6, 0.8), True, "0603"
    ),
    # --- power inductors for switching converters (differentiated sizes) -- #
    "Inductor_SMD:L_Bourns-SRR1210A": _fp(
        "Inductor_SMD:L_Bourns-SRR1210A", PackageType.SMD, (12.0, 12.0), True, "power_inductor"
    ),
    "Inductor_SMD:L_Taiyo-Yuden_NR-50xx": _fp(
        "Inductor_SMD:L_Taiyo-Yuden_NR-50xx", PackageType.SMD, (5.2, 5.2), True, "power_inductor"
    ),
    "Resistor_SMD:R_1206_3216Metric_Polyfuse": _fp(
        "Resistor_SMD:R_1206_3216Metric_Polyfuse", PackageType.SMD, (3.2, 1.6), True, "1206"
    ),
    # --- buttons --------------------------------------------------------- #
    "Button_Switch_SMD:SW_SPST_PTS645": _fp(
        "Button_Switch_SMD:SW_SPST_PTS645", PackageType.SMD, (4.5, 4.5), True, "button_smd"
    ),
    "Button_Switch_THT:SW_PUSH_6mm": _fp(
        "Button_Switch_THT:SW_PUSH_6mm", PackageType.THT, (6.0, 6.0), True, "button_tht"
    ),
    # --- ICs: flash / sensors / motor drivers ---------------------------- #
    "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm": _fp(
        "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", PackageType.SMD, (3.9, 4.9), True, "soic8"
    ),
    "Package_LGA:LGA-8_2.5x2.5mm_P0.65mm": _fp(
        "Package_LGA:LGA-8_2.5x2.5mm_P0.65mm", PackageType.SMD, (2.5, 2.5), False, "lga8"
    ),
    "Package_SO:HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm": _fp(
        "Package_SO:HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm",
        PackageType.SMD, (4.4, 5.0), True, "htssop16",
    ),
    "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm_DRV8871": _fp(
        "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm_DRV8871",
        PackageType.SMD, (3.9, 4.9), True, "soic8",
    ),
    # --- misc ------------------------------------------------------------ #
    "MountingHole:MountingHole_2.2mm_M2": _fp(
        "MountingHole:MountingHole_2.2mm_M2", PackageType.VIRTUAL, (4.0, 4.0), True, "mounting_hole"
    ),
}


# Ordering of SMD chip size classes from finest to coarsest. THT is treated as
# coarser than every SMD chip class for hand-solderability comparisons.
_SIZE_CLASS_ORDER: dict[str, int] = {"0402": 0, "0603": 1, "0805": 2, "1206": 3}


def size_class_rank(size_class: Optional[str]) -> Optional[int]:
    """Return an ordinal rank for a chip size class (smaller = finer pitch).

    Returns ``None`` for non-chip size classes (ICs, connectors, THT, etc.),
    which the hand-solderability comparison treats as "not finer than" any
    required minimum (i.e. they never trip the min_hand_solderable penalty by
    class alone — solderability is governed by ``hand_solderable`` instead).
    """
    if size_class is None:
        return None
    return _SIZE_CLASS_ORDER.get(size_class)


def get_footprint(fp_id: str) -> Optional[FootprintDef]:
    """Return the :class:`FootprintDef` for ``fp_id`` or ``None``."""
    return FOOTPRINTS.get(fp_id)


def footprint_area(fp_id: str) -> Optional[float]:
    """Return the area (mm^2) for ``fp_id`` or ``None`` if unknown."""
    fp = FOOTPRINTS.get(fp_id)
    return fp.area_mm2 if fp else None


def has_footprint(fp_id: str) -> bool:
    """Return ``True`` if ``fp_id`` is in the catalog."""
    return fp_id in FOOTPRINTS
