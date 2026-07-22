"""Tests for core/drt_analysis.py -- Tikhonov-regularized DRT deconvolution.

Self-consistency standard used throughout this app's EIS tooling: fit a
synthetic spectrum with a KNOWN closed-form ground truth and check the
numerical result recovers it. DRT is unusual in that a closed-form
ground truth only exists for a handful of simple elements (a single
ZARC here) -- most equivalent circuits have no known analytical DRT, so
this is one of the few direct checks available."""
import numpy as np
import pytest

from core import drt_analysis as drt


def test_analytical_zarc_drt_forward_integrates_to_the_true_zarc_impedance():
    """Independently verifies the analytical_zarc_drt() closed form itself
    (not just compute_drt()) by numerically forward-integrating
    Z(f) = R_inf + integral[gamma(ln tau)/(1+i*2*pi*f*tau) dlntau] and
    checking it reproduces Rct/(1+(i*2*pi*f*tau_zarc)^phi) directly --
    this is the check that caught a factor-of-2 error in an earlier draft
    of the formula (the source PDF's OCR could not be trusted for this
    specific equation, see the module docstring)."""
    from scipy.integrate import quad

    rct, tau_zarc, phi = 50.0, 1e-3, 0.8

    def z_true(f):
        w = 2 * np.pi * f
        return rct / (1 + (1j * w * tau_zarc) ** phi)

    def z_forward(f):
        w = 2 * np.pi * f

        def re_integrand(ln_tau):
            tau = np.exp(ln_tau)
            gamma = drt.analytical_zarc_drt(np.array([tau]), rct, tau_zarc, phi)[0]
            return gamma / (1 + (w * tau) ** 2)

        def im_integrand(ln_tau):
            tau = np.exp(ln_tau)
            gamma = drt.analytical_zarc_drt(np.array([tau]), rct, tau_zarc, phi)[0]
            return gamma * (-w * tau) / (1 + (w * tau) ** 2)

        re, _ = quad(re_integrand, -50, 50, limit=200)
        im, _ = quad(im_integrand, -50, 50, limit=200)
        return re + 1j * im

    for f in np.logspace(5, -3, 9):
        assert z_forward(f) == pytest.approx(z_true(f), rel=1e-4)


def test_compute_drt_recovers_r_inf_and_zarc_peak_position_and_area():
    rs, rct, tau_zarc, phi = 2.0, 50.0, 1e-3, 0.8
    freq = np.logspace(5, -3, 60)
    omega = 2 * np.pi * freq
    z = rs + rct / (1 + (1j * omega * tau_zarc) ** phi)

    result = drt.compute_drt(freq, z.real, z.imag, lambda_reg=1e-3)

    assert result.r_inf_ohm == pytest.approx(rs, rel=0.05)
    assert result.residual_percent < 1.0

    assert len(result.peaks) == 1
    peak = result.peaks[0]
    assert np.log(peak.tau_s) == pytest.approx(np.log(tau_zarc), abs=0.3)  # within ~35% in tau

    # The area under gamma(ln tau) d(ln tau) over a resolved single ZARC
    # peak should equal Rct (a standard DRT property -- the total charge-
    # transfer resistance is "conserved" under the transform).
    area = np.trapezoid(result.gamma, np.log(result.tau_s))
    assert area == pytest.approx(rct, rel=0.05)


def test_compute_drt_requires_at_least_five_points():
    with pytest.raises(ValueError):
        drt.compute_drt(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 3.0]))


def test_compute_drt_requires_equal_length_arrays():
    with pytest.raises(ValueError):
        drt.compute_drt(np.ones(10), np.ones(9), np.ones(10))


def test_analytical_zarc_drt_requires_phi_strictly_between_zero_and_one():
    with pytest.raises(ValueError):
        drt.analytical_zarc_drt(np.array([1e-3]), 50.0, 1e-3, 1.0)
    with pytest.raises(ValueError):
        drt.analytical_zarc_drt(np.array([1e-3]), 50.0, 1e-3, 0.0)


def test_classify_region_covers_the_full_tau_range_with_no_gaps():
    for tau in [1e-6, 1e-4, 1e-3, 1e-2, 1e-1, 1.0, 10.0, 1e6]:
        label, explanation = drt.classify_region(tau)
        assert label
        assert explanation


