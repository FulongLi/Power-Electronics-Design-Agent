"""
STEP export helpers for optimized converter candidates.

This module intentionally depends on CadQuery only at call time so the base PEA
install stays light. The generated model is a first-pass mechanical envelope:
PCB, magnetics, semiconductors, capacitors, and heatsink blocks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def export_candidate_step(candidate: dict[str, Any], dest: str | Path) -> dict[str, Any]:
    """Export a candidate envelope model to STEP using optional CadQuery."""
    try:
        import cadquery as cq
    except ImportError as e:
        raise ImportError("Install CAD extra for STEP export: pip install -e '.[cad]'") from e

    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    power = _power_from_candidate(candidate)
    volume = float(candidate.get("volume_mm3", 40000.0))
    pcb_area = max(1800.0, volume / 20.0)
    pcb_x = max(50.0, (pcb_area * 1.6) ** 0.5)
    pcb_y = max(35.0, pcb_area / pcb_x)
    pcb_z = 1.6

    mag = candidate.get("magnetics", {}) or {}
    mag_volume = _core_volume_from_candidate(mag)
    mag_x = max(18.0, mag_volume ** (1 / 3) * 1.45)
    mag_y = max(14.0, mag_volume ** (1 / 3) * 1.05)
    mag_z = max(10.0, mag_volume / (mag_x * mag_y))

    loss = (candidate.get("loss_breakdown", {}) or {}).get("total_loss_W", 4.0)
    heatsink_x = max(22.0, min(pcb_x * 0.8, float(loss) * 7.0))
    heatsink_y = max(14.0, min(pcb_y * 0.75, float(loss) * 4.0))
    heatsink_z = max(6.0, float(loss) * 1.8)

    pcb = cq.Workplane("XY").box(pcb_x, pcb_y, pcb_z).translate((0, 0, pcb_z / 2))
    magnetic = (
        cq.Workplane("XY")
        .box(mag_x, mag_y, mag_z)
        .translate((-pcb_x * 0.22, 0, pcb_z + mag_z / 2))
    )
    semiconductors = (
        cq.Workplane("XY")
        .box(18, 12, 4)
        .translate((pcb_x * 0.22, -pcb_y * 0.18, pcb_z + 2))
    )
    capacitors = (
        cq.Workplane("XY")
        .cylinder(18, 6)
        .translate((pcb_x * 0.25, pcb_y * 0.20, pcb_z + 9))
    )
    heatsink = (
        cq.Workplane("XY")
        .box(heatsink_x, heatsink_y, heatsink_z)
        .translate((pcb_x * 0.18, -pcb_y * 0.18, pcb_z + 4 + heatsink_z / 2))
    )

    model = pcb.union(magnetic).union(semiconductors).union(capacitors).union(heatsink)
    cq.exporters.export(model, str(dest_path))
    return {
        "ok": True,
        "path": str(dest_path),
        "power_W": power,
        "envelope_mm": {
            "pcb_x": round(pcb_x, 1),
            "pcb_y": round(pcb_y, 1),
            "height": round(pcb_z + max(mag_z, heatsink_z + 4, 18), 1),
        },
    }


def _power_from_candidate(candidate: dict[str, Any]) -> float:
    density = float(candidate.get("power_density_W_per_L", 0.0))
    volume = float(candidate.get("volume_mm3", 0.0))
    if density > 0 and volume > 0:
        return density * (volume / 1_000_000.0)
    design = candidate.get("design", {}) or {}
    return float(design.get("output_power_W", 0.0) or 0.0)


def _core_volume_from_candidate(mag: dict[str, Any]) -> float:
    if "Ae_mm2" in mag:
        return max(2500.0, float(mag["Ae_mm2"]) * 90.0)
    if "core_loss_mW" in mag:
        return max(3000.0, float(mag.get("core_loss_mW", 1.0)) * 30.0)
    return 5000.0
