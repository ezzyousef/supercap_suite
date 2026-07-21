"""
Electrochemical impedance spectroscopy (EIS) analysis.

Pure functions, no Qt imports.
"""
from dataclasses import dataclass
import numpy as np

try:
    from scipy.optimize import least_squares
    _HAVE_SCIPY = True
except ImportError:
    _HAVE_SCIPY = False


def capacitance_from_eis(z_imag_ohm: float, frequency_hz: float, mass_g: float | None = None) -> float:
    """Capacitance from the imaginary part of impedance at a given
    frequency:

        C = -1 / (2 * pi * f * Z'')

    Typically evaluated at the lowest measured frequency to approximate
    near-DC capacitive behavior. z_imag_ohm is expected negative for
    capacitive behavior (standard EIS sign convention: -Im(Z) positive is
    often plotted instead -- check which sign convention your data uses
    before calling this). Returns capacitance in Farads; if mass_g is
    given, returns specific capacitance in F/g instead.
    """
    if frequency_hz <= 0:
        raise ValueError("frequency_hz must be positive")
    if z_imag_ohm == 0:
        raise ValueError("z_imag_ohm cannot be zero (division by zero)")
    c = -1.0 / (2 * np.pi * frequency_hz * z_imag_ohm)
    if mass_g is not None:
        if mass_g <= 0:
            raise ValueError("mass_g must be positive")
        return c / mass_g
    return c


def equivalent_series_resistance_from_nyquist(z_re_ohm: np.ndarray, z_im_ohm: np.ndarray) -> float:
    """Estimate ESR (ohm) as the real-axis intercept of the Nyquist plot: the
    Z_re value at the point of minimum |Z_im|.

    CAUTION: for a spectrum that traces a full closed semicircle (no
    low-frequency capacitive tail), BOTH ends touch the real axis
    (Z_im ~ 0 at both the high-frequency AND low-frequency ends), and this
    simple global-minimum search can pick the wrong one. If you have the
    frequency array, use `high_frequency_intercept_from_nyquist` instead,
    which restricts the search to the high-frequency portion of the sweep
    where the ESR/high-frequency intercept is conventionally defined. This
    function is kept for cases where frequency isn't available and is a
    simple nearest-point estimate, not a fitted equivalent-circuit
    extraction.
    """
    z_re_ohm = np.asarray(z_re_ohm, dtype=float)
    z_im_ohm = np.asarray(z_im_ohm, dtype=float)
    if len(z_re_ohm) != len(z_im_ohm) or len(z_re_ohm) == 0:
        raise ValueError("z_re_ohm and z_im_ohm must be equal-length, non-empty arrays")
    idx = int(np.argmin(np.abs(z_im_ohm)))
    return float(z_re_ohm[idx])


def high_frequency_intercept_from_nyquist(frequency_hz: np.ndarray, z_re_ohm: np.ndarray,
                                           z_im_ohm: np.ndarray, top_fraction: float = 0.3) -> float:
    """Estimate the HIGH-FREQUENCY real-axis intercept (the conventional
    ESR / R_s value) by restricting the "minimum |Z_im|" search to the
    highest-frequency `top_fraction` of the data points, rather than
    searching the whole spectrum.

    This avoids the ambiguity in `equivalent_series_resistance_from_nyquist`
    for spectra that form a full closed semicircle (which also touches the
    real axis at the LOW-frequency end, at Rs+Rct) -- restricting to the
    high-frequency region ensures the high-frequency intercept (Rs) is the
    one found, matching the standard "ESR is measured at the
    highest-frequency real-axis crossing" convention.

    `top_fraction` = 0.3 means: search only the 30% of points with the
    highest frequency. If your data has very few points, this may include
    only 1-2 points; that's fine since the ESR is a single-point read.
    """
    f = np.asarray(frequency_hz, dtype=float)
    zr = np.asarray(z_re_ohm, dtype=float)
    zi = np.asarray(z_im_ohm, dtype=float)
    if not (len(f) == len(zr) == len(zi)) or len(f) == 0:
        raise ValueError("frequency_hz, z_re_ohm, and z_im_ohm must be equal-length, non-empty arrays")
    if not (0 < top_fraction <= 1):
        raise ValueError("top_fraction must be in (0, 1]")

    n_keep = max(1, int(np.ceil(len(f) * top_fraction)))
    order = np.argsort(-f)  # descending frequency
    hf_idx = order[:n_keep]
    local_idx = hf_idx[np.argmin(np.abs(zi[hf_idx]))]
    return float(zr[local_idx])


