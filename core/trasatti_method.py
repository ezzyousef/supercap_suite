"""
Trasatti's method: separates the total charge stored in a pseudocapacitive
electrode into an "outer" (surface-accessible, rate-independent) and
"inner" (diffusion-limited, only accessible at low scan rate) component,
by extrapolating capacitance-vs-scan-rate data to the v -> infinity and
v -> 0 limits.

Source: equations (16)-(22) as printed in Suganya et al., J. Energy
Storage 109 (2025) 115181 (present verbatim in this project's source
PDFs):

    Q*(v) = k1 * v**-0.5 + Q*_outer                     (eq 18, extrapolate v->inf, i.e. x=1/sqrt(v)->0)
    1/Q*(v) = k * v**0.5 + 1/Q*_total                    (eq 19, extrapolate v->0)
    Q*_total = Q*_inner + Q*_outer                        (eq 20)
    Q*_inner(%) = 100 * Q*_inner / Q*_total                (eq 21)
    Q*_outer(%) = 100 * Q*_outer / Q*_total                (eq 22)

Here Q*(v) is the specific capacitance (F/g) measured at scan rate v
(e.g. via the standard CV integral formula), NOT a literal charge in
coulombs, despite the "Q" notation used in the source paper -- this
matches how the source paper's own worked numbers are reported (F/g).
"""
from dataclasses import dataclass
import numpy as np


@dataclass
class TrasattiResult:
    outer_capacitance_f_per_g: float     # Q*_outer, from v -> infinity extrapolation
    total_capacitance_f_per_g: float     # Q*_total, from v -> 0 extrapolation
    inner_capacitance_f_per_g: float     # Q*_inner = Q*_total - Q*_outer
    inner_fraction_percent: float
    outer_fraction_percent: float
    outer_fit_slope: float
    outer_fit_intercept: float
    total_fit_slope: float
    total_fit_intercept: float


def trasatti_analysis(scan_rates_v_per_s: np.ndarray, capacitance_f_per_g: np.ndarray) -> TrasattiResult:
    """Run Trasatti's outer/inner/total capacitance analysis.

    Parameters
    ----------
    scan_rates_v_per_s : array of scan rates (V/s) used to measure
        capacitance_f_per_g -- need at least 3 distinct scan rates spanning
        a reasonably wide range (e.g. 1 order of magnitude+) for a
        meaningful extrapolation; 2 points give an exact but statistically
        unvalidated line.
    capacitance_f_per_g : specific capacitance (F/g) measured by CV
        integration (or GCD) at each corresponding scan rate.

    Outer capacitance: linear fit of Q*(v) vs v**-0.5, y-intercept at
    v**-0.5 = 0 (i.e. v -> infinity) gives Q*_outer.

    Total capacitance: linear fit of 1/Q*(v) vs v**0.5, y-intercept at
    v**0.5 = 0 (i.e. v -> 0) gives 1/Q*_total, so Q*_total = 1/intercept.
    """
    v = np.asarray(scan_rates_v_per_s, dtype=float)
    q = np.asarray(capacitance_f_per_g, dtype=float)
    if len(v) < 3:
        raise ValueError("Need at least 3 scan rates (spanning a wide range) for a "
                          "meaningful Trasatti extrapolation; 2 points give an exact "
                          "but statistically unvalidated line.")
    if len(v) != len(q):
        raise ValueError("scan_rates_v_per_s and capacitance_f_per_g must be the same length")
    if np.any(v <= 0) or np.any(q <= 0):
        raise ValueError("scan_rates_v_per_s and capacitance_f_per_g must be strictly positive")

    inv_sqrt_v = 1.0 / np.sqrt(v)
    sqrt_v = np.sqrt(v)
    inv_q = 1.0 / q

    # Outer: Q*(v) = k1 * v^-0.5 + Q*_outer  -> intercept at inv_sqrt_v = 0
    slope_outer, intercept_outer = np.polyfit(inv_sqrt_v, q, 1)
    q_outer = float(intercept_outer)

    # Total: 1/Q*(v) = k * v^0.5 + 1/Q*_total -> intercept at sqrt_v = 0
    slope_total, intercept_total = np.polyfit(sqrt_v, inv_q, 1)
    if intercept_total <= 0:
        raise ValueError("Fitted 1/Q*_total intercept is non-positive -- the extrapolation "
                          "did not produce a physical total capacitance; check your data "
                          "(scan-rate range, units) before trusting this result.")
    q_total = 1.0 / intercept_total

    q_inner = q_total - q_outer
    inner_pct = 100.0 * q_inner / q_total if q_total != 0 else float("nan")
    outer_pct = 100.0 * q_outer / q_total if q_total != 0 else float("nan")

    return TrasattiResult(
        outer_capacitance_f_per_g=q_outer,
        total_capacitance_f_per_g=q_total,
        inner_capacitance_f_per_g=q_inner,
        inner_fraction_percent=inner_pct,
        outer_fraction_percent=outer_pct,
        outer_fit_slope=float(slope_outer),
        outer_fit_intercept=float(intercept_outer),
        total_fit_slope=float(slope_total),
        total_fit_intercept=float(intercept_total),
    )
