"""
Dunn's method: separating capacitive (surface, non-diffusion-limited) vs.
diffusion-controlled (faradaic) contributions to current in a CV series
recorded at multiple scan rates.

Two related tools, both from the same underlying power-law relationship
i(V) = k1*v + k2*v^0.5  (at fixed potential V, across a set of scan rates v):

  - b_value_analysis: the power-law exponent b in i = a*v^b (from
    log(peak current) vs log(scan rate)), b~1 capacitive, b~0.5 diffusion.
  - capacitive_diffusive_split: fits i(V)/v^0.5 = k1*v^0.5 + k2 at each
    potential point across the scan-rate series, recovering k1, k2 so the
    capacitive current i_cap(V) = k1*v and diffusive current
    i_diff(V) = k2*v^0.5 can be separated and integrated to get a
    capacitive/diffusive percentage split.

Source: equations (15)-(17) as printed in a supercapacitor nanocomposite
paper in this project's source PDFs (Suganya et al., J. Energy Storage 109
(2025) 115181): "I = a*v^b" (eq 15) and "I(V) = k1*v + k2*v^(1/2)" /
"I(V)/v^(1/2) = k1*v^(1/2) + k2" (eqs 16-17), citing Dunn's method.

IMPORTANT CAVEAT -- read before trusting this analysis for a paper: a 2023
peer-reviewed critique (Pervez & Stallard, "Capacitive and Diffusive
Contributions in Supercapacitors and Batteries: A Critique of b-Value and
the v-v^1/2 Model," Small, 2023) documents that both the b-value metric and
the k1*v + k2*v^0.5 (Dunn) model have documented flaws -- results are
sensitive to the scan-rate range chosen, electrode mass loading, and can
be misinterpreted; the authors argue for caution and, in some cases, an
alternative model. This app implements the classic/most commonly reported
Dunn's method because that is what is used across the bulk of the
supercapacitor literature (including every source paper in this project),
but you should treat the resulting capacitive/diffusive percentages as a
widely used, not a definitively validated, decomposition -- state that
caveat if reporting these numbers.
"""
from dataclasses import dataclass
import numpy as np


@dataclass
class BValueResult:
    b_value: float
    log_scan_rates: np.ndarray
    log_peak_currents: np.ndarray
    fit_intercept: float


def b_value_analysis(scan_rates_v_per_s: np.ndarray, peak_currents_a: np.ndarray) -> BValueResult:
    """Power-law exponent b from i = a * v**b, via linear fit of
    log(|peak current|) vs log(scan rate). b~1 -> capacitive; b~0.5 ->
    diffusion-controlled. Needs at least 3 scan rates for a meaningful fit
    (2 gives an exact but unvalidated line).
    """
    scan_rates_v_per_s = np.asarray(scan_rates_v_per_s, dtype=float)
    peak_currents_a = np.asarray(peak_currents_a, dtype=float)
    if len(scan_rates_v_per_s) < 2:
        raise ValueError("Need at least 2 scan rates to fit a slope (3+ recommended)")
    if len(scan_rates_v_per_s) != len(peak_currents_a):
        raise ValueError("scan_rates_v_per_s and peak_currents_a must be the same length")

    log_v = np.log(scan_rates_v_per_s)
    log_i = np.log(np.abs(peak_currents_a))
    slope, intercept = np.polyfit(log_v, log_i, 1)
    return BValueResult(b_value=float(slope), log_scan_rates=log_v,
                         log_peak_currents=log_i, fit_intercept=float(intercept))


@dataclass
class PeakCurrentCapacitiveDiffusiveSplit:
    k1: float                          # capacitive coefficient (single fit across all scan rates)
    k2: float                          # diffusive coefficient (single fit across all scan rates)
    r_squared: float                   # goodness of the i/v^0.5 = k1*v^0.5 + k2 linear fit
    scan_rates_v_per_s: np.ndarray
    capacitive_currents_a: np.ndarray  # k1*v at each scan rate
    diffusive_currents_a: np.ndarray   # k2*v^0.5 at each scan rate
    total_currents_a: np.ndarray       # k1*v + k2*v^0.5 (the MODEL's reconstruction, not the raw measured peak)
    capacitive_percent: np.ndarray     # per scan rate, of the model total
    diffusive_percent: np.ndarray