# ---------------------------------------------------------------------------
# Ionic conductivity
# ---------------------------------------------------------------------------

def ionic_conductivity_s_per_cm(bulk_resistance_ohm: float, thickness_cm: float,
                                 area_cm2: float) -> float:
    """Ionic conductivity (S/cm) of an electrolyte/gel from a two-electrode
    ion-blocking-cell EIS measurement:

        sigma = L / (R * A)

    where L is the electrolyte thickness/gap (cm), R is the bulk
    resistance (ohm, typically the high-frequency real-axis intercept of
    the Nyquist plot), and A is the electrode contact area (cm^2).

    Source: present verbatim (as eqn 4 / eqn 10 respectively) in two
    independent source PDFs in this project (RSC gel-electrolyte paper;
    Chemical Engineering Journal gel-electrolyte paper), both citing the
    same two-electrode ion-blocking-cell convention.
    """
    if bulk_resistance_ohm <= 0:
        raise ValueError("bulk_resistance_ohm must be positive")
    if thickness_cm <= 0 or area_cm2 <= 0:
        raise ValueError("thickness_cm and area_cm2 must be positive")
    return thickness_cm / (bulk_resistance_ohm * area_cm2)


def bulk_resistance_from_nyquist(z_re_ohm: np.ndarray, z_im_ohm: np.ndarray,
                                  frequency_hz: np.ndarray | None = None) -> float:
    """Estimate the bulk/high-frequency resistance (ohm) for an ionic-
    conductivity calculation as the real-axis intercept -- the Z_re value
    where the Nyquist curve crosses (or comes closest to) Z_im = 0.

    If `frequency_hz` is supplied, uses `high_frequency_intercept_from_nyquist`
    to correctly restrict the search to the high-frequency portion of the
    spectrum (recommended -- avoids ambiguity for closed-semicircle spectra
    that also touch the real axis at the low-frequency end). If frequency
    isn't available, falls back to the simple global-minimum search via
    `equivalent_series_resistance_from_nyquist`, which can be ambiguous in
    that case.
    """
    if frequency_hz is not None:
        return high_frequency_intercept_from_nyquist(frequency_hz, z_re_ohm, z_im_ohm)
    return equivalent_series_resistance_from_nyquist(z_re_ohm, z_im_ohm)


# ---------------------------------------------------------------------------
# Series inductance removal (cable/connector high-frequency artifact)
# ---------------------------------------------------------------------------
#
# A stray series inductance (test-lead/cable/connector geometry, not a
# property of the cell) adds Z_L = j*omega*L in series with everything
# else, which only ever affects the IMAGINARY part of the impedance --
# Re(Z) is untouched by a pure inductor. On a standard Nyquist plot
# (-Im(Z) vs. Re(Z)) this shows up as the trace dipping BELOW the real
# axis at the highest frequencies (an "inductive loop"), since Im(Z)
# becomes positive there instead of the usual negative/capacitive sign.
# This is a well-known, standard EIS artifact -- see e.g. Metrohm/Autolab
# Application Note AN-EIS-004 (already cited in circuit_library.py for
# this app's optional series-L toggle on every preset circuit) and
# BioLogic EC-Lab's own "modified inductor" element (this app's "La",
# also cross-checked against EC-Lab's manual). Subtracting a known/fitted
# L from the raw data is a standard preprocessing step to see the
# underlying (semicircle/diffusion) response without it.

def _count_leading_positive(values_high_to_low_freq: np.ndarray) -> int:
    """How many points, walking down from the highest frequency, are
    consecutively > 0 before the first non-positive one. Shared by
    fit_inductance_from_high_frequency and inductive_point_count so the
    UI's "N points used" diagnostic always matches what the fit itself
    actually used."""
    n = 0
    for val in values_high_to_low_freq:
        if val > 0:
            n += 1
        else:
            break
    return n


