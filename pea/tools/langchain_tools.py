"""
LangChain structured tools for PEA design calculations.

Uses @tool decorator for reliable tool calling with OpenAI and other LLMs.
"""

from __future__ import annotations

import json
from typing import Optional

from langchain_core.tools import tool

from pea.tools.calculator import (
    buck_boost_design,
    buck_converter_design,
    boost_converter_design,
    cascade_design as _cascade_design,
    cuk_design as _cuk_design,
    dab_design as _dab_design,
    efficiency_estimate as _efficiency_estimate,
    flyback_design,
    forward_design as _forward_design,
    inductor_design as _inductor_design,
    llc_design as _llc_design,
    sepic_design as _sepic_design,
    topology_recommendation,
    transformer_design as _transformer_design,
)
from pea.optimization import optimize_converter_design as _optimize_converter_design


def _fmt(result: dict) -> str:
    return json.dumps(result, indent=2)


# ── Topology recommendation ──────────────────────────────────────────────


@tool
def recommend_topology(
    v_in: float,
    v_out: float,
    i_out: float,
    isolated: bool = False,
    bidirectional: bool = False,
) -> str:
    """Recommend a converter topology (Buck, Boost, SEPIC, Cuk, Forward, Flyback, LLC, DAB, or cascade) based on input/output voltage, current, isolation, and bidirectional requirements."""
    return _fmt(topology_recommendation(
        v_in=v_in, v_out=v_out, i_out=i_out,
        isolated=isolated, bidirectional=bidirectional,
    ))


# ── Non-isolated designs ─────────────────────────────────────────────────


@tool
def design_buck(
    v_in: float,
    v_out: float,
    i_out: float,
    f_sw_khz: float = 100,
    ripple_current_pct: float = 0.3,
    ripple_voltage_pct: float = 0.01,
) -> str:
    """Design a Buck (step-down) converter. Use when V_out < V_in. Returns inductance, capacitance, duty cycle, and design notes."""
    return _fmt(buck_converter_design(
        v_in=v_in, v_out=v_out, i_out=i_out,
        f_sw_khz=f_sw_khz, ripple_current_pct=ripple_current_pct,
        ripple_voltage_pct=ripple_voltage_pct,
    ))


@tool
def design_boost(
    v_in: float,
    v_out: float,
    i_out: float,
    f_sw_khz: float = 100,
    ripple_current_pct: float = 0.3,
    ripple_voltage_pct: float = 0.01,
) -> str:
    """Design a Boost (step-up) converter. Use when V_out > V_in. Returns inductance, capacitance, duty cycle, and design notes."""
    return _fmt(boost_converter_design(
        v_in=v_in, v_out=v_out, i_out=i_out,
        f_sw_khz=f_sw_khz, ripple_current_pct=ripple_current_pct,
        ripple_voltage_pct=ripple_voltage_pct,
    ))


@tool
def design_buck_boost(
    v_in: float,
    v_out: float,
    i_out: float,
    f_sw_khz: float = 100,
    ripple_current_pct: float = 0.3,
    ripple_voltage_pct: float = 0.01,
) -> str:
    """Design a Buck-Boost (inverting) converter. Pass v_out as positive magnitude; output polarity is negative. Good for wide input range."""
    return _fmt(buck_boost_design(
        v_in=v_in, v_out=-abs(v_out), i_out=i_out,
        f_sw_khz=f_sw_khz, ripple_current_pct=ripple_current_pct,
        ripple_voltage_pct=ripple_voltage_pct,
    ))


@tool
def design_sepic(
    v_in: float,
    v_out: float,
    i_out: float,
    f_sw_khz: float = 100,
    ripple_current_pct: float = 0.3,
    ripple_voltage_pct: float = 0.01,
) -> str:
    """Design a SEPIC converter (non-inverting buck-boost). Can step up or step down with common ground and positive output."""
    return _fmt(_sepic_design(
        v_in=v_in, v_out=v_out, i_out=i_out,
        f_sw_khz=f_sw_khz, ripple_current_pct=ripple_current_pct,
        ripple_voltage_pct=ripple_voltage_pct,
    ))


