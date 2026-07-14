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


def test_linear_baseline_anchor_averaging_matches_single_point_on_flat_noiseless_flanks():
    # With NO noise, averaging N points at a perfectly flat flanking
    # region must give the identical baseline as reading a single point
    # -- the averaging span should only matter once real per-sample
    # noise is present.
    t = np.linspace(0, 10, 200)
    y = np.zeros_like(t)
    y[80:121] = 5.0  # flat-topped "peak" over a flat-zero baseline
    b1 = dsc.linear_baseline(t, y, 60, 140, anchor_avg_points=1)
    b8 = dsc.linear_baseline(t, y, 60, 140, anchor_avg_points=8)
    assert np.allclose(b1[60:141], b8[60:141])


def test_linear_baseline_anchor_averaging_rejects_a_single_noisy_outlier():
    # One noisy outlier sample sitting exactly at the chosen boundary
    # anchors the ENTIRE single-point baseline to that outlier; averaging
    # a handful of the (otherwise clean/flat) surrounding points should
    # recover a value close to the true flat baseline instead.
    t = np.linspace(0, 10, 200)
    y = np.zeros_like(t)
    y[100] = 5.0  # a lone spike, not a real peak
    y[60] = 3.0   # noisy outlier sample sitting exactly at the left anchor row

    b1 = dsc.linear_baseline(t, y, 60, 140, anchor_avg_points=1)
    b5 = dsc.linear_baseline(t, y, 60, 140, anchor_avg_points=5)
    # single-point anchor is pinned to the y[60]=3.0 outlier
    assert b1[60] == pytest.approx(3.0)
    # averaged anchor is pulled back down toward the true flat baseline (0)
    assert b5[60] < 1.0


def test_linear_baseline_anchor_averaging_spans_never_overlap():
    # A short window with anchor_avg_points larger than half the window
    # must not let the two averaging spans overlap each other.
    t = np.linspace(0, 1, 10)
    y = np.arange(10, dtype=float)
    baseline = dsc.linear_baseline(t, y, 2, 5, anchor_avg_points=50)
    assert not np.any(np.isnan(baseline[2:6]))


def test_check_integration_accuracy_accepts_anchor_avg_points():
    t = np.linspace(0, 100, 1000)
    y = 6.0 * np.exp(-0.5 * ((t - 50) / 3.0) ** 2)
    result = dsc.check_integration_accuracy(t, y, 300, 700, anchor_avg_points=5)
    assert result.trapezoid_area_j > 0


def test_zero_and_subzero_peak_areas_splits_by_temperature_threshold():
    # Linear temperature ramp from -10 to +5 degC over a flat-signal
    # window: exactly 2/3 of the (time-uniform) window sits below 0 degC,
    # so a UNIFORM signal should give subzero_fraction == 2/3 regardless
    # of the (flat) signal's magnitude -- this is the same relationship
    # verified against the user's own reference spreadsheet (Calculations
    # of water (version 1).xlsx).
    n = 150
    t = np.linspace(0, 10, n)
    temp = np.linspace(-10, 5, n)
    y = np.full(n, 2.0)
    baseline = np.zeros(n)
    result = dsc.zero_and_subzero_peak_areas(t, y, baseline, temp, 0, n - 1)
    assert result.subzero_fraction == pytest.approx(2 / 3, abs=1e-3)
    assert result.zero_area_j + result.subzero_area_j == pytest.approx(result.total_area_j, rel=1e-9)


def test_zero_and_subzero_peak_areas_all_above_threshold_gives_zero_subzero():
    n = 100
    t = np.linspace(0, 10, n)
    temp = np.linspace(1, 20, n)  # entirely above 0 degC
    y = np.full(n, 3.0)
    baseline = np.zeros(n)
    result = dsc.zero_and_subzero_peak_areas(t, y, baseline, temp, 0, n - 1)
    assert result.subzero_area_j == pytest.approx(0.0, abs=1e-9)
    assert result.subzero_fraction == pytest.approx(0.0, abs=1e-9)


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


def test_symmetric_and_total_peak_areas_equal_for_a_perfectly_symmetric_peak():
    # peak_t exactly on a grid point, window exactly centered -> no
    # boundary-alignment artifacts, so symmetric_area should equal
    # total_area (a Gaussian is symmetric about its own apex).
    t = np.linspace(0, 10, 201)
    peak_idx = 100
    assert t[peak_idx] == 5.0
    y = 5.0 * np.exp(-0.5 * ((t - 5.0) / 0.5) ** 2)
    baseline = np.zeros_like(t)
    result = dsc.symmetric_and_total_peak_areas(t, y, baseline, peak_idx, 0, 200)
    assert result.symmetric_area_j == pytest.approx(result.total_area_j, rel=1e-9)
    assert result.asymmetry_fraction == pytest.approx(0.0, abs=1e-9)


def test_symmetric_and_total_peak_areas_detects_a_one_sided_shoulder():
    t = np.linspace(0, 10, 201)
    peak_idx = 100
    sharp = 5.0 * np.exp(-0.5 * ((t - 5.0) / 0.3) ** 2)
    shoulder = 1.5 * np.exp(-0.5 * ((t - 6.5) / 1.0) ** 2)  # one-sided extra feature
    y = sharp + shoulder
    baseline = np.zeros_like(t)
    result = dsc.symmetric_and_total_peak_areas(t, y, baseline, peak_idx, 0, 200)
    assert result.symmetric_area_j < result.total_area_j
    assert result.asymmetry_fraction > 0.1


def test_check_integration_accuracy_clean_wide_window_has_no_warnings():
    t = np.linspace(0, 100, 300)
    y = 0.1 * t + 5.0 * np.exp(-0.5 * ((t - 50) / 3.0) ** 2)
    peak_idx = int(np.argmin(np.abs(t - 50)))
    dt = t[1] - t[0]
    n_pts = int(8 * 3.0 / dt)  # +/- 8 sigma: tail fully decayed
    result = dsc.check_integration_accuracy(t, y, peak_idx - n_pts, peak_idx + n_pts)
    assert result.warnings == []
    assert result.boundary_sensitivity_percent < 1.0
    assert result.method_difference_percent < 1.0


def test_check_integration_accuracy_flags_a_boundary_still_on_the_peak_tail():
    # A tight window right at the auto-detected boundaries of a Gaussian
    # (whose tail never truly reaches zero) should show meaningful
    # boundary sensitivity and get flagged -- regression for the actual
    # behavior this diagnostic is meant to catch.
    t = np.linspace(0, 100, 300)
    y = 0.1 * t + 5.0 * np.exp(-0.5 * ((t - 50) / 3.0) ** 2)
    peak = dsc.detect_dsc_peak(t, y)
    result = dsc.check_integration_accuracy(t, y, peak.start_index, peak.end_index)
    assert result.boundary_sensitivity_percent > 5.0
    assert any("sensitive to the exact start/end row" in w for w in result.warnings)