def peak_current_capacitive_diffusive_split(scan_rates_v_per_s: np.ndarray,
                                             peak_currents_a: np.ndarray) -> PeakCurrentCapacitiveDiffusiveSplit:
    """Capacitive/diffusive split of Dunn's i(v) = k1*v + k2*v^0.5 model
    using only ONE representative current value per scan rate (typically
    peak current) -- the simpler, single-fit variant of Dunn's method seen
    throughout the literature when a full voltage-resolved breakdown
    (see capacitive_diffusive_split, which needs a complete CV curve at
    every scan rate) isn't available or needed, just a peak-current-vs-
    scan-rate table (the same shape of data as b_value_analysis).

    Method: linear regression of i(v)/v^0.5 against v^0.5 across ALL scan
    rates at once (ONE k1, k2 pair, not one per point) -- slope = k1,
    intercept = k2. capacitive_percent/diffusive_percent are then each
    scan rate's k1*v / k2*v^0.5 as a fraction of the model's OWN
    reconstructed total (k1*v + k2*v^0.5) at that scan rate, NOT of the
    raw measured peak current (which will differ from the model total by
    the fit residual).

    Verified against a real worked spreadsheet example (K1=0.0125,
    K2=0.0986, capacitive%/diffusion% per scan rate reproduced to 6
    significant figures).
    """
    scan_rates = np.asarray(scan_rates_v_per_s, dtype=float)
    peaks = np.asarray(peak_currents_a, dtype=float)
    if len(scan_rates) < 3:
        raise ValueError("Need at least 3 scan rates for a meaningful k1/k2 fit")
    if len(scan_rates) != len(peaks):
        raise ValueError("scan_rates_v_per_s and peak_currents_a must be the same length")
    if np.any(scan_rates <= 0):
        raise ValueError("scan_rates_v_per_s must all be positive")

    sqrt_v = np.sqrt(scan_rates)
    i_over_sqrt_v = peaks / sqrt_v
    k1, k2 = np.polyfit(sqrt_v, i_over_sqrt_v, 1)

    fit_vals = k1 * sqrt_v + k2
    residuals = i_over_sqrt_v - fit_vals
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((i_over_sqrt_v - np.mean(i_over_sqrt_v)) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    i_cap = k1 * scan_rates
    i_diff = k2 * sqrt_v
    total = i_cap + i_diff
    with np.errstate(divide="ignore", invalid="ignore"):
        cap_pct = 100.0 * i_cap / total
        diff_pct = 100.0 * i_diff / total

    return PeakCurrentCapacitiveDiffusiveSplit(
        k1=float(k1), k2=float(k2), r_squared=float(r_squared),
        scan_rates_v_per_s=scan_rates, capacitive_currents_a=i_cap,
        diffusive_currents_a=i_diff, total_currents_a=total,
        capacitive_percent=cap_pct, diffusive_percent=diff_pct,
    )


@dataclass
class CapacitiveDiffusiveSplit:
    k1: np.ndarray            # capacitive coefficient at each potential point
    k2: np.ndarray            # diffusive coefficient at each potential point
    capacitive_current_a: np.ndarray   # i_cap(V) at the scan rate requested
    diffusive_current_a: np.ndarray    # i_diff(V) at the scan rate requested
    capacitive_charge_fraction: float  # % of total |current| that is capacitive, integrated over V
    diffusive_charge_fraction: float


def capacitive_diffusive_split(voltage_v: np.ndarray, currents_by_scan_rate: dict,
                                scan_rate_to_report_v_per_s: float) -> CapacitiveDiffusiveSplit:
    """Separate capacitive vs diffusion-controlled current at each potential
    point across a CV series recorded at several scan rates, per Dunn's
    method: i(V) = k1*v + k2*v**0.5.

    Parameters
    ----------
    voltage_v : common potential axis (all CV curves in currents_by_scan_rate
        must already be interpolated onto this SAME voltage axis -- this
        function does not resample for you)
    currents_by_scan_rate : dict mapping {scan_rate_v_per_s (float): current_array_a}
        with at least 2 (3+ recommended) scan rates, each current_array_a
        the same length as voltage_v
    scan_rate_to_report_v_per_s : which scan rate's capacitive/diffusive
        split to return as arrays (must be one of the keys, or the
        function will fit k1/k2 at each point and evaluate it at this
        (possibly non-measured) scan rate)

    Returns k1(V), k2(V) fit at each potential point, and the resulting
    capacitive/diffusive current curves at the requested scan rate.
    """
    voltage_v = np.asarray(voltage_v, dtype=float)
    scan_rates = np.array(sorted(currents_by_scan_rate.keys()), dtype=float)
    if len(scan_rates) < 2:
        raise ValueError("Need at least 2 scan rates (3+ recommended) to fit k1, k2")

    currents = np.array([np.asarray(currents_by_scan_rate[v], dtype=float) for v in scan_rates])
    for row in currents:
        if len(row) != len(voltage_v):
            raise ValueError("All current arrays must be the same length as voltage_v "
                              "(interpolate onto a common voltage axis first)")

    n_points = len(voltage_v)
    k1 = np.zeros(n_points)
    k2 = np.zeros(n_points)
    sqrt_v = np.sqrt(scan_rates)

    for j in range(n_points):
        i_over_sqrt_v = currents[:, j] / sqrt_v
        # i(V)/sqrt(v) = k1*sqrt(v) + k2  -> linear fit vs sqrt(v)
        slope, intercept = np.polyfit(sqrt_v, i_over_sqrt_v, 1)
        k1[j] = slope
        k2[j] = intercept

    v_report = scan_rate_to_report_v_per_s
    i_cap = k1 * v_report
    i_diff = k2 * np.sqrt(v_report)

    trapz_fn = getattr(np, "trapezoid", None) or np.trapz
    total_cap = float(trapz_fn(np.abs(i_cap), voltage_v)) if len(voltage_v) > 1 else 0.0
    total_diff = float(trapz_fn(np.abs(i_diff), voltage_v)) if len(voltage_v) > 1 else 0.0
    total = total_cap + total_diff
    cap_frac = 100.0 * total_cap / total if total > 0 else float("nan")
    diff_frac = 100.0 * total_diff / total if total > 0 else float("nan")

    return CapacitiveDiffusiveSplit(
        k1=k1, k2=k2, capacitive_current_a=i_cap, diffusive_current_a=i_diff,
        capacitive_charge_fraction=cap_frac, diffusive_charge_fraction=diff_frac,
    )
