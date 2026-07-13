"""Worked-example / ground-truth tests for core.cv_analysis."""
import numpy as np
import pytest

from core import cv_analysis as cv


def test_capacitance_from_cv_direct_known_value():
    # C_s = I / (m * scan_rate)
    c = cv.capacitance_from_cv_direct(current_a=0.01, mass_g=0.005, scan_rate_v_per_s=0.02)
    assert c == pytest.approx(0.01 / (0.005 * 0.02))


def test_capacitance_from_cv_rectangular_curve_matches_direct_form():
    # A perfect rectangle (constant +I on forward sweep, -I on reverse)
    # integrated via the closed-loop integral form should match the
    # direct-form formula -- cross-checks the two capacitance formulas
    # against each other for the ideal-EDLC limiting case.
    v_fwd = np.linspace(0, 1, 200)
    v_rev = np.linspace(1, 0, 200)
    i_amp = 0.01
    i_fwd = np.full(200, i_amp)
    i_rev = np.full(200, -i_amp)
    v = np.concatenate([v_fwd, v_rev])
    i = np.concatenate([i_fwd, i_rev])
    mass_g, scan_rate = 0.005, 0.02

    c_integral = cv.capacitance_from_cv(v, i, scan_rate, mass_g)
    c_direct = cv.capacitance_from_cv_direct(i_amp, mass_g, scan_rate)
    assert c_integral == pytest.approx(c_direct, rel=1e-2)


def test_peak_to_peak_separation_finds_known_peaks():
    v = np.linspace(-0.5, 0.5, 1001)
    # place a clean anodic peak at v=+0.2 and cathodic peak at v=-0.3
    i = 1.0 * np.exp(-((v - 0.2) ** 2) / 0.001) - 0.8 * np.exp(-((v + 0.3) ** 2) / 0.001)
    result = cv.peak_to_peak_separation(v, i)
    assert result["e_pa_v"] == pytest.approx(0.2, abs=0.01)
    assert result["e_pc_v"] == pytest.approx(-0.3, abs=0.01)
    assert result["delta_ep_v"] == pytest.approx(0.5, abs=0.02)


def test_randles_sevcik_recovers_known_diffusion_coefficient():
    # Construct synthetic peak currents from the Randles-Sevcik equation
    # itself with a KNOWN D, then check the fit recovers it exactly.
    F, R, T = 96485.33212, 8.314462618, 298.15
    n, area, conc = 1.0, 0.5, 1e-6  # mol/cm^3
    d_true = 3.7e-6  # cm^2/s
    rates = np.array([0.005, 0.01, 0.02, 0.05, 0.1])
    peak_currents = 0.4463 * n * F * area * conc * np.sqrt(n * F * rates * d_true / (R * T))

    result = cv.randles_sevcik_diffusion_coefficient(
        rates, peak_currents, n_electrons=n, electrode_area_cm2=area,
        concentration_mol_per_cm3=conc, temperature_k=T,
    )
    assert result["diffusion_coefficient_cm2_per_s"] == pytest.approx(d_true, rel=1e-6)
    assert result["r_squared"] == pytest.approx(1.0, abs=1e-9)


def test_randles_sevcik_requires_at_least_three_points():
    with pytest.raises(ValueError):
        cv.randles_sevcik_diffusion_coefficient(
            np.array([0.01, 0.02]), np.array([1e-5, 1.4e-5]),
            n_electrons=1, electrode_area_cm2=1, concentration_mol_per_cm3=1e-6,
        )


def test_b_value_from_log_log_known_slope():
    # i = a * v^b with a known b -- log-log slope must recover b exactly
    rates = np.array([0.005, 0.01, 0.02, 0.05, 0.1])
    b_true = 0.73
    a = 2.0
    peaks = a * rates ** b_true
    b_fit = cv.b_value_from_log_log(rates, peaks)
    assert b_fit == pytest.approx(b_true, rel=1e-6)


def test_total_capacitance_from_cv_matches_gravimetric_areal_volumetric():
    # The same enclosed-loop integral, normalized 3 different ways, must
    # each multiply back out to the same total (Farads) -- regression for
    # the gravimetric/areal/volumetric capacitance feature.
    v_fwd = np.linspace(0, 1, 200)
    v_rev = np.linspace(1, 0, 200)
    i_fwd = np.full(200, 0.01)
    i_rev = np.full(200, -0.01)
    v = np.concatenate([v_fwd, v_rev])
    i = np.concatenate([i_fwd, i_rev])
    scan_rate = 0.02
    mass_g, area_cm2, volume_cm3 = 0.005, 2.0, 0.001

    c_total = cv.total_capacitance_from_cv(v, i, scan_rate)
    c_grav = cv.capacitance_from_cv(v, i, scan_rate, mass_g)
    c_areal = cv.areal_capacitance_from_cv(v, i, scan_rate, area_cm2)
    c_vol = cv.volumetric_capacitance_from_cv(v, i, scan_rate, volume_cm3)

    assert c_grav * mass_g == pytest.approx(c_total, rel=1e-9)
    assert c_areal * area_cm2 == pytest.approx(c_total, rel=1e-9)
    assert c_vol * volume_cm3 == pytest.approx(c_total, rel=1e-9)


def test_total_capacitance_from_cv_direct_matches_gravimetric_areal_volumetric():
    current_a, scan_rate = 0.01, 0.02
    mass_g, area_cm2, volume_cm3 = 0.005, 2.0, 0.001

    c_total = cv.total_capacitance_from_cv_direct(current_a, scan_rate)
    c_grav = cv.capacitance_from_cv_direct(current_a, mass_g, scan_rate)
    c_areal = cv.areal_capacitance_from_cv_direct(current_a, area_cm2, scan_rate)
    c_vol = cv.volumetric_capacitance_from_cv_direct(current_a, volume_cm3, scan_rate)

    assert c_grav * mass_g == pytest.approx(c_total, rel=1e-9)
    assert c_areal * area_cm2 == pytest.approx(c_total, rel=1e-9)
    assert c_vol * volume_cm3 == pytest.approx(c_total, rel=1e-9)


def test_areal_and_volumetric_capacitance_from_cv_reject_non_positive_normalizer():
    v = np.linspace(0, 1, 10)
    i = np.ones(10) * 0.01
    with pytest.raises(ValueError):
        cv.areal_capacitance_from_cv(v, i, 0.02, area_cm2=0)
    with pytest.raises(ValueError):
        cv.volumetric_capacitance_from_cv(v, i, 0.02, volume_cm3=-1)
