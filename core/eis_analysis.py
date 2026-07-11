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

    @property
    def display_name(self) -> str:
        return CIRCUIT_DISPLAY_NAMES.get(self.model, self.model)


def fit_equivalent_circuit(frequency_hz: np.ndarray, z_re_ohm: np.ndarray, z_im_ohm: np.ndarray,
                            model: str = "randles1_Q_none",
                            max_nfev: int | None = None) -> EquivalentCircuitFitResult:
    """Fit a Nyquist spectrum to one circuit from the core.circuit_library
    preset library via complex nonlinear least squares (scipy.optimize.
    least_squares on the STACKED real+imaginary residuals simultaneously --
    not two independent real/imaginary fits).

    `model`: any name in CIRCUIT_MODELS (~100 circuits; see
    core/circuit_library.py for the full library and its categories). Use
    `auto_fit_equivalent_circuit` to try many of them and keep the best fit
    instead of picking one by hand.

    z_im_ohm should be the signed imaginary part of impedance as measured
    (commonly negative for capacitive systems) -- this function does not
    flip signs for you; check your data's convention first.

    Requires scipy. Initial parameter guesses are constructed heuristically
    from the data (see circuit_library.initial_guess_and_bounds) -- for
    difficult/noisy spectra a single run can still converge to a local
    minimum; this function does not attempt multi-start global optimization
    on its own (auto_fit_equivalent_circuit approximates that by trying
    several circuit topologies instead).
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

    result = least_squares(residuals, x0, bounds=(bounds_lo, bounds_hi), max_nfev=max_nfev)

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

    return EquivalentCircuitFitResult(
        model=model, params=params, param_errors=param_errors,
        chi_squared=chi_sq, reduced_chi_squared=reduced_chi_sq,
        z_fit_re=z_fit.real, z_fit_im=z_fit.imag,
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
    # Final polish: re-fit the winner to full convergence (no nfev cap).
    best = fit_equivalent_circuit(frequency_hz, z_re_ohm, z_im_ohm, model=best_screen.model)
    attempts = [(m, best, err) if m == best_screen.model and r is not None else (m, r, err)
                for m, r, err in attempts]
    return best, attempts

