"""
Multi-objective DC-DC converter optimization for PEA.

The optimizer keeps the first release practical: it can run with no heavy
optional dependencies by generating deterministic engineering candidates and
extracting a Pareto front. When ``pymoo`` is installed, callers may request the
NSGA-II backend through ``OptimizationConfig.backend="pymoo"``.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass, field
from typing import Any

from pea.components.schema import (
    REFERENCE_CAPACITORS,
    REFERENCE_DIODES,
    REFERENCE_MOSFETS,
    Capacitor,
    Diode,
    MOSFET,
)
from pea.tools.calculator import (
    boost_converter_design,
    buck_boost_design,
    buck_converter_design,
    cuk_design,
    efficiency_estimate,
    inductor_design,
    llc_design,
    sepic_design,
    transformer_design,
)
from pea.tools.magnetics_data import CORE_DATA


SUPPORTED_TOPOLOGIES = ["Buck", "Boost", "Buck-Boost", "SEPIC", "Cuk", "LLC"]
DEFAULT_OBJECTIVES = ["efficiency", "volume", "cost"]


@dataclass
class DesignSpec:
    """Electrical and product constraints for a converter optimization run."""

    v_in_min: float
    v_in_nom: float
    v_in_max: float
    v_out: float
    i_out: float
    power_W: float | None = None
    topology_allowlist: list[str] = field(default_factory=lambda: SUPPORTED_TOPOLOGIES.copy())
    isolation_required: bool = False
    fsw_range_khz: tuple[float, float] = (50.0, 500.0)
    ambient_temp_C: float = 25.0
    max_temp_C: float = 100.0

    def __post_init__(self) -> None:
        for name in ("v_in_min", "v_in_nom", "v_in_max", "v_out", "i_out"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if not (self.v_in_min <= self.v_in_nom <= self.v_in_max):
            raise ValueError("Require v_in_min <= v_in_nom <= v_in_max")
        if self.power_W is None:
            self.power_W = self.v_out * self.i_out
        if self.power_W <= 0:
            raise ValueError("power_W must be positive")
        f_min, f_max = self.fsw_range_khz
        if f_min <= 0 or f_max <= 0 or f_min > f_max:
            raise ValueError("fsw_range_khz must be positive and ordered")
        allowed = [_normalize_topology(t) for t in self.topology_allowlist]
        self.topology_allowlist = [t for t in allowed if t in SUPPORTED_TOPOLOGIES]
        if not self.topology_allowlist:
            raise ValueError(f"No supported topology in allowlist: {SUPPORTED_TOPOLOGIES}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DesignSpec":
        fsw = data.get("fsw_range_khz", (50.0, 500.0))
        if isinstance(fsw, list):
            fsw = tuple(fsw)
        return cls(
            v_in_min=float(data["v_in_min"]),
            v_in_nom=float(data.get("v_in_nom", data["v_in_min"])),
            v_in_max=float(data.get("v_in_max", data.get("v_in_nom", data["v_in_min"]))),
            v_out=float(data["v_out"]),
            i_out=float(data["i_out"]),
            power_W=float(data["power_W"]) if data.get("power_W") is not None else None,
            topology_allowlist=list(data.get("topology_allowlist", SUPPORTED_TOPOLOGIES)),
            isolation_required=bool(data.get("isolation_required", False)),
            fsw_range_khz=(float(fsw[0]), float(fsw[1])),
            ambient_temp_C=float(data.get("ambient_temp_C", 25.0)),
            max_temp_C=float(data.get("max_temp_C", 100.0)),
        )


@dataclass
class OptimizationConfig:
    """Controls the search depth and optimizer backend."""

    objectives: list[str] = field(default_factory=lambda: DEFAULT_OBJECTIVES.copy())
    population_size: int = 48
    generations: int = 18
    seed: int = 7
    max_candidates: int = 80
    backend: str = "auto"

    def __post_init__(self) -> None:
        unknown = [o for o in self.objectives if o not in DEFAULT_OBJECTIVES]
        if unknown:
            raise ValueError(f"Unsupported objectives: {unknown}")
        self.population_size = max(8, int(self.population_size))
        self.generations = max(1, int(self.generations))
        self.max_candidates = max(5, int(self.max_candidates))
        if self.backend not in ("auto", "pymoo", "deterministic"):
            raise ValueError("backend must be auto, pymoo, or deterministic")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "OptimizationConfig":
        data = data or {}
        return cls(
            objectives=list(data.get("objectives", DEFAULT_OBJECTIVES)),
            population_size=int(data.get("population_size", 48)),
            generations=int(data.get("generations", 18)),
            seed=int(data.get("seed", 7)),
            max_candidates=int(data.get("max_candidates", 80)),
            backend=str(data.get("backend", "auto")),
        )


@dataclass
class CandidateDesign:
    """One feasible converter design candidate."""

    candidate_id: str
    topology: str
    frequency_khz: float
    selected_semiconductors: dict[str, Any]
    magnetics: dict[str, Any]
    capacitors: dict[str, Any]
    loss_breakdown: dict[str, float]
    estimated_efficiency_pct: float
    volume_mm3: float
    cost_usd: float
    power_density_W_per_L: float
    warnings: list[str] = field(default_factory=list)
    design: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParetoResult:
    """Complete optimizer output."""

    all_candidates: list[CandidateDesign]
    pareto_front: list[CandidateDesign]
    recommended_candidate: CandidateDesign | None
    ranking_explanation: str
    backend: str = "deterministic"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "warnings": self.warnings,
            "ranking_explanation": self.ranking_explanation,
            "all_candidates": [c.to_dict() for c in self.all_candidates],
            "pareto_front": [c.to_dict() for c in self.pareto_front],
            "recommended_candidate": (
                self.recommended_candidate.to_dict() if self.recommended_candidate else None
            ),
        }


def optimize_converter_design(
    spec: DesignSpec | dict[str, Any],
    config: OptimizationConfig | dict[str, Any] | None = None,
) -> ParetoResult:
    """Generate and rank Pareto-optimal DC-DC converter candidates."""
    spec_obj = spec if isinstance(spec, DesignSpec) else DesignSpec.from_dict(spec)
    cfg = config if isinstance(config, OptimizationConfig) else OptimizationConfig.from_dict(config)

    warnings: list[str] = []
    if cfg.backend in ("auto", "pymoo"):
        try:
            return _optimize_with_pymoo(spec_obj, cfg)
        except ImportError as e:
            if cfg.backend == "pymoo":
                raise
            warnings.append(str(e))
        except Exception as e:
            if cfg.backend == "pymoo":
                raise
            warnings.append(f"pymoo backend failed; used deterministic fallback: {e}")

    candidates = _generate_deterministic_candidates(spec_obj, cfg)
    return _build_result(candidates, spec_obj, backend="deterministic", warnings=warnings)


def optimize_converter_design_json(spec_json: str, config_json: str = "{}") -> str:
    """LangChain/CLI friendly JSON wrapper."""
    result = optimize_converter_design(json.loads(spec_json), json.loads(config_json or "{}"))
    return json.dumps(result.to_dict(), indent=2)


def pareto_front(candidates: list[CandidateDesign]) -> list[CandidateDesign]:
    """Return non-dominated candidates for max efficiency, min volume, min cost."""
    front: list[CandidateDesign] = []
    for cand in candidates:
        dominated = False
        for other in candidates:
            if other is cand:
                continue
            better_or_equal = (
                other.estimated_efficiency_pct >= cand.estimated_efficiency_pct
                and other.volume_mm3 <= cand.volume_mm3
                and other.cost_usd <= cand.cost_usd
            )
            strictly_better = (
                other.estimated_efficiency_pct > cand.estimated_efficiency_pct
                or other.volume_mm3 < cand.volume_mm3
                or other.cost_usd < cand.cost_usd
            )
            if better_or_equal and strictly_better:
                dominated = True
                break
        if not dominated:
            front.append(cand)
    return sorted(front, key=lambda c: (-c.estimated_efficiency_pct, c.volume_mm3, c.cost_usd))


def rank_candidates(candidates: list[CandidateDesign]) -> list[CandidateDesign]:
    """Score candidates with a fixed engineering default preference."""
    if not candidates:
        return []
    effs = [c.estimated_efficiency_pct for c in candidates]
    vols = [c.volume_mm3 for c in candidates]
    costs = [c.cost_usd for c in candidates]
    for c in candidates:
        eff_n = _norm(c.estimated_efficiency_pct, min(effs), max(effs), higher_better=True)
        vol_n = _norm(c.volume_mm3, min(vols), max(vols), higher_better=False)
        cost_n = _norm(c.cost_usd, min(costs), max(costs), higher_better=False)
        c.score = round(0.45 * eff_n + 0.35 * vol_n + 0.20 * cost_n, 4)
    return sorted(candidates, key=lambda c: (-c.score, -c.estimated_efficiency_pct))


def _optimize_with_pymoo(spec: DesignSpec, cfg: OptimizationConfig) -> ParetoResult:
    """Optional NSGA-II backend. Falls back only when caller chose auto."""
    try:
        from pymoo.algorithms.moo.nsga2 import NSGA2
        from pymoo.core.problem import ElementwiseProblem
        from pymoo.optimize import minimize
    except ImportError as e:
        raise ImportError("Install optimize extra for pymoo NSGA-II: pip install -e '.[optimize]'") from e

    topology_pool = _eligible_topologies(spec)
    mosfets = _eligible_mosfets(spec)
    diodes = _eligible_diodes(spec)
    capacitors = _eligible_capacitors(spec)
    core_shapes = ["EE", "ETD", "PQ"]
    materials = ["N87", "N97", "3C95"]

    class ConverterProblem(ElementwiseProblem):
        def __init__(self) -> None:
            super().__init__(n_var=8, n_obj=3, n_ieq_constr=1, xl=0.0, xu=1.0)

        def _evaluate(self, x, out, *args, **kwargs) -> None:
            cand = _candidate_from_vector(
                spec, x, topology_pool, mosfets, diodes, capacitors, core_shapes, materials
            )
            if cand is None:
                out["F"] = [1e3, 1e9, 1e6]
                out["G"] = [1.0]
                return
            out["F"] = [
                -cand.estimated_efficiency_pct,
                cand.volume_mm3,
                cand.cost_usd,
            ]
            out["G"] = [0.0 if not _has_hard_warning(cand) else 1.0]

    algorithm = NSGA2(pop_size=cfg.population_size)
    result = minimize(
        ConverterProblem(),
        algorithm,
        ("n_gen", cfg.generations),
        seed=cfg.seed,
        verbose=False,
    )
    if result.X is None:
        vectors = []
    else:
        try:
            import numpy as np

            vectors = np.atleast_2d(result.X)
        except Exception:
            vectors = result.X
    candidates = []
    for x in vectors:
        cand = _candidate_from_vector(
            spec, x, topology_pool, mosfets, diodes, capacitors, core_shapes, materials
        )
        if cand:
            candidates.append(cand)
    return _build_result(candidates, spec, backend="pymoo-nsga2", warnings=[])


def _generate_deterministic_candidates(spec: DesignSpec, cfg: OptimizationConfig) -> list[CandidateDesign]:
    rng = random.Random(cfg.seed)
    topology_pool = _eligible_topologies(spec)
    mosfets = _eligible_mosfets(spec)[:5]
    diodes = _eligible_diodes(spec)[:4]
    capacitors = _eligible_capacitors(spec)[:4]
    core_shapes = ["EE", "ETD", "PQ"]
    materials = ["N87", "N97", "3C95"]
    f_min, f_max = spec.fsw_range_khz
    if math.isclose(f_min, f_max):
        freqs = [f_min]
    else:
        steps = min(7, max(4, cfg.population_size // 8))
        freqs = [f_min + (f_max - f_min) * i / (steps - 1) for i in range(steps)]
    ripple_targets = [0.2, 0.3, 0.4]
    bmax_targets = [220.0, 280.0, 330.0]

    candidates: list[CandidateDesign] = []
    for topology in topology_pool:
        for f_khz in freqs:
            for ripple in ripple_targets:
                for shape in core_shapes:
                    for material in materials:
                        mosfet = rng.choice(mosfets) if mosfets else None
                        diode = rng.choice(diodes) if diodes else None
                        capacitor = rng.choice(capacitors) if capacitors else None
                        bmax = rng.choice(bmax_targets)
                        cand = _build_candidate(
                            spec=spec,
                            topology=topology,
                            f_sw_khz=f_khz,
                            ripple_current_pct=ripple,
                            core_shape=shape,
                            material=material,
                            b_max_mT=bmax,
                            j_current_density=4.5 if f_khz > 250 else 5.0,
                            mosfet=mosfet,
                            diode=diode,
                            capacitor=capacitor,
                        )
                        if cand:
                            candidates.append(cand)
    ranked = rank_candidates(candidates)
    return ranked[: cfg.max_candidates]


def _build_result(
    candidates: list[CandidateDesign],
    spec: DesignSpec,
    backend: str,
    warnings: list[str],
) -> ParetoResult:
    candidates = _dedupe_candidates(candidates)
    if not candidates:
        return ParetoResult(
            all_candidates=[],
            pareto_front=[],
            recommended_candidate=None,
            ranking_explanation=(
                "No feasible design found. Relax topology allowlist, frequency range, "
                "temperature limit, or voltage/current requirements."
            ),
            backend=backend,
            warnings=warnings,
        )
    front = pareto_front(candidates)
    ranked_front = rank_candidates(front)
    recommended = ranked_front[0] if ranked_front else rank_candidates(candidates)[0]
    explanation = (
        f"Recommended {recommended.topology} at {recommended.frequency_khz:.0f} kHz: "
        f"{recommended.estimated_efficiency_pct:.1f}% efficiency, "
        f"{recommended.power_density_W_per_L:.0f} W/L, "
        f"${recommended.cost_usd:.2f} estimated BOM. "
        "Score weights: efficiency 45%, volume 35%, cost 20%."
    )
    return ParetoResult(
        all_candidates=rank_candidates(candidates),
        pareto_front=ranked_front,
        recommended_candidate=recommended,
        ranking_explanation=explanation,
        backend=backend,
        warnings=warnings,
    )


def _dedupe_candidates(candidates: list[CandidateDesign]) -> list[CandidateDesign]:
    seen: set[tuple[str, float, str, str]] = set()
    unique: list[CandidateDesign] = []
    for cand in candidates:
        key = (
            cand.topology,
            cand.frequency_khz,
            str(cand.magnetics.get("core", "")),
            str(cand.magnetics.get("material", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(cand)
    return unique


def _candidate_from_vector(
    spec: DesignSpec,
    x: Any,
    topology_pool: list[str],
    mosfets: list[MOSFET],
    diodes: list[Diode],
    capacitors: list[Capacitor],
    core_shapes: list[str],
    materials: list[str],
) -> CandidateDesign | None:
    f_min, f_max = spec.fsw_range_khz
    return _build_candidate(
        spec=spec,
        topology=_pick(topology_pool, x[0]),
        f_sw_khz=f_min + (f_max - f_min) * float(x[1]),
        ripple_current_pct=0.15 + 0.35 * float(x[2]),
        core_shape=_pick(core_shapes, x[3]),
        material=_pick(materials, x[4]),
        b_max_mT=200.0 + 150.0 * float(x[5]),
        j_current_density=3.0 + 3.0 * float(x[6]),
        mosfet=_pick(mosfets, x[7]) if mosfets else None,
        diode=_pick(diodes, x[2]) if diodes else None,
        capacitor=_pick(capacitors, x[6]) if capacitors else None,
    )


def _build_candidate(
    spec: DesignSpec,
    topology: str,
    f_sw_khz: float,
    ripple_current_pct: float,
    core_shape: str,
    material: str,
    b_max_mT: float,
    j_current_density: float,
    mosfet: MOSFET | None,
    diode: Diode | None,
    capacitor: Capacitor | None,
) -> CandidateDesign | None:
    design = _run_topology_design(spec, topology, f_sw_khz, ripple_current_pct)
    if not design or "error" in design:
        return None

    mag = _run_magnetics_design(
        spec, topology, design, f_sw_khz, core_shape, material, b_max_mT, j_current_density
    )
    if not mag or "error" in mag:
        return None

    semiconductor = _semiconductor_dict(mosfet, diode, topology)
    cap = _capacitor_dict(capacitor, design, spec)
    loss = _estimate_total_loss(spec, topology, f_sw_khz, mosfet, diode, capacitor, mag)
    warnings = list(loss.pop("warnings", [])) + list(mag.get("warnings", []))
    if _has_hard_constraints(spec, loss, mag):
        warnings.append("Thermal or magnetic constraint near limit; verify with detailed design.")

    p_out = spec.power_W or spec.v_out * spec.i_out
    volume_mm3 = _estimate_volume_mm3(p_out, loss["total_loss_W"], semiconductor, cap, mag)
    cost_usd = _estimate_cost_usd(mosfet, diode, capacitor, mag, topology)
    efficiency = round(100.0 * p_out / (p_out + loss["total_loss_W"]), 2)
    power_density = p_out / (volume_mm3 / 1_000_000.0)
    cid = "-".join(
        _slug(x)
        for x in (
            topology,
            str(round(f_sw_khz)),
            str(mag.get("core", "core")),
            material,
            _part_number(mosfet) or "fet",
            _part_number(capacitor) or "cap",
        )
    )
    return CandidateDesign(
        candidate_id=cid,
        topology=topology,
        frequency_khz=round(f_sw_khz, 1),
        selected_semiconductors=semiconductor,
        magnetics=mag,
        capacitors=cap,
        loss_breakdown=loss,
        estimated_efficiency_pct=efficiency,
        volume_mm3=round(volume_mm3, 1),
        cost_usd=round(cost_usd, 2),
        power_density_W_per_L=round(power_density, 1),
        warnings=warnings,
        design=design,
    )


def _run_topology_design(
    spec: DesignSpec,
    topology: str,
    f_sw_khz: float,
    ripple_current_pct: float,
) -> dict[str, Any] | None:
    kwargs = {
        "v_in": spec.v_in_nom,
        "v_out": spec.v_out,
        "i_out": spec.i_out,
        "f_sw_khz": f_sw_khz,
        "ripple_current_pct": ripple_current_pct,
    }
    if topology == "Buck":
        return buck_converter_design(**kwargs)
    if topology == "Boost":
        return boost_converter_design(**kwargs)
    if topology == "Buck-Boost":
        return buck_boost_design(**kwargs)
    if topology == "SEPIC":
        return sepic_design(**kwargs)
    if topology == "Cuk":
        return cuk_design(**kwargs)
    if topology == "LLC":
        return llc_design(spec.v_in_nom, spec.v_out, spec.i_out, f_sw_khz=f_sw_khz)
    return None


def _run_magnetics_design(
    spec: DesignSpec,
    topology: str,
    design: dict[str, Any],
    f_sw_khz: float,
    core_shape: str,
    material: str,
    b_max_mT: float,
    j_current_density: float,
) -> dict[str, Any] | None:
    if topology == "LLC":
        return transformer_design(
            v_pri=spec.v_in_nom,
            v_sec=spec.v_out,
            power_W=spec.power_W or spec.v_out * spec.i_out,
            f_sw_khz=f_sw_khz,
            duty_cycle=0.45,
            core_shape=core_shape,
            material=material,
            b_max_mT=min(b_max_mT, 280.0),
        )

    L_uH = (
        design.get("inductance_uH")
        or design.get("L1_inductance_uH")
        or design.get("L1_input_inductance_uH")
        or design.get("resonant_inductance_Lr_uH")
    )
    if not L_uH:
        return None
    ripple = float(design.get("ripple_current_A") or design.get("ripple_current_input_A") or spec.i_out * 0.3)
    return inductor_design(
        inductance_uH=float(L_uH),
        i_peak=spec.i_out + ripple / 2,
        i_rms=spec.i_out,
        f_sw_khz=f_sw_khz,
        core_shape=core_shape,
        material=material,
        b_max_mT=b_max_mT,
        j_current_density=j_current_density,
    )


def _estimate_total_loss(
    spec: DesignSpec,
    topology: str,
    f_sw_khz: float,
    mosfet: MOSFET | None,
    diode: Diode | None,
    capacitor: Capacitor | None,
    mag: dict[str, Any],
) -> dict[str, float | list[str]]:
    rds = mosfet.rds_on_mohm if mosfet else 80.0
    qg = mosfet.qg_total_nC if mosfet else 50.0
    vf = diode.vf_typ_V if diode else 0.7
    # The first-pass magnetics calculator intentionally uses conservative
    # Steinmetz fits. For optimizer screening, temper that value so small
    # low-power converters are not dominated by unrealistic ferrite loss.
    mag_loss_scale = 0.015 if topology == "LLC" else 0.08
    mag_loss_W = float(mag.get("total_loss_mW", 0.0)) / 1000.0 * mag_loss_scale
    dcr_mohm = max((float(mag.get("copper_loss_mW", 0.0)) / 1000.0) / max(spec.i_out**2, 0.1) * 1000, 5.0)
    rise = max(8.0, 5.0 + qg * 0.18)
    fall = max(8.0, 5.0 + qg * 0.15)

    if topology == "LLC":
        p_out = spec.power_W or spec.v_out * spec.i_out
        i_pri = p_out / spec.v_in_nom
        p_fet_cond = 4 * (i_pri * 1.25) ** 2 * (rds / 1000.0) * 0.5
        p_secondary = spec.i_out**2 * (rds / 1000.0) * 0.20
        p_soft_switch = 0.5 * spec.v_in_nom * i_pri * (rise + fall) * 1e-9 * (f_sw_khz * 1000.0) * 0.18
        base = {"total_loss_W": p_fet_cond + p_secondary + p_soft_switch}
    else:
        base = efficiency_estimate(
            v_in=spec.v_in_nom,
            v_out=spec.v_out,
            i_out=spec.i_out,
            f_sw_khz=f_sw_khz,
            rds_on_mohm=rds,
            dcr_mohm=dcr_mohm,
            vf_diode=vf,
            t_rise_ns=rise,
            t_fall_ns=fall,
            sync_rect=topology == "Buck",
        )
    cap_esr = capacitor.esr_mohm if capacitor else 20.0
    cap_loss_W = spec.i_out**2 * cap_esr / 1000.0 * 0.25
    gate_drive_W = (qg * 1e-9) * 10.0 * (f_sw_khz * 1000.0) * (4 if topology == "LLC" else 2)
    total = float(base.get("total_loss_W", 0.0)) + mag_loss_W + cap_loss_W + gate_drive_W
    temp_rise = total * _system_thermal_resistance(topology, spec.power_W or spec.v_out * spec.i_out)
    warnings: list[str] = []
    if spec.ambient_temp_C + temp_rise > spec.max_temp_C:
        warnings.append(
            f"Estimated temperature {spec.ambient_temp_C + temp_rise:.0f} C exceeds limit; add heatsink or relax power density."
        )
    return {
        "semiconductor_loss_W": round(float(base.get("total_loss_W", 0.0)), 3),
        "magnetics_loss_W": round(mag_loss_W, 3),
        "capacitor_esr_loss_W": round(cap_loss_W, 3),
        "gate_drive_loss_W": round(gate_drive_W, 3),
        "total_loss_W": round(total, 3),
        "estimated_temp_C": round(spec.ambient_temp_C + temp_rise, 1),
        "warnings": warnings,
    }


def _estimate_volume_mm3(
    power_W: float,
    total_loss_W: float,
    semiconductor: dict[str, Any],
    capacitor: dict[str, Any],
    mag: dict[str, Any],
) -> float:
    core_volume = _core_package_volume_mm3(str(mag.get("core", "")))
    semi_volume = float(semiconductor.get("total_package_volume_mm3", 300.0))
    cap_volume = float(capacitor.get("package_volume_mm3", 800.0))
    pcb_volume = max(3000.0, power_W * 12.0)
    heatsink_volume = max(0.0, total_loss_W * 1800.0)
    clearance = 1.25
    return (core_volume + semi_volume + cap_volume + pcb_volume + heatsink_volume) * clearance


def _estimate_cost_usd(
    mosfet: MOSFET | None,
    diode: Diode | None,
    capacitor: Capacitor | None,
    mag: dict[str, Any],
    topology: str,
) -> float:
    fet_count = 4 if topology == "LLC" else (2 if topology == "Buck" else 1)
    diode_count = 0 if topology in ("Buck", "LLC") else 1
    fet_cost = _part_cost(mosfet, 1.5 if topology == "LLC" else 0.6)
    diode_cost = _part_cost(diode, 0.4)
    cap_cost = _part_cost(capacitor, 0.35)
    core_cost = _core_cost(str(mag.get("core", "")), topology)
    winding_cost = max(0.08, float(mag.get("turns", mag.get("N_primary", 10))) * 0.018)
    return fet_count * fet_cost + diode_count * diode_cost + cap_cost + core_cost + winding_cost


def _eligible_topologies(spec: DesignSpec) -> list[str]:
    allowed = [_normalize_topology(t) for t in spec.topology_allowlist]
    if spec.isolation_required:
        return [t for t in allowed if t == "LLC"]
    pool = []
    for t in allowed:
        if t == "Buck" and spec.v_out < spec.v_in_nom:
            pool.append(t)
        elif t == "Boost" and spec.v_out > spec.v_in_nom:
            pool.append(t)
        elif t in ("Buck-Boost", "SEPIC", "Cuk"):
            pool.append(t)
        elif t == "LLC" and (spec.power_W or 0) >= 200:
            pool.append(t)
    return pool or allowed


def _eligible_mosfets(spec: DesignSpec) -> list[MOSFET]:
    v_req = max(spec.v_in_max, spec.v_out) * 1.3
    i_req = spec.i_out * 1.2
    parts = [m for m in REFERENCE_MOSFETS if m.vds_max_V >= v_req and m.id_max_A >= i_req]
    return sorted(parts or REFERENCE_MOSFETS, key=lambda m: (m.rds_on_mohm, m.qg_total_nC))


def _eligible_diodes(spec: DesignSpec) -> list[Diode]:
    v_req = max(spec.v_in_max, spec.v_out) * 1.3
    i_req = spec.i_out * 1.0
    parts = [d for d in REFERENCE_DIODES if d.vr_max_V >= v_req and d.if_max_A >= i_req]
    return sorted(parts or REFERENCE_DIODES, key=lambda d: (d.vf_typ_V, -d.if_max_A))


def _eligible_capacitors(spec: DesignSpec) -> list[Capacitor]:
    parts = [c for c in REFERENCE_CAPACITORS if c.voltage_rating_V >= spec.v_out * 1.5]
    return sorted(parts or REFERENCE_CAPACITORS, key=lambda c: (c.esr_mohm, -c.capacitance_uF))


def _semiconductor_dict(mosfet: MOSFET | None, diode: Diode | None, topology: str) -> dict[str, Any]:
    fet_count = 4 if topology == "LLC" else (2 if topology == "Buck" else 1)
    diode_count = 0 if topology in ("Buck", "LLC") else 1
    fet_vol = _part_volume(mosfet, 180.0)
    diode_vol = _part_volume(diode, 140.0)
    return {
        "mosfet": _part_number(mosfet),
        "mosfet_count": fet_count,
        "diode": _part_number(diode) if diode_count else "",
        "diode_count": diode_count,
        "total_package_volume_mm3": round(fet_count * fet_vol + diode_count * diode_vol, 1),
        "technology": getattr(mosfet, "technology", "") if mosfet else "",
    }


def _capacitor_dict(capacitor: Capacitor | None, design: dict[str, Any], spec: DesignSpec) -> dict[str, Any]:
    required = (
        design.get("capacitance_uF")
        or design.get("output_capacitance_uF")
        or design.get("resonant_capacitance_Cr_nF", 0) / 1000.0
        or 10.0
    )
    return {
        "part_number": _part_number(capacitor),
        "required_capacitance_uF": round(float(required), 2),
        "selected_capacitance_uF": getattr(capacitor, "capacitance_uF", 0.0) if capacitor else 0.0,
        "voltage_rating_V": getattr(capacitor, "voltage_rating_V", spec.v_out * 1.5) if capacitor else spec.v_out * 1.5,
        "package_volume_mm3": _part_volume(capacitor, max(350.0, float(required) * 18.0)),
    }


def _has_hard_constraints(spec: DesignSpec, loss: dict[str, Any], mag: dict[str, Any]) -> bool:
    temp_bad = float(loss.get("estimated_temp_C", spec.ambient_temp_C)) > spec.max_temp_C
    fill_bad = float(mag.get("window_fill_pct", 0.0)) > 65.0
    b_bad = float(mag.get("B_peak_mT", 0.0)) > 360.0
    return temp_bad or fill_bad or b_bad


def _has_hard_warning(candidate: CandidateDesign) -> bool:
    return any("exceeds" in w.lower() or "constraint" in w.lower() for w in candidate.warnings)


def _normalize_topology(name: str) -> str:
    key = name.strip().lower().replace("_", "-")
    mapping = {
        "buck": "Buck",
        "boost": "Boost",
        "buck-boost": "Buck-Boost",
        "buck boost": "Buck-Boost",
        "sepic": "SEPIC",
        "cuk": "Cuk",
        "ćuk": "Cuk",
        "llc": "LLC",
        "llc resonant": "LLC",
    }
    return mapping.get(key, name)


def _norm(value: float, low: float, high: float, higher_better: bool) -> float:
    if math.isclose(low, high):
        return 1.0
    n = (value - low) / (high - low)
    return n if higher_better else 1.0 - n


def _pick(items: list[Any], x: float) -> Any:
    idx = min(len(items) - 1, max(0, int(float(x) * len(items))))
    return items[idx]


def _part_number(part: Any) -> str:
    return getattr(part, "part_number", "") if part else ""


def _slug(value: str) -> str:
    text = value.lower().replace(" ", "").replace("/", "").replace("_", "-")
    return "".join(ch for ch in text if ch.isalnum() or ch == "-") or "x"


def _part_cost(part: Any, fallback: float) -> float:
    return float(getattr(part, "unit_cost_usd", 0.0) or fallback)


def _part_volume(part: Any, fallback: float) -> float:
    return float(getattr(part, "package_volume_mm3", 0.0) or fallback)


def _core_package_volume_mm3(core_name: str) -> float:
    for shape in CORE_DATA.values():
        for core in shape["sizes"]:
            if core["name"] == core_name:
                return float(core["Ve"]) * 3.2
    return 3000.0


def _core_cost(core_name: str, topology: str) -> float:
    volume = _core_package_volume_mm3(core_name)
    return max(0.4, volume / 6000.0) * (1.5 if topology == "LLC" else 1.0)


def _system_thermal_resistance(topology: str, power_W: float) -> float:
    if topology == "LLC":
        return 2.2 if power_W > 300 else 3.2
    return 3.8 if power_W > 100 else 7.0
