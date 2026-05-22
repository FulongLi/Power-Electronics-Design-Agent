"""
Tests for the PEA Pareto optimizer and optional CAD boundary.
"""

import pytest

from pea.cad import export_candidate_step
from pea.optimization import (
    DesignSpec,
    OptimizationConfig,
    CandidateDesign,
    optimize_converter_design,
    pareto_front,
    rank_candidates,
)


def test_design_spec_validation():
    with pytest.raises(ValueError):
        DesignSpec(v_in_min=60, v_in_nom=48, v_in_max=36, v_out=12, i_out=10)


def test_pareto_front_removes_dominated_candidate():
    strong = CandidateDesign(
        candidate_id="strong",
        topology="Buck",
        frequency_khz=200,
        selected_semiconductors={},
        magnetics={},
        capacitors={},
        loss_breakdown={"total_loss_W": 1},
        estimated_efficiency_pct=96,
        volume_mm3=10000,
        cost_usd=5,
        power_density_W_per_L=1200,
    )
    weak = CandidateDesign(
        candidate_id="weak",
        topology="Buck",
        frequency_khz=100,
        selected_semiconductors={},
        magnetics={},
        capacitors={},
        loss_breakdown={"total_loss_W": 2},
        estimated_efficiency_pct=94,
        volume_mm3=12000,
        cost_usd=6,
        power_density_W_per_L=1000,
    )
    front = pareto_front([strong, weak])
    assert strong in front
    assert weak not in front
    assert rank_candidates(front)[0].score > 0


def test_buck_scenario_generates_pareto_front():
    result = optimize_converter_design(
        {
            "v_in_min": 10,
            "v_in_nom": 12,
            "v_in_max": 14,
            "v_out": 5,
            "i_out": 2,
            "topology_allowlist": ["Buck", "Boost", "SEPIC"],
            "fsw_range_khz": [100, 300],
        },
        {"backend": "deterministic", "max_candidates": 40},
    )
    assert result.pareto_front
    assert result.recommended_candidate is not None
    assert result.recommended_candidate.topology == "Buck"


def test_48v_12v_scenario_has_tradeoff_data():
    result = optimize_converter_design(
        {
            "v_in_min": 36,
            "v_in_nom": 48,
            "v_in_max": 60,
            "v_out": 12,
            "i_out": 20,
            "fsw_range_khz": [80, 400],
        },
        {"backend": "deterministic", "max_candidates": 60},
    )
    candidate = result.recommended_candidate
    assert candidate is not None
    assert candidate.frequency_khz >= 80
    assert candidate.magnetics
    assert candidate.selected_semiconductors
    assert candidate.cost_usd > 0


def test_isolated_high_power_prefers_llc():
    result = optimize_converter_design(
        {
            "v_in_min": 360,
            "v_in_nom": 400,
            "v_in_max": 420,
            "v_out": 12,
            "i_out": 41.67,
            "isolation_required": True,
            "fsw_range_khz": [100, 300],
        },
        {"backend": "deterministic", "max_candidates": 50},
    )
    assert result.recommended_candidate is not None
    assert result.recommended_candidate.topology == "LLC"


def test_impossible_allowlist_reports_no_candidate():
    result = optimize_converter_design(
        {
            "v_in_min": 5,
            "v_in_nom": 5,
            "v_in_max": 5,
            "v_out": 12,
            "i_out": 1,
            "topology_allowlist": ["Buck"],
            "fsw_range_khz": [100, 100],
        },
        {"backend": "deterministic"},
    )
    assert result.recommended_candidate is None
    assert not result.pareto_front
    assert "No feasible design" in result.ranking_explanation


def test_pymoo_backend_missing_gives_clear_error(monkeypatch):
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("pymoo"):
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    with pytest.raises(ImportError, match="Install optimize extra"):
        optimize_converter_design(
            {
                "v_in_min": 10,
                "v_in_nom": 12,
                "v_in_max": 14,
                "v_out": 5,
                "i_out": 2,
            },
            {"backend": "pymoo"},
        )


def test_cad_missing_gives_clear_error(tmp_path, monkeypatch):
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "cadquery":
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    candidate = optimize_converter_design(
        {
            "v_in_min": 10,
            "v_in_nom": 12,
            "v_in_max": 14,
            "v_out": 5,
            "i_out": 2,
            "topology_allowlist": ["Buck"],
        },
        {"backend": "deterministic"},
    ).recommended_candidate
    assert candidate is not None
    with pytest.raises(ImportError, match="Install CAD extra"):
        export_candidate_step(candidate.to_dict(), tmp_path / "candidate.step")
