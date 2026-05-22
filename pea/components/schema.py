"""
Normalized component schema for PEA.

Defines dataclasses for MOSFETs, diodes, and capacitors with the fields
most relevant to power converter design.  The schema is intentionally
minimal — it captures what the calculators and agent need for automated
component selection, not a full datasheet.

Design pattern borrowed from:
    upb-lea/transistordatabase — unified transistor records, export to
    simulators, JSON exchange, workspace operating-point workflow.
    (GPL-3.0; schema ideas only, no code copied.)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class MOSFET:
    """N-channel power MOSFET record."""

    part_number: str
    manufacturer: str = ""
    vds_max_V: float = 0
    id_max_A: float = 0
    rds_on_mohm: float = 0
    qg_total_nC: float = 0
    qgd_nC: float = 0
    coss_pF: float = 0
    vgs_th_V: float = 0
    package: str = ""
    technology: str = ""  # e.g. "Si", "GaN", "SiC"
    spice_model: str = ""
    datasheet_url: str = ""
    tags: list[str] = field(default_factory=list)
    unit_cost_usd: float = 0
    package_volume_mm3: float = 0
    thermal_resistance_C_per_W: float = 0


@dataclass
class Diode:
    """Power diode / Schottky / SiC diode record."""

    part_number: str
    manufacturer: str = ""
    vr_max_V: float = 0
    if_max_A: float = 0
    vf_typ_V: float = 0
    trr_ns: float = 0
    diode_type: str = ""  # "Schottky", "SiC", "Ultrafast", "Standard"
    package: str = ""
    spice_model: str = ""
    datasheet_url: str = ""
    tags: list[str] = field(default_factory=list)
    unit_cost_usd: float = 0
    package_volume_mm3: float = 0
    thermal_resistance_C_per_W: float = 0


@dataclass
class Capacitor:
    """Power capacitor record (output / input / bus)."""

    part_number: str
    manufacturer: str = ""
    capacitance_uF: float = 0
    voltage_rating_V: float = 0
    esr_mohm: float = 0
    ripple_current_A: float = 0
    cap_type: str = ""  # "MLCC", "Electrolytic", "Polymer", "Film"
    package: str = ""
    datasheet_url: str = ""
    tags: list[str] = field(default_factory=list)
    unit_cost_usd: float = 0
    package_volume_mm3: float = 0


# ── Reference component library ─────────────────────────────────────────

REFERENCE_MOSFETS: list[MOSFET] = [
    MOSFET("BSC0902NS", "Infineon", 30, 71, 2.9, 29, 5.7, 680, 1.7, "TDSON-8", "Si"),
    MOSFET("BSC010N04LS", "Infineon", 40, 100, 1.0, 63, 10, 1400, 2.0, "TDSON-8", "Si"),
    MOSFET("IRFB4110PBF", "Infineon", 100, 180, 3.7, 150, 30, 3800, 4.0, "TO-220", "Si"),
    MOSFET("IPB072N15N3G", "Infineon", 150, 50, 7.2, 82, 20, 1200, 3.0, "TO-263", "Si"),
    MOSFET("STL160NS3LLH7", "ST", 30, 120, 1.5, 30, 4.5, 560, 1.3, "PowerFLAT-8", "Si"),
    MOSFET("EPC2045", "EPC", 100, 16, 7.0, 6.4, 1.4, 135, 1.4, "BGA", "GaN"),
    MOSFET("GS66508T", "GaN Systems", 650, 30, 50, 5.8, 1.8, 130, 1.7, "GaNPX", "GaN"),
    MOSFET("C3M0065090D", "Wolfspeed", 900, 36, 65, 30, 8, 90, 2.6, "TO-247", "SiC"),
    MOSFET("C3M0025065D", "Wolfspeed", 650, 60, 25, 58, 14, 180, 3.0, "TO-247", "SiC"),
    MOSFET("SCT3060AL", "ROHM", 650, 39, 60, 37, 11, 130, 3.3, "TO-247N", "SiC"),
]

REFERENCE_DIODES: list[Diode] = [
    Diode("SS34", "Vishay", 40, 3, 0.45, 0, "Schottky", "SMA"),
    Diode("SS54", "Vishay", 40, 5, 0.5, 0, "Schottky", "SMC"),
    Diode("MBR20100CT", "ON Semi", 100, 20, 0.7, 0, "Schottky", "TO-220"),
    Diode("ES2D", "Fairchild", 200, 2, 0.95, 20, "Ultrafast", "SMB"),
    Diode("C4D10120A", "Wolfspeed", 1200, 10, 1.5, 0, "SiC", "TO-220"),
    Diode("C3D10065A", "Wolfspeed", 650, 10, 1.35, 0, "SiC", "TO-220"),
    Diode("STPSC6H065", "ST", 650, 6, 1.35, 0, "SiC", "DPAK"),
]

REFERENCE_CAPACITORS: list[Capacitor] = [
    Capacitor("GRM31CR71E106KA12", "Murata", 10, 25, 3, 3, "MLCC", "1206"),
    Capacitor("GRM32ER71E226KE15", "Murata", 22, 25, 3, 4, "MLCC", "1210"),
    Capacitor("CL31B106KAHNNNE", "Samsung", 10, 25, 5, 3, "MLCC", "1206"),
    Capacitor("EEH-ZA1V101P", "Panasonic", 100, 35, 18, 2, "Polymer", "8x10"),
    Capacitor("UPM1H101MHD", "Nichicon", 100, 50, 30, 1.5, "Electrolytic", "10x12.5"),
    Capacitor("ECW-F4105JA", "Panasonic", 1, 400, 5, 2, "Film", "Box"),
    Capacitor("B32523Q6105K", "EPCOS/TDK", 1, 400, 8, 1.5, "Film", "Box"),
]


_PACKAGE_VOLUME_MM3 = {
    "TDSON-8": 35,
    "PowerFLAT-8": 30,
    "BGA": 18,
    "GaNPX": 90,
    "TO-220": 1250,
    "TO-247": 2600,
    "TO-247N": 2600,
    "TO-263": 820,
    "DPAK": 260,
    "SMA": 70,
    "SMB": 120,
    "SMC": 220,
    "1206": 8,
    "1210": 13,
    "8x10": 500,
    "10x12.5": 980,
    "Box": 900,
}

_TECH_COST_USD = {
    "Si": 0.85,
    "GaN": 4.5,
    "SiC": 6.0,
}


def _with_estimated_component_metadata() -> None:
    """Fill cost/volume fields for built-in records without changing call sites."""
    for m in REFERENCE_MOSFETS:
        if not m.package_volume_mm3:
            m.package_volume_mm3 = _PACKAGE_VOLUME_MM3.get(m.package, 250)
        if not m.unit_cost_usd:
            voltage_factor = 1.0 + max(m.vds_max_V - 100, 0) / 1000
            current_factor = 1.0 + m.id_max_A / 200
            m.unit_cost_usd = round(_TECH_COST_USD.get(m.technology, 1.0) * voltage_factor * current_factor, 2)
        if not m.thermal_resistance_C_per_W:
            m.thermal_resistance_C_per_W = 45 if "TO-247" in m.package else 65
    for d in REFERENCE_DIODES:
        if not d.package_volume_mm3:
            d.package_volume_mm3 = _PACKAGE_VOLUME_MM3.get(d.package, 160)
        if not d.unit_cost_usd:
            type_factor = 2.5 if d.diode_type == "SiC" else 1.0
            d.unit_cost_usd = round(type_factor * (0.25 + d.vr_max_V / 2500 + d.if_max_A / 80), 2)
        if not d.thermal_resistance_C_per_W:
            d.thermal_resistance_C_per_W = 55
    for c in REFERENCE_CAPACITORS:
        if not c.package_volume_mm3:
            c.package_volume_mm3 = _PACKAGE_VOLUME_MM3.get(c.package, max(12, c.capacitance_uF * 12))
        if not c.unit_cost_usd:
            type_factor = {"MLCC": 0.18, "Polymer": 0.6, "Electrolytic": 0.35, "Film": 0.75}.get(c.cap_type, 0.3)
            c.unit_cost_usd = round(type_factor * (1 + c.voltage_rating_V / 200 + c.capacitance_uF / 220), 2)


_with_estimated_component_metadata()


def search_mosfets(
    vds_min_V: float = 0,
    id_min_A: float = 0,
    rds_max_mohm: float = 1e6,
    technology: str = "",
) -> list[dict]:
    """Filter reference MOSFETs by operating-point requirements."""
    results = []
    for m in REFERENCE_MOSFETS:
        if m.vds_max_V < vds_min_V:
            continue
        if m.id_max_A < id_min_A:
            continue
        if m.rds_on_mohm > rds_max_mohm:
            continue
        if technology and m.technology.lower() != technology.lower():
            continue
        results.append(asdict(m))
    return results


def search_diodes(
    vr_min_V: float = 0,
    if_min_A: float = 0,
    diode_type: str = "",
) -> list[dict]:
    """Filter reference diodes by voltage and current."""
    results = []
    for d in REFERENCE_DIODES:
        if d.vr_max_V < vr_min_V:
            continue
        if d.if_max_A < if_min_A:
            continue
        if diode_type and d.diode_type.lower() != diode_type.lower():
            continue
        results.append(asdict(d))
    return results


def search_capacitors(
    capacitance_min_uF: float = 0,
    voltage_min_V: float = 0,
    cap_type: str = "",
) -> list[dict]:
    """Filter reference capacitors."""
    results = []
    for c in REFERENCE_CAPACITORS:
        if c.capacitance_uF < capacitance_min_uF:
            continue
        if c.voltage_rating_V < voltage_min_V:
            continue
        if cap_type and c.cap_type.lower() != cap_type.lower():
            continue
        results.append(asdict(c))
    return results


def recommend_components(v_in: float, v_out: float, i_out: float) -> dict:
    """Auto-recommend components for a converter design point."""
    v_sw = max(v_in, v_out) * 1.5
    mosfets = search_mosfets(vds_min_V=v_sw, id_min_A=i_out * 1.5)
    diodes = search_diodes(vr_min_V=v_sw, if_min_A=i_out)
    caps = search_capacitors(voltage_min_V=v_out * 1.5)

    return {
        "operating_point": {
            "V_switch_min": round(v_sw, 1),
            "I_switch_min": round(i_out * 1.5, 1),
        },
        "recommended_mosfets": mosfets[:3],
        "recommended_diodes": diodes[:3],
        "recommended_output_caps": caps[:3],
        "notes": (
            "Components filtered from reference library. Verify with full "
            "datasheet for thermal, package, and availability constraints."
        ),
    }


def load_spice_catalog(catalog_path: str | Path | None = None) -> list[dict]:
    """
    Load the SPICE JSON catalog if available.

    Falls back to an empty list when the file does not exist (e.g. in CI
    or minimal installs).
    """
    if catalog_path is None:
        catalog_path = Path(__file__).resolve().parents[2] / "data" / "spice_models_json" / "ui_catalog.json"
    else:
        catalog_path = Path(catalog_path)

    if not catalog_path.exists():
        return []

    with open(catalog_path, encoding="utf-8") as f:
        return json.load(f)