@tool
def design_cuk(
    v_in: float,
    v_out: float,
    i_out: float,
    f_sw_khz: float = 100,
    ripple_current_pct: float = 0.3,
    ripple_voltage_pct: float = 0.01,
) -> str:
    """Design a Cuk converter (inverting, continuous input & output current). Low input/output ripple current."""
    return _fmt(_cuk_design(
        v_in=v_in, v_out=v_out, i_out=i_out,
        f_sw_khz=f_sw_khz, ripple_current_pct=ripple_current_pct,
        ripple_voltage_pct=ripple_voltage_pct,
    ))


# ── Isolated designs ─────────────────────────────────────────────────────


@tool
def design_forward(
    v_in_min: float,
    v_in_max: float,
    v_out: float,
    i_out: float,
    f_sw_khz: float = 100,
    n_ratio: Optional[float] = None,
) -> str:
    """Design a Forward converter (isolated single-ended). Good for 50-300 W. v_in_min/v_in_max define input voltage range."""
    return _fmt(_forward_design(
        v_in_min=v_in_min, v_in_max=v_in_max, v_out=v_out, i_out=i_out,
        f_sw_khz=f_sw_khz, n_ratio=n_ratio,
    ))


@tool
def design_flyback(
    v_in_min: float,
    v_in_max: float,
    v_out: float,
    i_out: float,
    f_sw_khz: float = 100,
    n_ratio: Optional[float] = None,
) -> str:
    """Design a Flyback isolated converter. Use when galvanic isolation is required. v_in_min and v_in_max define input voltage range."""
    return _fmt(flyback_design(
        v_in_min=v_in_min, v_in_max=v_in_max, v_out=v_out, i_out=i_out,
        f_sw_khz=f_sw_khz, n_ratio=n_ratio,
    ))


@tool
def design_llc(
    v_in: float,
    v_out: float,
    i_out: float,
    f_sw_khz: float = 100,
    q_factor: float = 0.5,
    n_ratio: Optional[float] = None,
) -> str:
    """Design an LLC resonant converter. High-efficiency isolated topology with ZVS. Good for >200 W."""
    return _fmt(_llc_design(
        v_in=v_in, v_out=v_out, i_out=i_out,
        f_sw_khz=f_sw_khz, q_factor=q_factor, n_ratio=n_ratio,
    ))


# ── DAB ───────────────────────────────────────────────────────────────────


@tool
def design_dab(
    v1: float,
    v2: float,
    p_rated: float,
    f_sw_khz: float = 100,
    phi_deg: float = 30,
) -> str:
    """Design a DAB (Dual Active Bridge) bidirectional isolated converter. Ideal for EV charging, energy storage, and V2G. Returns leakage inductance, currents, ZVS status."""
    return _fmt(_dab_design(
        v1=v1, v2=v2, p_rated=p_rated,
        f_sw_khz=f_sw_khz, phi_deg=phi_deg,
    ))


# ── Cascade / multi-stage ────────────────────────────────────────────────


@tool
def design_cascade(
    v_in: float,
    v_out: float,
    i_out: float,
    f_sw_khz: float = 100,
) -> str:
    """Design a cascade (multi-stage) converter. Auto-selects appropriate stages (e.g. PFC Boost + LLC, Buck + Buck). Use for extreme conversion ratios or AC-DC with isolation."""
    return _fmt(_cascade_design(
        v_in=v_in, v_out=v_out, i_out=i_out, f_sw_khz=f_sw_khz,
    ))


# ── Magnetics design ─────────────────────────────────────────────────────


