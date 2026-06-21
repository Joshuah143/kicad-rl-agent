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
}


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
