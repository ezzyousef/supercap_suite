"""Worked-example / ground-truth tests for core.gcd_analysis.

Run with: pytest tests/ -v  (from the project root)
"""
import numpy as np
import pytest

from core import gcd_analysis as gcd


def test_capacitance_gcd_normal_known_values():
    # C_s = I*dt / (m*dV) -- 1 A, 10 s, 5 g, 1 V -> C_s = 2 F/g
    c = gcd.capacitance_gcd_normal(current_a=1.0, discharge_time_s=10.0, voltage_window_v=1.0, mass_g=5.0)
    assert c == pytest.approx(2.0)


def test_capacitance_gcd_integral_reduces_to_normal_for_a_linear_discharge():
    # For a perfectly linear discharge, the integral form must numerically
    # match the normal (closed-form) formula -- this is the mathematical
    # consistency check between the two formulas, not a literature number.
    t = np.linspace(0, 10, 500)
    v = 1.0 - 0.1 * t  # linear discharge, dV=1 over dt=10
    current_a, mass_g = 0.5, 2.0
    c_normal = gcd.capacitance_gcd_normal(current_a, 10.0, 1.0, mass_g)
    c_integral = gcd.capacitance_gcd_integral(t, v, current_a, mass_g, voltage_window_v=1.0)
    assert c_integral == pytest.approx(c_normal, rel=1e-3)


def test_classify_discharge_linearity_detects_linear_curve():
    t = np.linspace(0, 10, 100)
    v = 1.0 - 0.1 * t
    result = gcd.classify_discharge_linearity(t, v)
    assert result.is_linear
    assert result.r_squared > 0.999


def test_classify_discharge_linearity_detects_nonlinear_curve():
    t = np.linspace(0, 10, 100)
    v = np.exp(-t / 3.0)  # strongly curved (pseudocapacitive-like) decay
    result = gcd.classify_discharge_linearity(t, v, r2_threshold=0.98)
    assert not result.is_linear


def test_esr_from_ir_drop():
    # ESR = IR_drop / I
    assert gcd.esr_from_ir_drop(ir_drop_v=0.1, current_a=0.5) == pytest.approx(0.2)


def test_energy_and_power_density_known_values():
    # E = C*dV^2/7.2 ; P = E*3600/dt
    e = gcd.energy_density_wh_per_kg(capacitance_f_per_g=100.0, voltage_window_v=1.2)
    assert e == pytest.approx(100.0 * 1.2 ** 2 / 7.2)
    p = gcd.power_density_w_per_kg(e, discharge_time_s=10.0)
    assert p == pytest.approx(e * 3600 / 10.0)


def test_symmetric_and_three_electrode_conversions_are_inverses():
    c_cell = 25.0
    c_electrode = gcd.symmetric_cell_to_electrode_capacitance(c_cell)
    assert c_electrode == pytest.approx(4 * c_cell)
    back = gcd.three_electrode_to_two_electrode_estimate(c_electrode)
    assert back == pytest.approx(c_cell)


def test_capacitance_retention_percent():
    caps = np.array([100.0, 95.0, 90.0, 80.0])
    retention = gcd.capacitance_retention_percent(caps)
    np.testing.assert_allclose(retention, [100.0, 95.0, 90.0, 80.0])


def _make_synthetic_cycle(t0, dt_charge, dt_discharge, n=50):
    t_c = np.linspace(t0, t0 + dt_charge, n)
    v_c = np.linspace(0, 1.0, n)
    t0 += dt_charge
    t_d = np.linspace(t0, t0 + dt_discharge, n)
    v_d = np.linspace(1.0, 0, n)
    t0 += dt_discharge
    return t0, (t_c, v_c), (t_d, v_d)


def test_detect_charge_discharge_segments_alternates_correctly():
    t0 = 0.0
    segs_t, segs_v, expected_kinds = [], [], []
    for _ in range(3):
        t0, (t_c, v_c), (t_d, v_d) = _make_synthetic_cycle(t0, 10.0, 10.0)
        segs_t += [t_c, t_d]
        segs_v += [v_c, v_d]
        expected_kinds += ["charge", "discharge"]
    t = np.concatenate(segs_t)
    v = np.concatenate(segs_v)
    segments = gcd.detect_charge_discharge_segments(t, v)
    assert [s.kind for s in segments] == expected_kinds


def test_analyze_cycling_stability_recovers_known_fade_and_efficiency():
    current, mass = 0.001, 0.005
    segs_t, segs_v = [], []
    t0 = 0.0
    true_caps = []
    n_cycles = 4
    fade_per_cycle = 0.03
    ce_true = 0.97
    for cyc in range(n_cycles):
        fade = 1.0 - fade_per_cycle * cyc
        dt_c, dt_d = 10.0 * fade, 10.0 * fade * ce_true
        t0, (t_c, v_c), (t_d, v_d) = _make_synthetic_cycle(t0, dt_c, dt_d)
        segs_t += [t_c, t_d]
        segs_v += [v_c, v_d]
        true_caps.append(current * dt_d / (mass * 1.0))

    t = np.concatenate(segs_t)
    v = np.concatenate(segs_v)
    results = gcd.analyze_cycling_stability(t, v, current, mass)

    assert len(results) == n_cycles
    for r, true_c in zip(results, true_caps):
        assert r.capacitance_f_per_g == pytest.approx(true_c, rel=0.02)
        assert r.coulombic_efficiency_percent == pytest.approx(ce_true * 100, rel=0.02)
    # retention should track the fade curve
    expected_retention = [100.0 * (1 - fade_per_cycle * c) / 1.0 for c in range(n_cycles)]
    for r, exp in zip(results, expected_retention):
        assert r.retention_percent == pytest.approx(exp, rel=0.05)


def test_analyze_cycling_stability_with_explicit_cycle_column_matches_heuristic():
    current, mass = 0.001, 0.005
    segs_t, segs_v, segs_cyc = [], [], []
    t0 = 0.0
    for cyc in range(3):
        t0, (t_c, v_c), (t_d, v_d) = _make_synthetic_cycle(t0, 10.0, 9.7)
        segs_t += [t_c, t_d]
        segs_v += [v_c, v_d]
        segs_cyc += [np.full(50, cyc + 1), np.full(50, cyc + 1)]
    t = np.concatenate(segs_t)
    v = np.concatenate(segs_v)
    cyc_col = np.concatenate(segs_cyc)

    from_heuristic = gcd.analyze_cycling_stability(t, v, current, mass)
    from_column = gcd.analyze_cycling_stability(t, v, current, mass, cycle_numbers=cyc_col)

    assert len(from_heuristic) == len(from_column) == 3
    for a, b in zip(from_heuristic, from_column):
        assert a.capacitance_f_per_g == pytest.approx(b.capacitance_f_per_g, rel=1e-6)


def test_analyze_cycling_stability_raises_on_no_cycles():
    t = np.linspace(0, 10, 50)
    v = np.full(50, 0.5)  # flat -- no charge/discharge shape at all
    with pytest.raises(ValueError):
        gcd.analyze_cycling_stability(t, v, current_a=0.001, mass_g=0.005)
