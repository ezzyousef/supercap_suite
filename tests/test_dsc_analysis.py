"""Worked-example / ground-truth tests for core.dsc_analysis."""
import numpy as np
import pytest

from core import dsc_analysis as dsc


def test_enthalpy_j_per_g_known_value():
    assert dsc.enthalpy_j_per_g(peak_area_j=0.05, sample_mass_g=0.01) == pytest.approx(5.0)


def test_classify_water_types_known_worked_example():
    # From the source paper's equation set (Eqs. 1-6): pick round numbers
    # and verify each derived quantity by hand.
    result = dsc.classify_water_types(
        mass_water_g=0.02, mass_dry_g=0.1,
        melting_peak_area_j=3.34,  # -> W_f = 3.34/(334*0.1) = 0.1 g/g
        symmetric_peak_area_j=1.67,  # half of total -> W_fb = W_f * 0.5
        total_peak_area_j=3.34,
        heat_of_fusion_j_per_g=334.0,
    )
    assert result.total_water_content == pytest.approx(0.2)       # W_t = m_w/m_d
    assert result.freezable_water_content == pytest.approx(0.1)   # W_f = A_f/(334*m_d)
    assert result.non_freezable_bound_water == pytest.approx(0.1)  # W_nb = W_t - W_f
    assert result.freezable_bound_water == pytest.approx(0.05)     # W_fb = W_f * (1.67/3.34)
    assert result.total_bound_water == pytest.approx(0.15)         # W_nb + W_fb
    assert result.free_water == pytest.approx(0.05)                # W_f - W_fb


def test_integrate_dsc_peak_known_rectangular_area():
    # A flat 2 mW signal for 5 s above a 0 mW baseline -> 10 mJ = 0.01 J
    t = np.linspace(0, 5, 500)
    y = np.full_like(t, 2.0)
    baseline = np.zeros_like(t)
    area = dsc.integrate_dsc_peak(t, y, baseline_mw=baseline)
    assert area == pytest.approx(0.01, rel=1e-3)


def test_detect_dsc_peak_finds_known_gaussian_peak():
    t = np.linspace(0, 100, 1000)
    y = -0.05 + (-8.0 * np.exp(-0.5 * ((t - 60) / 3.0) ** 2))
    result = dsc.detect_dsc_peak(t, y)
    assert result.direction == "endotherm-down"
    assert result.peak_time_s == pytest.approx(60.0, abs=0.5)
    assert result.peak_value_mw == pytest.approx(-8.05, abs=0.05)
    assert result.start_index < result.peak_index < result.end_index


def test_detect_dsc_peak_finds_upward_peak_too():
    t = np.linspace(0, 100, 1000)
    y = 0.1 + 6.0 * np.exp(-0.5 * ((t - 40) / 2.0) ** 2)
    result = dsc.detect_dsc_peak(t, y)
    assert result.direction == "endotherm-up"
    assert result.peak_time_s == pytest.approx(40.0, abs=0.5)


def test_detect_dsc_peak_raises_on_flat_signal():
    t = np.linspace(0, 100, 200)
    y = np.full_like(t, 0.5)
    with pytest.raises(ValueError):
        dsc.detect_dsc_peak(t, y)


def test_classify_water_types_flags_negative_non_freezable_bound_water():
    # W_f (freezable) deliberately exceeds W_t (total) -- should still
    # compute (not raise), letting the UI layer surface the physical
    # implausibility rather than silently hiding it.
    result = dsc.classify_water_types(
        mass_water_g=0.01, mass_dry_g=0.1,
        melting_peak_area_j=10.0,  # W_f = 10/(334*0.1) = 0.30 >> W_t = 0.1
        symmetric_peak_area_j=5.0, total_peak_area_j=10.0,
    )
    assert result.non_freezable_bound_water < 0