@tool
def design_inductor(
    inductance_uH: float,
    i_peak: float,
    i_rms: float,
    f_sw_khz: float = 100,
    core_shape: str = "EE",
    material: str = "N87",
    b_max_mT: float = 300,
) -> str:
    """Design a filter inductor: select core, compute turns, wire gauge, air gap, and Steinmetz core loss. Use after running a converter design to size the inductor."""
    return _fmt(_inductor_design(
        inductance_uH=inductance_uH, i_peak=i_peak, i_rms=i_rms,
        f_sw_khz=f_sw_khz, core_shape=core_shape, material=material,
        b_max_mT=b_max_mT,
    ))


@tool
def design_transformer(
    v_pri: float,
    v_sec: float,
    power_W: float,
    f_sw_khz: float = 100,
    duty_cycle: float = 0.45,
    core_shape: str = "EE",
    material: str = "N87",
    b_max_mT: float = 250,
) -> str:
    """Design a power transformer: select core, compute turns ratio, wire sizes, and losses. Use for isolated converter transformer design."""
    return _fmt(_transformer_design(
        v_pri=v_pri, v_sec=v_sec, power_W=power_W,
        f_sw_khz=f_sw_khz, duty_cycle=duty_cycle,
        core_shape=core_shape, material=material, b_max_mT=b_max_mT,
    ))


# ── Efficiency estimation ────────────────────────────────────────────────


@tool
def estimate_efficiency(
    v_in: float,
    v_out: float,
    i_out: float,
    f_sw_khz: float = 100,
    rds_on_mohm: float = 50.0,
    dcr_mohm: float = 30.0,
    vf_diode: float = 0.5,
    t_rise_ns: float = 20.0,
    t_fall_ns: float = 20.0,
    sync_rect: bool = False,
) -> str:
    """Estimate converter efficiency and loss breakdown given component parameters (MOSFET Rds_on, inductor DCR, diode Vf, switching times)."""
    return _fmt(_efficiency_estimate(
        v_in=v_in, v_out=v_out, i_out=i_out, f_sw_khz=f_sw_khz,
        rds_on_mohm=rds_on_mohm, dcr_mohm=dcr_mohm, vf_diode=vf_diode,
        t_rise_ns=t_rise_ns, t_fall_ns=t_fall_ns, sync_rect=sync_rect,
    ))


# ── Pareto optimization ──────────────────────────────────────────────────


@tool
def optimize_converter_design(
    v_in_min: float,
    v_in_nom: float,
    v_in_max: float,
    v_out: float,
    i_out: float,
    isolation_required: bool = False,
    f_sw_min_khz: float = 50.0,
    f_sw_max_khz: float = 500.0,
    population_size: int = 48,
    generations: int = 18,
) -> str:
    """Generate Pareto converter designs across topology, frequency, semiconductors, magnetics, efficiency, volume, and cost. Use when the user asks for optimized or trade-off designs."""
    result = _optimize_converter_design(
        {
            "v_in_min": v_in_min,
            "v_in_nom": v_in_nom,
            "v_in_max": v_in_max,
            "v_out": v_out,
            "i_out": i_out,
            "isolation_required": isolation_required,
            "fsw_range_khz": [f_sw_min_khz, f_sw_max_khz],
        },
        {
            "population_size": population_size,
            "generations": generations,
            "max_candidates": 80,
            "backend": "auto",
        },
    )
    data = result.to_dict()
    # Keep agent context compact: return Pareto front and recommendation, not every candidate.
    return _fmt({
        "backend": data["backend"],
        "warnings": data["warnings"],
        "ranking_explanation": data["ranking_explanation"],
        "recommended_candidate": data["recommended_candidate"],
        "pareto_front": data["pareto_front"][:12],
    })


# ── Tool list ────────────────────────────────────────────────────────────


def get_pea_tools() -> list:
    """Return list of LangChain tools for PEA agent."""
    return [
        recommend_topology,
        design_buck,
        design_boost,
        design_buck_boost,
        design_sepic,
        design_cuk,
        design_forward,
        design_flyback,
        design_llc,
        design_dab,
        design_cascade,
        design_inductor,
        design_transformer,
        estimate_efficiency,
        optimize_converter_design,
    ]