def inductive_point_count(frequency_hz: np.ndarray, z_im_ohm: np.ndarray) -> int:
    """How many points fit_inductance_from_high_frequency would use for
    THIS spectrum -- exposed separately so a caller (e.g. the EIS tab's
    auto-detect button) can report it to the user as a fit-confidence
    signal ("fit from only 3 points" is far less trustworthy than "fit
    from 15 points") without duplicating the point-selection logic."""
    f = np.asarray(frequency_hz, dtype=float)
    zi = np.asarray(z_im_ohm, dtype=float)
    if len(f) != len(zi) or len(f) == 0:
        return 0
    order = np.argsort(-f)
    return _count_leading_positive(zi[order])


def fit_inductance_from_high_frequency(frequency_hz: np.ndarray, z_im_ohm: np.ndarray,
                                        min_points: int = 3) -> float:
    """Estimate a series inductance (H) from the portion of the spectrum
    where Im(Z) is POSITIVE -- the genuinely inductive region. A capacitor
    or CPE (0 < n <= 1) can only ever contribute a NEGATIVE imaginary
    part, so a positive Im(Z) cannot be explained by anything else in a
    normal EDLC/pseudocapacitive circuit and is unambiguous evidence of
    inductance. Using a fixed high-frequency fraction instead was tried
    first and rejected: for a small inductance relative to the rest of
    the circuit's own frequency-dependent imaginary contribution, the
    top-N-percent window can still be dominated by the CPE's own
    curvature rather than the inductive signal, producing a badly wrong
    (even wrong-SIGN) fitted L -- confirmed by a synthetic test where
    "top 15% by frequency" recovered L off by more than 10x with the
    wrong sign.

    Only a CONTIGUOUS run of Im(Z) > 0 points starting from the HIGHEST
    frequency is used, not every Im(Z) > 0 point anywhere in the
    spectrum: a genuine inductive artifact is confined to the highest-
    frequency end of a real spectrum, so as soon as a point's Im(Z) drops
    back to <= 0 walking down in frequency, everything past that is
    outside the inductive region. An ISOLATED Im(Z) > 0 point elsewhere
    (e.g. a single noisy point near the low-frequency end, common on a
    real noisy spectrum) is measurement noise, not inductance -- letting
    it into the same zero-intercept regression as the real high-frequency
    points can visibly distort the fitted L (confirmed: a synthetic
    spectrum with 10 genuine high-frequency inductive points plus 4
    scattered low-frequency noise points elsewhere biased the old
    all-points fit measurably versus the true L, and applying that biased
    L then visibly deformed the LOW-frequency part of the corrected curve
    it should never have touched -- this is the "removing inductance
    destroys the curve" failure mode). Restricting to the contiguous
    high-frequency run removes that contamination entirely.

    Once restricted, Im(Z) ~= omega*L is fit as a zero-intercept
    least-squares slope of Im(Z) vs. omega.

    Raises ValueError if fewer than `min_points` CONSECUTIVE points from
    the highest frequency have Im(Z) > 0 -- i.e. this spectrum doesn't
    show a genuine inductive loop (or not enough of one to fit reliably),
    which is itself useful information: don't "remove" an inductance that
    was never actually there.
    """
    f = np.asarray(frequency_hz, dtype=float)
    zi = np.asarray(z_im_ohm, dtype=float)
    if len(f) != len(zi) or len(f) == 0:
        raise ValueError("frequency_hz and z_im_ohm must be equal-length, non-empty arrays")

    # Work in strictly descending-frequency order regardless of how the
    # caller's arrays were ordered, so "contiguous from the highest
    # frequency" is well-defined even if the input isn't pre-sorted.
    order = np.argsort(-f)
    f_sorted = f[order]
    zi_sorted = zi[order]
    n_contiguous = _count_leading_positive(zi_sorted)

    if n_contiguous < min_points:
        raise ValueError(
            f"No inductive loop found (need at least {min_points} CONSECUTIVE points from the "
            f"highest frequency with Im(Z) > 0, found {n_contiguous}) -- this spectrum doesn't "
            "show a high-frequency inductive artifact to remove, or it's too small/noisy to "
            "fit reliably."
        )
    omega = 2 * np.pi * f_sorted[:n_contiguous]
    zi_sel = zi_sorted[:n_contiguous]
    denom = float(np.sum(omega ** 2))
    if denom <= 0:
        raise ValueError("Cannot fit an inductance from a single (or zero-frequency) point")
    return float(np.sum(omega * zi_sel) / denom)