def test_classify_region_matches_expected_bands():
    high, _ = drt.classify_region(1e-4)
    mid, _ = drt.classify_region(1e-2)
    low, _ = drt.classify_region(10.0)
    assert "High" in high
    assert "Mid" in mid
    assert "Low" in low


def test_compute_drt_extends_the_collocation_grid_beyond_the_measured_range():
    rs, rct, tau_zarc, phi = 2.0, 50.0, 1e-3, 0.8
    freq = np.logspace(5, -3, 60)
    omega = 2 * np.pi * freq
    z = rs + rct / (1 + (1j * omega * tau_zarc) ** phi)

    result = drt.compute_drt(freq, z.real, z.imag, lambda_reg=1e-3)

    assert len(result.tau_s) > len(freq)  # extended grid has more collocation points than measured frequencies
    assert len(result.tau_s) == len(result.gamma) == len(result.within_measured_range)
    assert len(result.frequency_hz) == len(freq)  # frequency_hz/model_z_* stay at the measured length
    assert len(result.model_z_re_ohm) == len(freq)
    assert result.within_measured_range.sum() == len(freq)  # exactly the measured points are flagged True
    tau_measured = 1.0 / (2 * np.pi * freq)
    assert result.tau_s.min() < tau_measured.min()  # grid extends below the smallest measured tau
    assert result.tau_s.max() > tau_measured.max()  # and above the largest


def test_compute_drt_flags_a_rising_low_frequency_tail_as_a_warning():
    """Reproduces the exact failure mode from a real reported screenshot:
    a spectrum whose low-frequency (near-vertical, blocking-electrode-
    like) capacitive tail is truncated before it's fully resolved. Before
    the grid-extension fix this produced one sharp spike jammed at the
    edge of the collocation grid and a large (~17%) residual; the fix
    should both reduce the residual substantially AND surface an explicit
    warning about the still-rising tail rather than silently showing a
    now-smaller-looking but still misleading result."""
    rs, rct, tau_zarc, phi = 5.0, 15.0, 5e-3, 0.85
    c_low = 2.0  # a large low-frequency series capacitance (near-vertical Nyquist tail)
    freq = np.logspace(4, -1.5, 60)  # truncated before the tail is fully resolved
    omega = 2 * np.pi * freq
    z = rs + rct / (1 + (1j * omega * tau_zarc) ** phi) + 1.0 / (1j * omega * c_low)

    result = drt.compute_drt(freq, z.real, z.imag, lambda_reg=1e-3)

    assert result.residual_percent < 2.0  # much better than the ~17% seen before the fix
    assert any("RISING" in w for w in result.warnings)


def test_compute_drt_clean_spectrum_produces_no_warnings():
    rs, rct, tau_zarc, phi = 2.0, 50.0, 1e-3, 0.8
    freq = np.logspace(5, -3, 60)
    omega = 2 * np.pi * freq
    z = rs + rct / (1 + (1j * omega * tau_zarc) ** phi)

    result = drt.compute_drt(freq, z.real, z.imag, lambda_reg=1e-3)
    assert result.warnings == []


def test_compute_drt_large_residual_produces_a_warning():
    # Deliberately mismatched/noisy data that no reasonable DRT can fit
    # well, to exercise the large-residual warning path.
    freq = np.logspace(4, -2, 40)
    rng = np.random.default_rng(0)
    zre = rng.uniform(-50, 50, size=len(freq))
    zim = rng.uniform(-50, 50, size=len(freq))
    result = drt.compute_drt(freq, zre, zim, lambda_reg=1e-3)
    assert result.residual_percent > 5.0
    assert any("residual is large" in w for w in result.warnings)


# ---------------------------------------------------------------- DCT (Distribution of Capacitive Times)
#
# DCT is the admittance-domain counterpart to DRT, built for BLOCKING-
# electrode systems (Py, Maradesa & Ciucci, Electrochimica Acta 479
# (2024) 143741). Its own closed-form ground truth is the YARC element
# (the admittance-domain analog of a ZARC): Y(f) = G_inf + Gct/(1+(i*2*
# pi*f*tau_YARC)^phi). The source paper states the YARC's DCT has the
# SAME functional form as the ZARC's DRT with Gct substituted for Rct --
# so analytical_zarc_drt() is reused directly as the YARC's ground-truth
# DCT rather than needing a second, separately-derived formula.

