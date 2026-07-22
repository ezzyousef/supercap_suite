"""
Distribution of Relaxation Times (DRT) analysis for EIS spectra.

Pure functions, no Qt imports (same convention as core/eis_analysis.py).

DRT is a non-parametric alternative/complement to equivalent-circuit
fitting: instead of assuming one specific circuit topology up front, it
recovers a continuous distribution gamma(ln tau) of relaxation-time
"weights" directly from the measured spectrum, such that

    Z_DRT(f) = R_inf + integral[ gamma(ln tau) / (1 + i*2*pi*f*tau) dlntau ]

reproduces the data (eq. 1-2 in the source below). Every parallel RC
element in an equivalent circuit shows up as one peak in gamma(ln tau) at
tau = R*C -- so a DRT plot is, informally, "what an equivalent circuit fit
would look like if you didn't have to commit to a specific circuit first."

Source (method + eq. numbers cited in each function's docstring below):
T.H. Wan, M. Saccoccio, C. Chen, F. Ciucci, "Influence of the
Discretization Methods on the Distribution of Relaxation Times
Deconvolution: Implementing Radial Basis Functions with DRTtools,"
Electrochimica Acta 184 (2015) 483-499 -- the paper behind DRTtools, the
standard open-source reference implementation in this field. This module
implements the paper's piecewise-linear (PWL) discretization case (their
eq. 5-6), not their RBF extension -- the paper's own abstract states PWL
and RBF give "comparable" results "at normal data collection range,"
which is the case this app is built for (a normal, complete-looking EIS
sweep, not a truncated/incomplete one, where the paper found RBF's
extended support helps more).

Peak physical-interpretation caveats (frequency-region explanations) are
based on: C. Plank et al., "A review of the distribution of relaxation
times method for the analysis of impedance spectra," Journal of Power
Sources 594 (2024) 233845 (see "Interpretation of peaks" and the
CPE/blocking-electrode discussion); and B. Py, A. Maradesa, F. Ciucci,
"From theory to practice: Unlocking the distribution of capacitive times
in electrochemical impedance spectroscopy," Electrochimica Acta 479
(2024) 143741 (documents that classical DRT is not well-suited to the
low-frequency behavior of BLOCKING-electrode systems -- i.e. exactly
supercapacitors and batteries -- because the DRT model's impedance
necessarily tends to a FINITE value as f->0, which cannot represent the
diverging/unbounded low-frequency impedance a real blocking electrode
shows; this shows up as an "increasing series of peaks" artifact mimicking
a CPE rather than one genuine low-frequency peak).
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np

try:
    from scipy.optimize import nnls
    from scipy.integrate import quad
    from scipy.signal import find_peaks
    _HAVE_SCIPY = True
except ImportError:
    _HAVE_SCIPY = False


@dataclass
class DRTPeak:
    tau_s: float
    frequency_hz: float
    gamma: float
    region: str
    explanation: str
    within_measured_range: bool = True


@dataclass
class DRTResult:
    tau_s: np.ndarray              # collocation grid, EXTENDED beyond the measured range (see compute_drt)
    gamma: np.ndarray              # same length as tau_s
    within_measured_range: np.ndarray  # bool array, same length as tau_s -- see compute_drt
    r_inf_ohm: float
    lambda_used: float
    frequency_hz: np.ndarray       # the MEASURED frequencies only -- matches model_z_re_ohm/model_z_im_ohm, NOT tau_s/gamma
    model_z_re_ohm: np.ndarray
    model_z_im_ohm: np.ndarray
    residual_percent: float
    peaks: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


# Practical, literature-informed frequency-region bands for interpreting
# DRT peaks -- NOT universal physical constants (no single tau cutoff is
# correct for every electrochemical system; the actual boundary between
# "charge transfer" and "diffusion" timescales depends on the specific
# electrode/electrolyte). These are the commonly-cited ORDER-OF-MAGNITUDE
# ranges from the DRT peak-interpretation literature (Plank et al. 2024
# and standard EIS textbook practice: fast interfacial kinetics at high
# frequency, progressively slower transport/diffusion processes at lower
# frequency) -- always cross-check against the Nyquist/Bode shape and the
# specific system's chemistry rather than trusting the label alone.
FREQUENCY_REGIONS = [
    (
        "High frequency (fast process)",
        0.0, 1e-3,
        "Typically charge-transfer / interfacial reaction kinetics and "
        "double-layer charging -- the fastest processes in the cell. "
        "A resistance-like (narrow, symmetric) peak here usually maps "
        "cleanly to a single Rct||C(or CPE) pair in an equivalent circuit.",
    ),
    (
        "Mid frequency (interfacial / distributed)",
        1e-3, 1.0,
        "Typically a combination of charge-transfer and double-layer "
        "effects, contact/grain-boundary resistance (solid electrodes), "
        "or porous-electrode effects. A BROADER peak here indicates a "
        "more DISTRIBUTED process (a range of local time constants, e.g. "
        "non-uniform pore sizes or surface heterogeneity) rather than one "
        "sharp relaxation.",
    ),
    (
        "Low frequency (slow / transport-limited)",
        1.0, float("inf"),
        "Typically diffusion or mass-transport-limited response (ion "
        "transport in the electrolyte/pores). IMPORTANT CAVEAT for "
        "blocking-electrode systems like supercapacitors: classical DRT "
        "cannot represent a truly diverging low-frequency impedance (its "
        "model impedance is mathematically forced to a FINITE value as "
        "f->0), so this often shows up as an ARTIFICIAL increasing series "
        "of peaks mimicking a CPE rather than one genuine low-frequency "
        "process -- treat isolated peaks in this region with caution and "
        "cross-check against the raw Nyquist/Bode shape (Py, Maradesa & "
        "Ciucci, Electrochimica Acta 479 (2024) 143741).",
    ),
]


def classify_region(tau_s: float) -> tuple[str, str]:
    """Returns (region_label, explanation) for a given relaxation time,
    using the practical FREQUENCY_REGIONS bands above."""
    for label, lo, hi, explanation in FREQUENCY_REGIONS:
        if lo <= tau_s < hi:
            return label, explanation
    return FREQUENCY_REGIONS[-1][0], FREQUENCY_REGIONS[-1][3]


def _hat_function_integral_re_im(tau_n: float, tau_m: float, y_lo: float, y_hi: float) -> tuple[float, float]:
    """Numerically integrates the m-th PWL ("hat"/"tent") basis function,
    centered at tau_m, against the RC-element kernel evaluated at the
    measurement time constant tau_n = 1/(2*pi*f_n) -- i.e. computes one
    (real, imaginary) entry pair of the A'/A'' design matrices from
    Wan et al. 2015, eq. (30)-(33). The hat function is triangular in
    y = ln(tau) - ln(tau_m), rising linearly from 0 at y_lo to 1 at y=0
    and back to 0 at y_hi (y_lo <= 0 <= y_hi always).

    This evaluates the general integral formula from eq. (32)-(33)
    numerically (via scipy.integrate.quad) rather than using a closed-form
    solution -- the source paper gives the general integral for an
    arbitrary basis function f_m but the closed form specific to the PWL
    "hat" shape is not spelled out there in elementary terms. Numerical
    quadrature is mathematically equivalent and is verified in this
    module's test suite by fitting a synthetic ZARC-element spectrum
    (closed-form DRT known exactly, see docs/EQUATIONS.md) and checking
    the peak position/shape is recovered.
    """
    def hat(y):
        if y <= y_lo or y >= y_hi:
            return 0.0
        if y <= 0:
            return 1.0 - y / y_lo
        return 1.0 - y / y_hi

    ratio_ln = np.log(tau_n / tau_m)

    def re_integrand(y):
        wt = np.exp(y - ratio_ln)  # omega*tau at this y, using tau = tau_m*exp(y), omega*tau_n cancels via tau_n/tau_m
        return hat(y) / (1.0 + wt ** 2)

    def im_integrand(y):
        wt = np.exp(y - ratio_ln)
        return hat(y) * (-wt) / (1.0 + wt ** 2)

    re_val, _ = quad(re_integrand, y_lo, y_hi, limit=100)
    im_val, _ = quad(im_integrand, y_lo, y_hi, limit=100)
    return re_val, im_val


def _build_extended_grid_and_kernels(tau_meas: np.ndarray) -> tuple:
    """Shared by compute_drt() and compute_dct(): builds the collocation
    grid EXTENDED beyond the measured tau range (see compute_drt's
    docstring for why -- the same edge-artifact concern applies equally
    to DCT), plus the PWL-basis/RC-kernel design matrices (a_re, a_im:
    shape (N measured, M extended collocation points)) and the second-
    difference regularization matrix (shape (M-2, M)) over the extended
    grid. Returns (tau, within_range, a_re, a_im, d)."""
    n = len(tau_meas)
    ln_tau_meas = np.log(tau_meas)
    median_step = float(np.median(np.diff(ln_tau_meas))) if n > 1 else 1.0
    n_extra = max(5, n // 5)
    extra_lo = ln_tau_meas[0] - median_step * np.arange(n_extra, 0, -1)
    extra_hi = ln_tau_meas[-1] + median_step * np.arange(1, n_extra + 1)
    ln_tau = np.concatenate([extra_lo, ln_tau_meas, extra_hi])
    tau = np.exp(ln_tau)
    within_range = np.concatenate([
        np.zeros(n_extra, dtype=bool), np.ones(n, dtype=bool), np.zeros(n_extra, dtype=bool),
    ])
    m_total = len(tau)

    a_re = np.zeros((n, m_total))
    a_im = np.zeros((n, m_total))
    for m in range(m_total):
        y_lo = ln_tau[m - 1] - ln_tau[m] if m > 0 else -(ln_tau[m + 1] - ln_tau[m])
        y_hi = ln_tau[m + 1] - ln_tau[m] if m < m_total - 1 else -(ln_tau[m - 1] - ln_tau[m])
        for k in range(n):
            re_val, im_val = _hat_function_integral_re_im(tau_meas[k], tau[m], y_lo, y_hi)
            a_re[k, m] = re_val
            a_im[k, m] = im_val

    d = np.zeros((max(m_total - 2, 0), m_total))
    for i in range(m_total - 2):
        d[i, i] = 1.0
        d[i, i + 1] = -2.0
        d[i, i + 2] = 1.0

    return tau, within_range, a_re, a_im, d


def compute_drt(frequency_hz: np.ndarray, z_re_ohm: np.ndarray, z_im_ohm: np.ndarray,
                 lambda_reg: float = 1e-3) -> "DRTResult":
    """Tikhonov-regularized DRT deconvolution using a piecewise-linear
    (PWL) discretization basis, one basis function per measured
    frequency (collocation points tau_m = 1/(2*pi*f_m)) -- following
    Wan, Saccoccio, Chen & Ciucci, "Influence of the Discretization
    Methods on the Distribution of Relaxation Times Deconvolution:
    Implementing Radial Basis Functions with DRTtools," Electrochimica
    Acta 184 (2015) 483-499 (the paper behind DRTtools, the standard
    open-source reference implementation). Uses the same
    inductive-loop-cropped, sign-normalized (frequency_hz, z_re_ohm,
    z_im_ohm) convention as every other calculation in the EIS tab.

    Regularization: penalizes the discrete SECOND difference of gamma
    across collocation points (a standard smoothness penalty -- eq. 11-12
    of the source paper use the norm of the first derivative; second-
    difference regularization is an equally standard and commonly offered
    alternative order in DRT toolboxes, chosen here because it does not
    require the closed-form derivative of the PWL basis function). Larger
    `lambda_reg` gives a smoother (less oscillatory) but potentially
    over-smoothed DRT; smaller gives a noisier but more detailed one.
    `lambda_reg` is a PRACTICAL DEFAULT here, not automatically optimized
    against the data (the source paper notes optimal-lambda selection,
    e.g. via re-im cross-validation, is itself a nontrivial choice) --
    always check whether the result changes qualitatively across a
    reasonable lambda range before trusting a specific peak.

    Non-negativity: gamma(ln tau) and R_inf are both solved for jointly
    via non-negative least squares (scipy.optimize.nnls) -- both are
    physically non-negative quantities, so this is a direct, dependency-
    free way to enforce the same physical constraint DRTtools enforces
    via a general bounded quadratic program.

    Raises ValueError if the input arrays are mismatched, have fewer than
    5 points, or scipy is unavailable.
    """
    if not _HAVE_SCIPY:
        raise ValueError("scipy is required for DRT analysis")
    f = np.asarray(frequency_hz, dtype=float)
    zre = np.asarray(z_re_ohm, dtype=float)
    zim = np.asarray(z_im_ohm, dtype=float)
    if not (len(f) == len(zre) == len(zim)):
        raise ValueError("frequency_hz, z_re_ohm, and z_im_ohm must be equal-length arrays")
    if len(f) < 5:
        raise ValueError("DRT analysis needs at least 5 frequency points")

    order = np.argsort(f)  # ascending frequency
    f_sorted = f[order]
    zre_sorted = zre[order]
    zim_sorted = zim[order]

    tau_meas = 1.0 / (2.0 * np.pi * f_sorted)
    tau_meas = tau_meas[::-1]  # ascending tau (descending frequency)
    zre_by_tau = zre_sorted[::-1]
    zim_by_tau = zim_sorted[::-1]
    f_by_tau = f_sorted[::-1]

    n = len(tau_meas)

    # Extend the collocation grid beyond the strictly measured tau range.
    # Basis functions compactly supported ONLY within [tau_min, tau_max]
    # force gamma to exactly zero at those edges -- if the true underlying
    # process's relaxation extends beyond what was actually measured
    # (very common for a supercapacitor's near-vertical low-frequency
    # capacitive tail, which implies relaxation times longer than the
    # measurement covered), the deconvolution has nowhere to put that
    # "missing" weight except a sharp, physically implausible spike
    # jammed into the very last edge collocation point. Extending the
    # grid a bit past each measured boundary -- the same idea Wan et al.
    # 2015 sec. 2.1 highlight as an advantage of RBF discretization's
    # naturally infinite support, applied here to PWL via a handful of
    # extra collocation points at the same log-spacing as the measured
    # grid -- gives that mass room to spread out naturally instead of
    # being clipped into one artificial spike. Peaks landing in the
    # extended region are flagged (DRTPeak.within_measured_range=False):
    # they are less certain than a peak directly constrained by data,
    # since no measurement was actually taken there.
    tau, within_range, a_re, a_im, d = _build_extended_grid_and_kernels(tau_meas)
    m_total = len(tau)

    # Design matrix: column 0 is R_inf (contributes 1 to every real-part
    # row, 0 to imaginary/regularization rows); columns 1..m_total are
    # the DRT weights gamma_m over the extended grid.
    n_reg = d.shape[0]
    design = np.zeros((2 * n + n_reg, 1 + m_total))
    design[:n, 0] = 1.0
    design[:n, 1:] = a_re
    design[n:2 * n, 1:] = a_im
    design[2 * n:, 1:] = np.sqrt(lambda_reg) * d
    target = np.concatenate([zre_by_tau, zim_by_tau, np.zeros(n_reg)])

    coeffs, _ = nnls(design, target)
    r_inf = coeffs[0]
    gamma = coeffs[1:]

    model_re = r_inf + a_re @ gamma
    model_im = a_im @ gamma
    z_mag = np.sqrt(zre_by_tau ** 2 + zim_by_tau ** 2)
    z_mag = np.where(z_mag == 0, np.finfo(float).eps, z_mag)
    residual_percent = float(np.sqrt(np.mean(
        ((zre_by_tau - model_re) ** 2 + (zim_by_tau - model_im) ** 2) / z_mag ** 2
    )) * 100.0)

    peaks_idx, _ = find_peaks(gamma, prominence=max(gamma.max() * 0.02, 1e-12))
    peaks = []
    for idx in peaks_idx:
        region, explanation = classify_region(tau[idx])
        peaks.append(DRTPeak(
            tau_s=float(tau[idx]), frequency_hz=float(1.0 / (2.0 * np.pi * tau[idx])),
            gamma=float(gamma[idx]), region=region, explanation=explanation,
            within_measured_range=bool(within_range[idx]),
        ))

    result_warnings = []
    # Even with the extended grid above, a real blocking-electrode (i.e.
    # supercapacitor/battery) low-frequency capacitive tail that the
    # measurement didn't extend low enough to fully resolve will keep
    # gamma RISING all the way to the largest tau collocation point
    # (never turning over into a proper peak, since no true local maximum
    # exists within the computed range) -- this is the documented
    # "increasing series of peaks" signature for blocking electrodes (Py,
    # Maradesa & Ciucci 2024), not a numerical bug. Flag it explicitly
    # rather than let it pass as an unremarkable-looking rising tail.
    if gamma.max() > 0 and gamma[-1] > 0.3 * gamma.max():
        result_warnings.append(
            "gamma is still RISING at the largest relaxation times computed (even after "
            "extending the collocation grid past the measured range) -- the low-frequency "
            "process is likely not fully resolved. This is the expected signature for "
            "blocking-electrode systems (supercapacitors, batteries) whose near-vertical "
            "low-frequency Nyquist tail a bounded DRT model cannot fully represent -- "
            "extending the measurement to lower frequency would help; treat this region's "
            "peak count/shape with caution in the meantime."
        )
    if residual_percent > 5.0:
        result_warnings.append(
            f"Model residual is large ({residual_percent:.3g}% RMS) -- try a different "
            "lambda, check for an unremoved inductive loop, or check the data for noise issues."
        )

    return DRTResult(
        tau_s=tau, gamma=gamma, within_measured_range=within_range,
        r_inf_ohm=float(r_inf), lambda_used=lambda_reg,
        frequency_hz=f_by_tau, model_z_re_ohm=model_re, model_z_im_ohm=model_im,
        residual_percent=residual_percent, peaks=peaks, warnings=result_warnings,
    )


def compute_drt_with_dct_recommendation(frequency_hz: np.ndarray, z_re_ohm: np.ndarray,
                                         z_im_ohm: np.ndarray, lambda_reg: float = 1e-3) -> "DRTResult":
    """Runs compute_drt() and, ONLY if it raised any warning (the rising-
    tail blocking-electrode signature, a large residual, or both),
    automatically ALSO runs compute_dct() on the same data as a direct,
    actionable cross-check -- rather than leaving the user to discover
    DCT (or that switching to it would NOT help either) only after
    already seeing a warning with no obvious next step. Appends one more
    entry to the returned DRTResult.warnings:
      - if DCT fits substantially better (>=20% lower residual): tells
        the user to switch this tab's Method dropdown to DCT;
      - otherwise: tells the user DCT does not help either, and suggests
        checking the raw Nyquist/Bode shape or the Kramers-Kronig test
        instead, since neither decomposition may suit this spectrum
        (reproduced directly: a series-topology blocking-electrode
        spectrum where DCT fits WORSE than DRT, not better -- see
        compute_dct's own docstring and tests -- so this comparison must
        never assume DCT is the fix, only check it).

    Silently falls back to the plain compute_drt() result (no extra
    warning) if compute_dct() itself raises for this data.
    """
    result = compute_drt(frequency_hz, z_re_ohm, z_im_ohm, lambda_reg=lambda_reg)
    if not result.warnings:
        return result
    try:
        dct_result = compute_dct(frequency_hz, z_re_ohm, z_im_ohm, lambda_reg=lambda_reg)
    except ValueError:
        return result
    if dct_result.residual_percent < result.residual_percent * 0.8:
        result.warnings.append(
            f"Automatically tried DCT (the admittance-domain method built for exactly this "
            f"kind of blocking-electrode case) as a cross-check: it fits this spectrum "
            f"substantially better ({dct_result.residual_percent:.3g}% residual vs "
            f"{result.residual_percent:.3g}% for DRT). Switch this tab's Method dropdown to "
            f"DCT and re-run to use it."
        )
    else:
        result.warnings.append(
            f"Also tried DCT automatically as a cross-check: it does not fit this spectrum "
            f"notably better either ({dct_result.residual_percent:.3g}% residual). Neither "
            f"decomposition may be well-suited to this data -- check the raw Nyquist/Bode "
            f"shape directly, or run the Kramers-Kronig validity test (EIS tab) to check "
            f"whether the measurement itself is self-consistent."
        )
    return result


@dataclass
class DCTPeak:
    tau_s: float
    frequency_hz: float
    gamma: float
    region: str
    explanation: str
    within_measured_range: bool = True


@dataclass
class DCTResult:
    tau_s: np.ndarray              # collocation grid, EXTENDED beyond the measured range (see compute_drt)
    gamma: np.ndarray              # same length as tau_s
    within_measured_range: np.ndarray  # bool array, same length as tau_s
    g0_s: float                    # zero-frequency conductance
    c0_f: float                    # instantaneous/high-frequency capacitance
    lambda_used: float
    frequency_hz: np.ndarray       # the MEASURED frequencies only
    model_y_re_s: np.ndarray
    model_y_im_s: np.ndarray
    residual_percent: float
    peaks: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def compute_dct(frequency_hz: np.ndarray, z_re_ohm: np.ndarray, z_im_ohm: np.ndarray,
                 lambda_reg: float = 1e-3) -> "DCTResult":
    """Distribution of Capacitive Times (DCT): the ADMITTANCE-domain
    counterpart to compute_drt(), purpose-built for BLOCKING-electrode
    systems -- i.e. exactly supercapacitors and batteries -- where
    classical DRT structurally cannot represent the data well. compute_drt()
    fits Z(f) = R_inf + integral[gamma_DRT/(1+j*2*pi*f*tau) dlntau], whose
    model impedance is mathematically forced to a FINITE value as f->0;
    a real blocking electrode's impedance instead keeps growing
    (unbounded) toward DC (the near-vertical low-frequency Nyquist tail),
    which DRT can only approximate by piling gamma up in an ever-
    increasing series of peaks toward the largest computed tau rather
    than resolving one genuine feature (compute_drt() detects and warns
    about exactly this pattern). DCT sidesteps the problem by fitting the
    ADMITTANCE Y(f) = 1/Z(f) instead, whose model

        Y_DCT(f) = j*2*pi*f*C0 + G0 + integral[ gamma_DCT(ln tau) / (1 + j*2*pi*f*tau) dlntau ]

    (eq. 2-3 in the source below) tends to a FINITE admittance (not
    impedance) as f->0 -- exactly the behavior a blocking electrode's
    admittance actually has (Y->0, i.e. Z->infinity, as f->0 is
    perfectly representable: it just means G0 and gamma_DCT's total mass
    are small). Uses the SAME piecewise-linear/extended-grid/Tikhonov/
    NNLS machinery as compute_drt() (see that function's docstring for
    the discretization and regularization details), just applied to Y
    instead of Z, with an added free parameter C0 (the DCT counterpart to
    DRT's R_inf) capturing the instantaneous/high-frequency capacitance.

    Source: B. Py, A. Maradesa, F. Ciucci, "From theory to practice:
    Unlocking the distribution of capacitive times in electrochemical
    impedance spectroscopy," Electrochimica Acta 479 (2024) 143741,
    eq. 2-3 for the admittance model. G0 and C0 are both solved for
    jointly with gamma_DCT via non-negative least squares -- both are
    physically non-negative quantities (a conductance and a
    capacitance), the same reasoning compute_drt() uses for R_inf.

    Raises ValueError if the input arrays are mismatched, have fewer than
    5 points, contain a zero impedance (undefined admittance), or scipy
    is unavailable.
    """
    if not _HAVE_SCIPY:
        raise ValueError("scipy is required for DCT analysis")
    f = np.asarray(frequency_hz, dtype=float)
    zre = np.asarray(z_re_ohm, dtype=float)
    zim = np.asarray(z_im_ohm, dtype=float)
    if not (len(f) == len(zre) == len(zim)):
        raise ValueError("frequency_hz, z_re_ohm, and z_im_ohm must be equal-length arrays")
    if len(f) < 5:
        raise ValueError("DCT analysis needs at least 5 frequency points")
    z_complex = zre + 1j * zim
    if np.any(z_complex == 0):
        raise ValueError("Z=0 encountered -- cannot compute the admittance Y=1/Z for DCT analysis")

    order = np.argsort(f)  # ascending frequency
    f_sorted = f[order]
    y_sorted = 1.0 / z_complex[order]

    tau_meas = 1.0 / (2.0 * np.pi * f_sorted)
    tau_meas = tau_meas[::-1]  # ascending tau (descending frequency)
    yre_by_tau = y_sorted.real[::-1]
    yim_by_tau = y_sorted.imag[::-1]
    f_by_tau = f_sorted[::-1]
    omega_by_tau = 2.0 * np.pi * f_by_tau

    n = len(tau_meas)
    tau, within_range, a_re, a_im, d = _build_extended_grid_and_kernels(tau_meas)
    m_total = len(tau)

    # Design matrix: column 0 is G0 (contributes 1 to every real-part
    # row), column 1 is C0 (contributes omega to every imaginary-part
    # row -- Im(Y) = omega*C0 for a plain capacitor's admittance);
    # columns 2..m_total+1 are the DCT weights gamma_m over the extended grid.
    n_reg = d.shape[0]
    design = np.zeros((2 * n + n_reg, 2 + m_total))
    design[:n, 0] = 1.0
    design[n:2 * n, 1] = omega_by_tau
    design[:n, 2:] = a_re
    design[n:2 * n, 2:] = a_im
    design[2 * n:, 2:] = np.sqrt(lambda_reg) * d
    target = np.concatenate([yre_by_tau, yim_by_tau, np.zeros(n_reg)])

    coeffs, _ = nnls(design, target)
    g0 = coeffs[0]
    c0 = coeffs[1]
    gamma = coeffs[2:]

    model_re = g0 + a_re @ gamma
    model_im = omega_by_tau * c0 + a_im @ gamma
    y_mag = np.sqrt(yre_by_tau ** 2 + yim_by_tau ** 2)
    y_mag = np.where(y_mag == 0, np.finfo(float).eps, y_mag)
    residual_percent = float(np.sqrt(np.mean(
        ((yre_by_tau - model_re) ** 2 + (yim_by_tau - model_im) ** 2) / y_mag ** 2
    )) * 100.0)

    peaks_idx, _ = find_peaks(gamma, prominence=max(gamma.max() * 0.02, 1e-12))
    peaks = []
    for idx in peaks_idx:
        region, explanation = classify_region(tau[idx])
        peaks.append(DCTPeak(
            tau_s=float(tau[idx]), frequency_hz=float(1.0 / (2.0 * np.pi * tau[idx])),
            gamma=float(gamma[idx]), region=region, explanation=explanation,
            within_measured_range=bool(within_range[idx]),
        ))

    result_warnings = []
    if gamma.max() > 0 and gamma[-1] > 0.3 * gamma.max():
        result_warnings.append(
            "gamma is still RISING at the largest relaxation times computed (even after "
            "extending the collocation grid past the measured range) -- unlike DRT, this is "
            "NOT the expected signature for a blocking electrode (DCT is specifically built "
            "to represent that case without a rising tail); a genuinely still-rising DCT tail "
            "more likely means the measurement itself didn't extend to low enough frequency to "
            "resolve this process at all, or there's a modeling/data issue worth checking."
        )
    if residual_percent > 5.0:
        result_warnings.append(
            f"Model residual is large ({residual_percent:.3g}% RMS) -- try a different "
            "lambda, check for an unremoved inductive loop, or check the data for noise issues."
        )

    return DCTResult(
        tau_s=tau, gamma=gamma, within_measured_range=within_range,
        g0_s=float(g0), c0_f=float(c0), lambda_used=lambda_reg,
        frequency_hz=f_by_tau, model_y_re_s=model_re, model_y_im_s=model_im,
        residual_percent=residual_percent, peaks=peaks, warnings=result_warnings,
    )


def analytical_zarc_drt(tau_s: np.ndarray, rct_ohm: float, tau_zarc_s: float, phi: float) -> np.ndarray:
    """Exact closed-form DRT of a single ZARC element (Z = Rct / (1 +
    (i*2*pi*f*tau_zarc)^phi), i.e. a resistor in parallel with a CPE):

        gamma(ln tau) = Rct * sin(pi*(1-phi)) /
            (2*pi * (cosh(phi*ln(tau/tau_zarc)) - cos(pi*(1-phi))))

    This is the standard ZARC/Cole-Cole DRT closed form reproduced across
    the DRT literature (e.g. Schichlein et al., J. Appl. Electrochem. 32
    (2002) 875; Boukamp, "Fourier Transform Distribution Function of
    Relaxation Times," Solid State Ionics). The specific source PDF in
    this project's reference material (Py, Maradesa & Ciucci,
    Electrochimica Acta 479 (2024) 143741, eq. 10) states an equivalent
    formula, but its printed equation could not be reliably transcribed
    from this project's extracted PDF text (the two-column layout's OCR
    interleaved characters from adjacent columns across the equation).
    Rather than risk transcribing a garbled equation, this formula was
    independently verified by forward-integration: computing
    integral[gamma(ln tau)/(1+i*2*pi*f*tau) dlntau] numerically at several
    frequencies and confirming it reproduces Rct/(1+(i*2*pi*f*tau_zarc)^phi)
    to 5 decimal places for phi in (0,1) -- see the corresponding test.

    Used only as a ground-truth reference for self-consistency testing
    compute_drt() (no closed-form DRT exists for most real circuits, so
    this is one of the few cases the numerical deconvolution can be
    checked against exactly) and, in the UI, as an optional overlay so a
    user fitting a single-semicircle-like feature can sanity-check the
    numerical DRT's peak shape against the ideal case. phi=1 recovers an
    ideal (non-distributed) RC element, a Dirac delta in the limit --
    this formula is only meaningful for 0 < phi < 1.
    """
    tau = np.asarray(tau_s, dtype=float)
    if not (0.0 < phi < 1.0):
        raise ValueError("phi must be strictly between 0 and 1 for the ZARC DRT closed form")
    x = phi * np.log(tau / tau_zarc_s)
    return rct_ohm * np.sin(np.pi * (1.0 - phi)) / (2.0 * np.pi * (np.cosh(x) - np.cos(np.pi * (1.0 - phi))))
