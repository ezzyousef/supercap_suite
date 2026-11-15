"""Independent numerical oracles for every equation in docs/EQUATIONS.md.

Each test builds data from KNOWN physical parameters (an ideal capacitor with a series resistor, a
known R||C circuit, a heat-flow peak of known area ...) and checks that the app's functions recover
those parameters. The expected values are computed here from first principles in SI units, never
by calling the formula under test. A failure therefore means the app disagrees with the physics,
not with itself. Section numbers refer to docs/EQUATIONS.md.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from core import cv_analysis as CV
from core import drt_analysis as DRT
from core import dsc_analysis as DSC
from core import dunn_method as DUNN
from core import eis_analysis as EIS
from core import gcd_analysis as GCD
from core import trasatti_method as TRA

TRAPZ = getattr(np, "trapezoid", None) or np.trapz


# ---------------------------------------------------------------- simulated galvanostatic cell
def rc_discharge(c_f=2.0, r_ohm=0.5, i_a=0.1, v_cap0=1.0, v_end=0.0, dt=0.01):
    """Terminal voltage of an ideal capacitor C in series with R, charged at +I and then
    discharged at -I. Point 0 is the last charge point; the IR step is 2*I*R."""
    t_dis = c_f * (v_cap0 - i_a * r_ohm - v_end) / i_a
    t = np.arange(0.0, t_dis + dt / 2, dt)
    v = v_cap0 - i_a * r_ohm - i_a * t / c_f            # during discharge
    t = np.concatenate([[0.0], t + dt])
    v = np.concatenate([[v_cap0 + i_a * r_ohm], v])     # last charge point
    return t, v


# ---- Section 1a: normal (linear) GCD capacitance, with the IR step excluded
def test_gcd_linear_recovers_capacitance_of_an_ideal_cell():
    c_f, mass_g = 2.0, 0.010
    t, v = rc_discharge(c_f=c_f)
    res = GCD.capacitance_gcd_auto(t, v, current_a=0.1, mass_g=mass_g)
    assert res["method"].startswith("normal")
    assert res["capacitance_f_per_g"] == pytest.approx(c_f / mass_g, rel=2e-3)        # 200 F/g
    assert res["ir_drop_excluded_v"] == pytest.approx(2 * 0.1 * 0.5, rel=0.02)        # 2IR = 0.1 V
    tot = GCD.total_capacitance_gcd_auto(t, v, current_a=0.1)
    assert tot["capacitance_f"] == pytest.approx(c_f, rel=2e-3)


@pytest.mark.parametrize("basis,size", [("areal", 1.5), ("volumetric", 0.02)])
def test_gcd_normalisations_divide_the_same_total_capacitance(basis, size):
    c_f, i_a, dt_s, dv = 2.0, 0.1, 19.0, 0.95
    fn = GCD.areal_capacitance_gcd_normal if basis == "areal" else GCD.volumetric_capacitance_gcd_normal
    assert fn(i_a, dt_s, dv, size) == pytest.approx((i_a * dt_s / dv) / size, rel=1e-12)


# ---- Section 1b: integral form; must not depend on where the potential window sits
@pytest.mark.parametrize("v_min", [0.0, -0.2, 0.4])
def test_gcd_integral_matches_analytic_integral_and_is_offset_invariant(v_min):
    i_a, span, t_end = 0.05, 1.0, 100.0
    t = np.linspace(0.0, t_end, 200_001)
    v = v_min + span * np.sqrt(1.0 - t / t_end)                     # battery-like, non-linear
    # analytic: integral of (V - V_min) dt = span * T * 2/3  ->  C = 2 I (2/3 span T) / span^2
    expected = 2 * i_a * (2.0 / 3.0 * span * t_end) / span ** 2
    assert GCD.total_capacitance_gcd_integral(t, v, i_a) == pytest.approx(expected, rel=1e-3)


def test_gcd_integral_and_linear_forms_each_recover_the_generator_capacitance():
    # Independent of the app (Codex review): the segment after the IR step is known from the
    # generator (index 1 on), and each form is compared with the 2 F the cell was built with.
    c_f, i_a = 2.0, 0.1
    t, v = rc_discharge(c_f=c_f, i_a=i_a)
    t, v = t[1:], v[1:]
    assert GCD.total_capacitance_gcd_integral(t, v, i_a) == pytest.approx(c_f, rel=1e-6)
    assert GCD.total_capacitance_gcd_normal(i_a, t[-1] - t[0], v.max() - v.min()) == pytest.approx(c_f, rel=1e-9)


# ---- Section 2: ESR from the IR step, both conventions
def test_esr_recovers_series_resistance_in_both_conventions():
    r_ohm, i_a = 0.5, 0.1
    t, v = rc_discharge(r_ohm=r_ohm, i_a=i_a)
    step = GCD.estimate_ir_drop(t, v)
    assert GCD.esr_from_ir_drop(step, i_a, current_reverses=True) == pytest.approx(r_ohm, rel=0.01)
    # starting from rest the current changes by I, not 2I: same cell, step of I*R
    assert GCD.esr_from_ir_drop(i_a * r_ohm, i_a, current_reverses=False) == pytest.approx(r_ohm, rel=1e-12)


# ---- Section 3: energy and power density from the SI chain
def test_energy_and_power_density_follow_from_half_c_v_squared():
    c_s, dv, t_dis = 200.0, 1.0, 19.0                                # F/g, V, s
    joule_per_g = 0.5 * c_s * dv ** 2
    wh_per_kg = joule_per_g / 3600.0 * 1000.0
    assert GCD.energy_density_wh_per_kg(c_s, dv) == pytest.approx(wh_per_kg, rel=1e-12)
    assert GCD.energy_density_wh(c_s, dv) == pytest.approx(joule_per_g / 3600.0, rel=1e-12)    # Wh/g, no g->kg
    assert GCD.power_density_w_per_kg(wh_per_kg, t_dis) == pytest.approx(joule_per_g * 1000.0 / t_dis, rel=1e-12)


def test_energy_density_equals_energy_actually_delivered_by_the_simulated_cell():
    c_f, mass_g, i_a = 2.0, 0.010, 0.1
    t, v = rc_discharge(c_f=c_f, r_ohm=0.0, i_a=i_a, v_cap0=1.0, v_end=0.0)
    delivered_j_per_g = TRAPZ(i_a * v[1:], t[1:]) / mass_g            # integral of I*V dt, per gram
    from_formula = GCD.energy_density_wh_per_kg(c_f / mass_g, 1.0) * 3.6
    assert from_formula == pytest.approx(delivered_j_per_g, rel=1e-3)


# ---- Section 4: two/three-electrode conversions, series cells, mass balance
def test_symmetric_cell_factor_of_four_from_two_identical_electrodes():
    c_electrode_f, m_electrode_g = 1.0, 0.005
    c_cell_f = 1.0 / (1.0 / c_electrode_f + 1.0 / c_electrode_f)       # two in series
    c_cell_spec = c_cell_f / (2 * m_electrode_g)                       # per total active mass
    assert GCD.symmetric_cell_to_electrode_capacitance(c_cell_spec) == pytest.approx(c_electrode_f / m_electrode_g)
    assert GCD.three_electrode_to_two_electrode_estimate(c_electrode_f / m_electrode_g) == pytest.approx(c_cell_spec)


def test_series_capacitance_and_charge_balanced_masses():
    assert GCD.cell_capacitance_series(3.0, 6.0) == pytest.approx(2.0)
    c_pos, dv_pos, c_neg, dv_neg = 150.0, 0.8, 250.0, 1.0
    ratio = GCD.asymmetric_electrode_mass_balance(c_pos, dv_pos, c_neg, dv_neg)
    m_neg = 1.0
    m_pos = ratio * m_neg
    assert c_pos * m_pos * dv_pos == pytest.approx(c_neg * m_neg * dv_neg)   # equal charge q = C m dV


# ---------------------------------------------------------------- Section 5: CV of a known capacitor
def triangle_cv(c_f=2.0, scan=0.05, v_lo=-0.2, v_hi=0.8, n=4000, r_ohm=0.0, cycles=1):
    """Current of capacitor C (with optional series R) under a triangular sweep."""
    period = 2 * (v_hi - v_lo) / scan
    t = np.linspace(0.0, period * cycles, n * cycles + 1)
    phase = (t % period) / period
    v = np.where(phase < 0.5, v_lo + 2 * phase * (v_hi - v_lo), v_hi - 2 * (phase - 0.5) * (v_hi - v_lo))
    direction = np.where(phase < 0.5, 1.0, -1.0)
    if r_ohm == 0:
        i = c_f * scan * direction
    else:
        tau = r_ohm * c_f
        since_turn = (phase % 0.5) * period
        i = c_f * scan * direction * (1 - 2 * np.exp(-since_turn / tau))
    return v, i


def test_cv_integral_and_direct_forms_recover_capacitance():
    v, i = triangle_cv(c_f=2.0, scan=0.05)
    assert CV.total_capacitance_from_cv(v, i, 0.05) == pytest.approx(2.0, rel=2e-3)
    assert CV.total_capacitance_from_cv_direct(2.0 * 0.05, 0.05) == pytest.approx(2.0)
    assert CV.specific_capacity_from_cv(v, i, 0.05, mass_g=0.01) == pytest.approx(2.0 * 1.0 / 0.01, rel=2e-3)   # C/g = C*dV/m


def test_cv_with_series_resistance_stays_close_when_rc_is_short():
    v, i = triangle_cv(c_f=2.0, scan=0.05, r_ohm=0.05)                 # tau = 0.1 s, half period 20 s
    assert CV.total_capacitance_from_cv(v, i, 0.05) == pytest.approx(2.0 * (1 - 2 * 0.1 / 20), rel=1e-2)


def test_cv_two_stacked_cycles_double_the_naive_integral():
    v, i = triangle_cv(cycles=2)
    assert CV.total_capacitance_from_cv(v, i, 0.05) == pytest.approx(4.0, rel=5e-3)   # why the app warns
    assert CV.count_cycles(v) == pytest.approx(2.0, abs=0.3)


# ---- Section 5 / 5a: Dunn's b-value and the k1 v + k2 v^0.5 split
def test_b_value_recovers_power_law_exponent():
    scans = np.array([0.005, 0.01, 0.02, 0.05, 0.1])
    assert DUNN.b_value_analysis(scans, 3e-3 * scans ** 0.72).b_value == pytest.approx(0.72, abs=1e-9)


def test_dunn_split_recovers_k1_and_k2():
    scans = np.array([0.005, 0.01, 0.02, 0.05, 0.1, 0.2])
    k1, k2 = 0.0125, 0.0986
    r = DUNN.peak_current_capacitive_diffusive_split(scans, k1 * scans + k2 * np.sqrt(scans))
    assert (r.k1, r.k2) == pytest.approx((k1, k2), rel=1e-9)
    assert r.capacitive_percent[-1] == pytest.approx(100 * k1 * 0.2 / (k1 * 0.2 + k2 * math.sqrt(0.2)), rel=1e-9)


# ---- Section 5b: Trasatti extrapolations
def test_trasatti_outer_and_total_limits():
    scans = np.array([0.005, 0.01, 0.02, 0.05, 0.1, 0.2])
    outer = TRA.trasatti_analysis(scans, 80.0 + 3.0 / np.sqrt(scans))          # eq 18 exactly
    assert outer.outer_capacitance_f_per_g == pytest.approx(80.0, rel=1e-9)
    total = TRA.trasatti_analysis(scans, 1.0 / (0.02 * np.sqrt(scans) + 1.0 / 250.0))   # eq 19 exactly
    assert total.total_capacitance_f_per_g == pytest.approx(250.0, rel=1e-9)


# ---------------------------------------------------------------- Section 6: EIS of known circuits
def test_eis_capacitance_and_conductivity():
    c_f, f = 2.0, 0.01
    z_im = -1.0 / (2 * math.pi * f * c_f)                                   # ideal capacitor
    assert EIS.capacitance_from_eis(z_im, f) == pytest.approx(c_f)
    assert EIS.capacitance_from_eis(z_im, f, mass_g=0.01) == pytest.approx(200.0)
    # sigma = L / (R A): 0.1 cm gel, 2 cm2 electrodes, 5 ohm -> 0.01 S/cm
    assert EIS.ionic_conductivity_s_per_cm(5.0, 0.1, 2.0) == pytest.approx(0.01)


def randles_rc(f, rs=1.0, rct=10.0, c=1e-3):
    w = 2 * np.pi * f
    z = rs + rct / (1 + 1j * w * rct * c)
    return z.real, z.imag


def test_circuit_fit_recovers_rs_rct_c_from_exact_spectrum():
    f = np.logspace(5, -2, 60)
    zr, zi = randles_rc(f)
    fit = EIS.fit_equivalent_circuit(f, zr, zi, model="randles1_C_none", multistart=True)
    values = sorted(fit.params.values())
    for expected in (1e-3, 1.0, 10.0):
        assert any(v == pytest.approx(expected, rel=0.02) for v in values), (expected, fit.params)
    model = fit.z_fit_re + 1j * fit.z_fit_im
    assert np.max(np.abs(model - (zr + 1j * zi)) / np.abs(zr + 1j * zi)) < 5e-3


def test_kramers_kronig_passes_valid_data_and_flags_drift():
    f = np.logspace(5, -2, 60)
    zr, zi = randles_rc(f)
    ok = EIS.kramers_kronig_test(f, zr, zi)
    assert ok.passed and ok.mean_residual_percent < 1.0 and not ok.systematic_trend
    drift = np.linspace(0.0, 0.3, f.size)                                  # 30 % drift in |Z| across the sweep
    bad = EIS.kramers_kronig_test(f, zr * (1 + drift), zi * (1 + drift))
    # Known and documented (REVIEW_LOG): smooth drift leaves a small residual, so the % test alone still
    # passes (1.25 % here); the residual autocorrelation is what catches it.
    assert bad.systematic_trend and bad.residual_autocorrelation > 0.5


# ---- Section 10: DRT of a single RC element peaks at tau = R C and integrates to R
def test_drt_single_rc_peak_position_and_area():
    rct, c = 10.0, 1e-3
    f = np.logspace(5, -2, 70)
    zr, zi = randles_rc(f, rs=1.0, rct=rct, c=c)
    res = DRT.compute_drt(f, zr, zi, lambda_reg=1e-4)
    peak_tau = res.tau_s[int(np.argmax(res.gamma))]
    assert math.log10(peak_tau) == pytest.approx(math.log10(rct * c), abs=0.15)
    area = TRAPZ(res.gamma, np.log(res.tau_s))
    assert area == pytest.approx(rct, rel=0.1)
    assert res.r_inf_ohm == pytest.approx(1.0, rel=0.1)


# ---------------------------------------------------------------- Sections 8-9: DSC
def test_dsc_peak_area_enthalpy_and_unit_conversion():
    t = np.linspace(0.0, 600.0, 6001)                                       # 10 min at 0.1 s
    area_j, mass_g = 0.5, 0.010                                             # 0.5 J peak, 10 mg sample
    sigma = 20.0
    q_mw = area_j * 1000.0 * np.exp(-0.5 * ((t - 300) / sigma) ** 2) / (sigma * math.sqrt(2 * math.pi))
    assert DSC.integrate_dsc_peak(t, q_mw) == pytest.approx(area_j, rel=1e-6)
    assert DSC.enthalpy_j_per_g(area_j, mass_g) == pytest.approx(50.0)
    w_per_g = q_mw / 1000.0 / mass_g                                         # the same curve, mass-normalised
    assert DSC.heat_flow_to_mw(w_per_g, "W/g (normalised)", mass_g) == pytest.approx(q_mw, rel=1e-12)
    assert DSC.heat_flow_to_mw(q_mw / 1000.0, "W") == pytest.approx(q_mw, rel=1e-12)
    baseline = 0.3 + 0.001 * t                                              # sloping baseline under the peak
    assert DSC.integrate_dsc_peak(t, q_mw + baseline, baseline_mw=baseline) == pytest.approx(area_j, rel=1e-6)


def test_water_classification_mass_balance():
    m_water, m_dry, dh = 0.40, 0.10, 333.55
    freezable_g = 0.30                                                       # of which 0.10 g melts below 0 degC
    area = freezable_g * dh
    res = DSC.classify_water_types(m_water, m_dry, melting_peak_area_j=area,
                                   symmetric_peak_area_j=0.10 * dh, total_peak_area_j=area)
    assert res.total_water_content == pytest.approx(m_water / m_dry)
    assert res.freezable_water_content == pytest.approx(freezable_g / m_dry, rel=1e-9)
    assert res.non_freezable_bound_water == pytest.approx((m_water - freezable_g) / m_dry, rel=1e-9)
    # each population on its own (Codex review: sums alone would not catch two swapped categories)
    assert res.freezable_bound_water == pytest.approx(0.10 / m_dry, rel=1e-9)          # melts below 0 degC: 1
    assert res.free_water == pytest.approx((freezable_g - 0.10) / m_dry, rel=1e-9)      # 2
    assert res.total_bound_water == pytest.approx((m_water - freezable_g + 0.10) / m_dry, rel=1e-9)   # 2