def test_compute_dct_recovers_g0_and_yarc_peak_position_and_area():
    g_inf, gct, tau_yarc, phi = 0.05, 0.2, 1e-3, 0.8
    freq = np.logspace(4, -3, 60)
    omega = 2 * np.pi * freq
    y = g_inf + gct / (1 + (1j * omega * tau_yarc) ** phi)
    z = 1.0 / y

    result = drt.compute_dct(freq, z.real, z.imag, lambda_reg=1e-3)

    assert result.g0_s == pytest.approx(g_inf, rel=0.1)
    assert result.c0_f == pytest.approx(0.0, abs=1e-6)
    assert result.residual_percent < 1.0

    assert len(result.peaks) == 1
    peak = result.peaks[0]
    assert np.log(peak.tau_s) == pytest.approx(np.log(tau_yarc), abs=0.3)

    # Same "area under gamma d(ln tau) recovers the element's characteristic
    # magnitude" property compute_drt's ZARC test relies on, here for Gct.
    area = np.trapezoid(result.gamma, np.log(result.tau_s))
    assert area == pytest.approx(gct, rel=0.1)


def test_compute_dct_requires_at_least_five_points():
    with pytest.raises(ValueError):
        drt.compute_dct(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 3.0]))


def test_compute_dct_requires_equal_length_arrays():
    with pytest.raises(ValueError):
        drt.compute_dct(np.ones(10), np.ones(9), np.ones(10))


def test_compute_dct_raises_on_zero_impedance():
    freq = np.logspace(4, -2, 10)
    zre = np.zeros(10)
    zim = np.zeros(10)
    with pytest.raises(ValueError):
        drt.compute_dct(freq, zre, zim)


def test_compute_dct_extends_the_collocation_grid_beyond_the_measured_range():
    g_inf, gct, tau_yarc, phi = 0.05, 0.2, 1e-3, 0.8
    freq = np.logspace(4, -3, 60)
    omega = 2 * np.pi * freq
    y = g_inf + gct / (1 + (1j * omega * tau_yarc) ** phi)
    z = 1.0 / y

    result = drt.compute_dct(freq, z.real, z.imag, lambda_reg=1e-3)

    assert len(result.tau_s) > len(freq)
    assert len(result.tau_s) == len(result.gamma) == len(result.within_measured_range)
    assert len(result.frequency_hz) == len(freq)
    assert result.within_measured_range.sum() == len(freq)


def test_compute_dct_clean_yarc_spectrum_produces_no_warnings():
    g_inf, gct, tau_yarc, phi = 0.05, 0.2, 1e-3, 0.8
    freq = np.logspace(4, -3, 60)
    omega = 2 * np.pi * freq
    y = g_inf + gct / (1 + (1j * omega * tau_yarc) ** phi)
    z = 1.0 / y

    result = drt.compute_dct(freq, z.real, z.imag, lambda_reg=1e-3)
    assert result.warnings == []


def test_compute_dct_large_residual_produces_a_warning():
    freq = np.logspace(4, -2, 40)
    rng = np.random.default_rng(0)
    zre = rng.uniform(1, 50, size=len(freq))  # avoid exact zero impedance
    zim = rng.uniform(-50, 50, size=len(freq))
    result = drt.compute_dct(freq, zre, zim, lambda_reg=1e-3)
    assert result.residual_percent > 5.0
    assert any("residual is large" in w for w in result.warnings)


def test_compute_dct_does_not_universally_fix_a_series_topology_blocking_electrode_spectrum():
    """DCT is a complementary decomposition, not a guaranteed fix for
    every blocking-electrode spectrum: it fits well when the underlying
    admittance genuinely has a Maxwell-type (parallel-branches) structure
    (see the YARC test above), but a spectrum built as a SERIES
    combination (Rs + a ZARC + a series capacitor -- a Voigt-type
    topology, exactly what DRT itself is suited for) is not automatically
    well-represented by DCT's admittance model either. This is expected,
    honest behavior, not a bug -- documented so a future change doesn't
    "fix" this test by silently forcing DCT to always report a small
    residual regardless of whether the data actually supports it."""
    rs, rct, tau_zarc, phi = 5.0, 15.0, 5e-3, 0.85
    c_low = 2.0
    freq = np.logspace(4, -1.5, 60)
    omega = 2 * np.pi * freq
    z = rs + rct / (1 + (1j * omega * tau_zarc) ** phi) + 1.0 / (1j * omega * c_low)

    result = drt.compute_dct(freq, z.real, z.imag, lambda_reg=1e-3)
    assert result.residual_percent > 5.0