def remove_inductance(frequency_hz: np.ndarray, z_re_ohm: np.ndarray, z_im_ohm: np.ndarray,
                       inductance_h: float) -> tuple[np.ndarray, np.ndarray]:
    """Subtract a series inductance's contribution from measured impedance
    data: Z_corrected = Z_measured - j*omega*L. Re(Z) is returned
    unchanged (a pure inductor has no real part); only Im(Z) is corrected.
    `inductance_h` may be negative (subtracting a negative L adds
    impedance back) -- this function does not assume its sign.
    """
    f = np.asarray(frequency_hz, dtype=float)
    zre = np.asarray(z_re_ohm, dtype=float)
    zim = np.asarray(z_im_ohm, dtype=float)
    if not (len(f) == len(zre) == len(zim)):
        raise ValueError("frequency_hz, z_re_ohm, and z_im_ohm must be equal-length arrays")
    omega = 2 * np.pi * f
    zim_corrected = zim - omega * inductance_h
    return zre.copy(), zim_corrected


def crop_inductive_loop_points(frequency_hz: np.ndarray, z_re_ohm: np.ndarray,
                                z_im_ohm: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Simpler alternative to remove_inductance()/fit_inductance_from_high_
    frequency(): instead of estimating a series inductance L and
    subtracting j*omega*L from every point (which depends on how
    precisely L can be fit -- an imprecise fit was found to visibly
    distort the corrected curve, see remove_inductance's history), this
    just DELETES the contiguous run of points with Im(Z) > 0 starting
    from the highest frequency -- i.e. the actual inductive loop itself
    -- and returns the remaining (freq, z_re, z_im) arrays, shorter than
    the input by however many points were removed. No inductance value
    is estimated or subtracted anywhere, so there's nothing to get
    slightly wrong: every remaining point is untouched raw data.

    This is a legitimate, commonly-used practical approach when the
    inductive loop is a minor cable/connector artifact not worth
    modeling explicitly (as opposed to the "L-" circuit variants in
    circuit_library.py, which fit L as part of a full CNLS circuit fit
    -- appropriate when the inductance itself needs to be reported as a
    result, not just discarded).

    Returns the input arrays UNCHANGED (as copies) if there's no
    contiguous positive run at the highest frequency at all -- i.e. this
    is a safe no-op on a spectrum with no inductive loop, never raises.
    """
    f = np.asarray(frequency_hz, dtype=float)
    zre = np.asarray(z_re_ohm, dtype=float)
    zim = np.asarray(z_im_ohm, dtype=float)
    if not (len(f) == len(zre) == len(zim)):
        raise ValueError("frequency_hz, z_re_ohm, and z_im_ohm must be equal-length arrays")
    if len(f) == 0:
        return f.copy(), zre.copy(), zim.copy()

    order = np.argsort(-f)
    f_sorted, zre_sorted, zim_sorted = f[order], zre[order], zim[order]
    n_drop = _count_leading_positive(zim_sorted)
    return f_sorted[n_drop:].copy(), zre_sorted[n_drop:].copy(), zim_sorted[n_drop:].copy()


# ---------------------------------------------------------------------------
# Equivalent circuit fitting (complex nonlinear least squares)
# ---------------------------------------------------------------------------
#
# The element formulas and the ~100-circuit preset library (Randles
# variants, blocking electrodes, two/three time-constant circuits, finite
# Warburg Wo/Ws, the de Levie transmission-line/porous-electrode model,
# and Gerischer elements) live in core/circuit_library.py, which documents
# where each formula convention was verified from. This module just wires
# that generic tree-based circuit engine into the CNLS (complex nonlinear
# least-squares) fitting routine and the EquivalentCircuitFitResult shape
# the rest of the app already expects.

from . import circuit_library as _cl

CIRCUIT_MODELS = _cl.all_circuit_names()
CIRCUIT_DISPLAY_NAMES = {name: spec.display for name, spec in _cl.CIRCUITS.items()}
CIRCUIT_CATEGORIES = {name: spec.category for name, spec in _cl.CIRCUITS.items()}


@dataclass
class EquivalentCircuitFitResult:
    model: str
    params: dict            # fitted parameter values, keyed by name
    param_errors: dict      # 1-sigma standard errors from the covariance estimate (or NaN if unavailable)
    chi_squared: float
    reduced_chi_squared: float
    z_fit_re: np.ndarray
    z_fit_im: np.ndarray
    warnings: list = None   # human-readable per-parameter warnings, e.g. a parameter pinned at its search bound

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []

    @property
    def display_name(self) -> str:
        return CIRCUIT_DISPLAY_NAMES.get(self.model, self.model)


def fit_equivalent_circuit(frequency_hz: np.ndarray, z_re_ohm: np.ndarray, z_im_ohm: np.ndarray,
                            model: str = "randles1_Q_none",
                            max_nfev: int | None = None,
                            multistart: bool = False) -> EquivalentCircuitFitResult:
    """Fit a Nyquist spectrum to one circuit from the core.circuit_library
    preset library via complex nonlinear least squares (scipy.optimize.
    least_squares on the STACKED real+imaginary residuals simultaneously --
    not two independent real/imaginary fits).

    `model`: any name in CIRCUIT_MODELS (~110 circuits; see
    core/circuit_library.py for the full library and its categories). Use
    `auto_fit_equivalent_circuit` to try many of them and keep the best fit
    instead of picking one by hand.

    z_im_ohm should be the signed imaginary part of impedance as measured
    (commonly negative for capacitive systems) -- this function does not
    flip signs for you; check your data's convention first.

    `multistart`: when True, also tries the heuristic guess with its
    Y0/B/C-kind parameters (CPE admittance, Warburg length, capacitance --
    the parameters most prone to landing an order of magnitude off, since
    several of them can independently produce "capacitive-like" behavior
    toward low frequency and are easily confused for each other from a
    single cold start) scaled by a few different multipliers, and keeps
    whichever converges to the lowest residual. Off by default (used for
    single-circuit fits, i.e. the EIS tab's "Fit this circuit" button and
    auto_fit_equivalent_circuit's final polish of its winner) because it
    costs several extra fits -- too slow to also apply to auto-fit's ~110
    -circuit screening pass, which instead approximates multi-start by
    trying many circuit TOPOLOGIES.

    Requires scipy. Initial parameter guesses are constructed heuristically
    from the data (see circuit_library.initial_guess_and_bounds) -- for
    difficult/noisy spectra a single run can still converge to a local
    minimum; `multistart=True` mitigates but does not eliminate this.
    """
    if not _HAVE_SCIPY:
        raise ImportError("scipy is required for equivalent circuit fitting "
                           "(pip install scipy)")
    f = np.asarray(frequency_hz, dtype=float)
    zr = np.asarray(z_re_ohm, dtype=float)
    zi = np.asarray(z_im_ohm, dtype=float)
    if not (len(f) == len(zr) == len(zi)):
        raise ValueError("frequency_hz, z_re_ohm, and z_im_ohm must be the same length")
    if len(f) < 4:
        raise ValueError("Need at least 4 frequency points for a stable circuit fit")
    if np.any(f <= 0):
        raise ValueError("frequency_hz must be strictly positive")

    try:
        spec = _cl.get_circuit(model)
    except KeyError:
        raise ValueError(f"Unknown circuit '{model}'. Choose from core.circuit_library.CIRCUIT_MODELS.")

    omega = 2 * np.pi * f
    param_names = spec.param_order
    param_kinds = spec.param_kinds
    x0, bounds_lo, bounds_hi = _cl.initial_guess_and_bounds(spec, f, zr)
    if len(f) * 2 < len(param_names):
        raise ValueError(
            f"Circuit '{spec.display}' has {len(param_names)} free parameters -- need at "
            f"least {(len(param_names) + 1) // 2} frequency points, got {len(f)}."
        )

    def residuals(x):
        params = dict(zip(param_names, x))
        z_model = _cl.evaluate_circuit(spec.tree, omega, params)
        return np.concatenate([(z_model.real - zr), (z_model.imag - zi)])

    candidate_x0s = [x0]
    if multistart:
        rescale_kinds = ("Y0", "B", "C")
        for factor in (0.1, 10.0, 0.01, 100.0):
            candidate = [
                float(np.clip(v * factor, lo, hi)) if param_kinds[name] in rescale_kinds else v
                for name, v, lo, hi in zip(param_names, x0, bounds_lo, bounds_hi)
            ]
            candidate_x0s.append(candidate)

    best_result = None
    for candidate in candidate_x0s:
        r = least_squares(residuals, candidate, bounds=(bounds_lo, bounds_hi), max_nfev=max_nfev)
        if best_result is None or float(np.sum(r.fun ** 2)) < float(np.sum(best_result.fun ** 2)):
            best_result = r
    result = best_result

    params = dict(zip(param_names, result.x))

    # Approximate parameter standard errors from the Jacobian (linearized
    # covariance estimate) -- reported as NaN if the Jacobian is singular
    # or under-determined, rather than a misleadingly precise-looking number.
    try:
        jac = result.jac
        residual_variance = float(np.sum(result.fun ** 2)) / max(len(result.fun) - len(x0), 1)
        cov = np.linalg.inv(jac.T @ jac) * residual_variance
        diag = np.diag(cov)
        # A negative diagonal means an ill-conditioned/near-singular
        # covariance (common for an overfit or poorly-identified circuit)
        # -- report NaN for that parameter's error rather than let sqrt
        # warn on a negative input; NaN is the correct "unavailable" value
        # either way, this just keeps the warning from firing on the
        # expected case.
        errors = np.where(diag >= 0, np.sqrt(np.clip(diag, 0, None)), np.nan)
        param_errors = dict(zip(param_names, errors))
    except (np.linalg.LinAlgError, ValueError):
        param_errors = {name: float("nan") for name in param_names}

    chi_sq = float(np.sum(result.fun ** 2))
    dof = max(len(result.fun) - len(x0), 1)
    reduced_chi_sq = chi_sq / dof

    z_fit = _cl.evaluate_circuit(spec.tree, omega, params)

    # Bound-pinning diagnostic: scipy's least_squares reports which bounds
    # are actually ACTIVE at the solution (result.active_mask: -1 = pinned
    # at lower bound, 1 = pinned at upper bound, 0 = free). A parameter
    # pinned at its lower bound almost always means the optimizer is
    # trying to SUPPRESS an element the model can't actually use to
    # explain the data -- most commonly a Warburg element fit against
    # data whose low-frequency shape it cannot represent (see the "which
    # Warburg element for a supercapacitor" note in circuit_library.py) --
    # not a successful measurement of a genuinely tiny quantity. Surfacing
    # this explicitly means a "vanished" Warburg is reported as a modeling
    # mismatch instead of silently showing a small/strange fitted number.
    warnings_list = []
    active_mask = getattr(result, "active_mask", np.zeros(len(param_names)))
    for name, val, active in zip(param_names, result.x, active_mask):
        if active < 0:
            warnings_list.append(
                f"'{name}' is pinned at its lower search bound ({val:.4g}) -- this usually "
                f"means the model doesn't actually need this element to explain the data "
                f"(common for a Warburg element fit against data whose shape it can't "
                f"represent), not that you've precisely measured a tiny value."
            )
        elif active > 0:
            warnings_list.append(
                f"'{name}' is pinned at its upper search bound ({val:.4g}) -- the optimizer "
                f"hit an artificial ceiling rather than a true optimum; treat this value with "
                f"caution."
            )

    # Resistance-overestimation diagnostic: this catches a DIFFERENT, more
    # dangerous failure mode than bound-pinning above -- one where the
    # optimizer converges to a genuine (non-boundary) local optimum that's
    # still wildly unphysical. Reproduced directly: fitting a circuit with
    # NO Warburg/diffusion element to data that has a real low-frequency
    # diffusion tail which hasn't fully resolved within the measured
    # frequency range returned Rct = 4447 Ohm for a true value of 50 Ohm
    # (89x) -- with NO bound-pinning warning, since 4447 was nowhere near
    # any search-bound ceiling. Physically: without a Warburg term, the
    # only way an Rct||CPE branch can mimic a still-rising (not yet
    # saturated) low-frequency curve is to push Rct far beyond the
    # semicircle's actual diameter, moving the RC knee below the measured
    # range entirely. A resistance parameter that's wildly larger than the
    # data's own real-axis span is the concrete, checkable signature of
    # this -- a genuinely large, well-resolved Rct instead lands close to
    # (not many multiples of) the measured span (verified: ratio ~1.0 for
    # a correct large-Rct fit vs. ~32x for the reproduced failure above).
    # Rleak is excluded: it is DESIGNED to be much larger than the span
    # (see the Rleak-specific initial-guess heuristic in
    # circuit_library.initial_guess_and_bounds), so this ratio doesn't
    # apply to it.
    r_span = float(np.max(zr) - np.min(zr)) if len(zr) else 0.0
    if r_span > 0:
        OVERESTIMATE_FACTOR = 20.0
        for name, val in params.items():
            if param_kinds.get(name) == "R" and name != "Rleak" and val > OVERESTIMATE_FACTOR * r_span:
                warnings_list.append(
                    f"'{name}' = {val:.4g} Ω is over {OVERESTIMATE_FACTOR:.0f}x the "
                    f"measured real-axis span ({r_span:.4g} Ω) -- this is the signature of "
                    f"a circuit missing an element it needs (most often a Warburg/diffusion "
                    f"element) to explain a low-frequency feature that hasn't fully resolved "
                    f"within your measured frequency range, not a genuine measurement. Try a "
                    f"circuit with a Warburg element (e.g. the Supercapacitor category) or "
                    f"extend the measurement to lower frequency."
                )

    return EquivalentCircuitFitResult(
        model=model, params=params, param_errors=param_errors,
        chi_squared=chi_sq, reduced_chi_squared=reduced_chi_sq,
        z_fit_re=z_fit.real, z_fit_im=z_fit.imag, warnings=warnings_list,
    )


def auto_fit_equivalent_circuit(
    frequency_hz: np.ndarray, z_re_ohm: np.ndarray, z_im_ohm: np.ndarray,
    models: list[str] | None = None,
    progress_callback=None,
) -> tuple[EquivalentCircuitFitResult, list[tuple[str, EquivalentCircuitFitResult | None, str | None]]]:
    """Try every circuit topology in `models` (default: ALL ~100 circuits
    in core.circuit_library) against the same spectrum and return the best
    fit by reduced chi-squared, along with the full attempt log so the
    choice is never hidden -- each entry is
    (model_name, result_or_None, error_or_None).

    This is a practical stand-in for true multi-start global optimization:
    instead of retrying one topology from many random starting points, it
    tries many DIFFERENT plausible circuit topologies (which is usually the
    more relevant ambiguity for real electrode/electrolyte systems) and
    reports which one the data best supports. It is still a single
    heuristic-initial-guess nonlinear least squares run per topology, so a
    "best" result here is best among the models tried, not a guarantee of
    the true global optimum -- always check the overlay plot, not just the
    ranked chi-squared table.

    Models with more free parameters will often fit numerically better even
    when not physically more correct (over-fitting) -- the results list
    reports the parameter count for each model alongside reduced chi-squared
    so this trade-off is visible, not just the winner.

    Each of the ~100 screening fits is run with a bounded `max_nfev` (fast
    but slightly less converged); once the best candidate is identified,
    it is re-fit once more with no iteration cap so the FINAL reported
    result/overlay is fully converged, not just "best of a quick pass."
    `progress_callback(done, total, model_name)`, if given, is called after
    each screening fit -- lets a caller show progress on a ~100-circuit
    sweep instead of the UI appearing to hang.
    """
    candidates = models or CIRCUIT_MODELS
    attempts: list[tuple[str, EquivalentCircuitFitResult | None, str | None]] = []
    screening_max_nfev = 60
    for i, m in enumerate(candidates):
        try:
            r = fit_equivalent_circuit(frequency_hz, z_re_ohm, z_im_ohm, model=m,
                                        max_nfev=screening_max_nfev)
            attempts.append((m, r, None))
        except (ValueError, ImportError, RuntimeError) as e:
            attempts.append((m, None, str(e)))
        if progress_callback is not None:
            progress_callback(i + 1, len(candidates), m)

    successful = [r for _, r, err in attempts if r is not None]
    if not successful:
        errs = "; ".join(f"{m}: {err}" for m, r, err in attempts if err)
        raise ValueError(f"No circuit model could be fit to this data. Attempts failed: {errs}")

    best_screen = min(successful, key=lambda r: r.reduced_chi_squared)
    # Final polish: re-fit the winner to full convergence (no nfev cap),
    # with multistart -- affordable here since it's only ONE circuit, not
    # the whole screening pass, and this is the result actually reported.
    best = fit_equivalent_circuit(frequency_hz, z_re_ohm, z_im_ohm, model=best_screen.model,
                                   multistart=True)
    attempts = [(m, best, err) if m == best_screen.model and r is not None else (m, r, err)
                for m, r, err in attempts]
    return best, attempts

