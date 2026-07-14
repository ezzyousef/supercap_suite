"""
Differential scanning calorimetry (DSC) analysis for hydrogel / gel
electrolyte water-state characterization, plus generic enthalpy
calculation from raw heat-flow curves.

Pure functions, no Qt imports.

Water-type equations (Eqs. 1-6) follow the widely-used hydrogel water-
classification scheme (freezable/non-freezable bound water, free water)
as applied to DSC melting-peak data, e.g. Yousef et al., "Anti-freezing
... gel electrolyte", Chemical Engineering Journal 526 (2025) 171441:

    W_t   = m_w / m_d                                  (total water content, Eq.1)
    W_f   = A_f / (333.55 * m_d)                        (freezable water,   Eq.2)
    W_nb  = W_t - W_f                                   (non-freezable bound water, Eq.3)
    W_fb  = W_f * (area_symmetric_peak / total_peak_area) (freezable bound water, Eq.4)
    W_b   = W_nb + W_fb                                 (total bound water, Eq.5)
    W_free= W_f - W_fb                                  (free water,        Eq.6)

where m_w = mass of water in the sample (g), m_d = mass of the dry sample
(g), A_f = melting endotherm peak area (J), and 333.55 J/g is the specific
latent heat of fusion of water used as the reference ("Pure water
Enthalpy") in the user's own validated reference spreadsheet
("Calculations of water (version 1).xlsx"), kept as the default here to
match it exactly (still user-adjustable -- the literature value for the
heat of fusion of pure bulk water is commonly cited anywhere in the
~333.5-334 J/g range depending on source).

Each water population can also be expressed as a percentage OF TOTAL
WATER CONTENT (W_t) -- see WaterContentResult.as_percent_of_total_water()
-- which is exactly the "Freezable water %", "Non-Freezable bound water",
"Freezable bound water %", "Free water %" columns tabulated in that same
reference spreadsheet (verified to 5-6 significant figures against 3
real sample rows): freezable_pct + non_freezable_bound_pct == 100, and
freezable_bound_pct + free_pct == freezable_pct.
"""
from dataclasses import dataclass
import numpy as np


DEFAULT_HEAT_OF_FUSION_WATER_J_PER_G = 333.55


@dataclass
class WaterContentResult:
    total_water_content: float          # W_t  (g water / g dry sample)
    freezable_water_content: float      # W_f
    non_freezable_bound_water: float    # W_nb
    freezable_bound_water: float        # W_fb
    total_bound_water: float            # W_b
    free_water: float                   # W_free

    def as_percent_of_total_water(self) -> dict:
        """Every water population expressed as a percentage of TOTAL water
        content (W_t) -- this is exactly the "Freezable water %",
        "Non-Freezable bound water", "Freezable bound water %", "Free
        water %" columns tabulated in the source reference spreadsheet
        (Calculations of water (version 1).xlsx), verified to 5-6
        significant figures against 3 real sample rows. All four are on
        the SAME basis (W_t), so they relate consistently:
        freezable_pct + non_freezable_bound_pct == 100, and
        freezable_bound_pct + free_pct == freezable_pct.

        For the freezable-bound/free split expressed relative to the
        freezable fraction alone instead (a narrower, different-basis
        view -- NOT the spreadsheet's convention), see
        as_percent_of_freezable_water().
        """
        if self.total_water_content == 0:
            return {"freezable_pct": None, "non_freezable_bound_pct": None,
                    "freezable_bound_pct": None, "free_pct": None}
        t = self.total_water_content
        return {
            "freezable_pct": 100 * self.freezable_water_content / t,
            "non_freezable_bound_pct": 100 * self.non_freezable_bound_water / t,
            "freezable_bound_pct": 100 * self.freezable_bound_water / t,
            "free_pct": 100 * self.free_water / t,
        }

    def as_percent_of_freezable_water(self) -> dict:
        """Freezable-bound / free water, each as a percentage of the
        FREEZABLE water fraction (W_f) only -- these two sum to 100%
        between themselves. An alternate, narrower view than
        as_percent_of_total_water(); NOT the basis used in the source
        reference spreadsheet (use as_percent_of_total_water() to match
        that). Guards against division by zero."""
        if self.freezable_water_content == 0:
            return {"freezable_bound_pct": None, "free_pct": None}
        return {
            "freezable_bound_pct": 100 * self.freezable_bound_water / self.freezable_water_content,
            "free_pct": 100 * self.free_water / self.freezable_water_content,
        }


def classify_water_types(mass_water_g: float, mass_dry_g: float,
                          melting_peak_area_j: float,
                          symmetric_peak_area_j: float, total_peak_area_j: float,
                          heat_of_fusion_j_per_g: float = DEFAULT_HEAT_OF_FUSION_WATER_J_PER_G
                          ) -> WaterContentResult:
    """Classify the three water populations (free, freezable bound,
    non-freezable bound) in a hydrogel/gel electrolyte from DSC melting-peak
    data, per Eqs. 1-6 above.

    Parameters
    ----------
    mass_water_g : total mass of water in the as-prepared sample (g)
    mass_dry_g : mass of the dry (water-free) sample (g)
    melting_peak_area_j : integrated area of the DSC melting endotherm (J) --
        this is A_f, giving the freezable water content via the heat of fusion
    symmetric_peak_area_j : the portion of the melting endotherm's area (J)
        attributable to freezable BOUND water -- despite the name (kept for
        continuity with the source paper's Eq.4 notation), this is NOT a
        curve-symmetry quantity: validated directly against the source
        paper's own worked calculations, it is the SUBZERO area (the part
        of the melting peak occurring BELOW 0 degC, i.e. at a depressed
        melting point from confinement/interaction with the polymer
        matrix -- the Gibbs-Thomson signature of "bound" water that can
        still freeze/melt, just not at the normal temperature). See
        zero_and_subzero_peak_areas() below, which computes exactly this
        split from a temperature-vs-heat-flow curve.
    total_peak_area_j : total integrated area of all melting peak
        components (J); symmetric_peak_area_j / total_peak_area_j is the
        fraction of freezable water that is "freezable bound"
    heat_of_fusion_j_per_g : specific heat of fusion of water used to
        convert peak area to mass of freezable water; defaults to
        333.55 J/g, matching the "Pure water Enthalpy" reference value
        used in the source reference spreadsheet -- verify against your
        chosen reference if precision matters.
    """
    if mass_dry_g <= 0:
        raise ValueError("mass_dry_g must be positive")
    if total_peak_area_j <= 0:
        raise ValueError("total_peak_area_j must be positive")
    if heat_of_fusion_j_per_g <= 0:
        raise ValueError("heat_of_fusion_j_per_g must be positive")

    w_t = mass_water_g / mass_dry_g
    w_f = melting_peak_area_j / (heat_of_fusion_j_per_g * mass_dry_g)
    w_nb = w_t - w_f
    w_fb = w_f * (symmetric_peak_area_j / total_peak_area_j)
    w_b = w_nb + w_fb
    w_free = w_f - w_fb

    return WaterContentResult(
        total_water_content=w_t,
        freezable_water_content=w_f,
        non_freezable_bound_water=w_nb,
        freezable_bound_water=w_fb,
        total_bound_water=w_b,
        free_water=w_free,
    )


# ---------------------------------------------------------------------------
# Generic enthalpy calculation from raw DSC heat-flow data
# ---------------------------------------------------------------------------

def integrate_dsc_peak(time_s: np.ndarray, heat_flow_mw: np.ndarray,
                        baseline_mw: np.ndarray | None = None) -> float:
    """Integrate a DSC heat-flow-vs-time peak to get peak area in Joules.

    `heat_flow_mw` is in milliwatts (mJ/s); integrating over time in seconds
    gives millijoules, so the result is converted to Joules (/1000).

    If `baseline_mw` is supplied (same length as heat_flow_mw, e.g. a
    linear baseline you've already constructed between the peak's start and
    end points), it is subtracted before integrating -- this is the
    standard way to isolate the peak from instrument/sample baseline drift.
    If not supplied, the raw heat_flow_mw is integrated as-is, which assumes
    the input already has the baseline removed.
    """
    time_s = np.asarray(time_s, dtype=float)
    heat_flow_mw = np.asarray(heat_flow_mw, dtype=float)
    if len(time_s) != len(heat_flow_mw):
        raise ValueError("time_s and heat_flow_mw must be the same length")
    if len(time_s) < 2:
        raise ValueError("Need at least 2 points to integrate")

    signal = heat_flow_mw
    if baseline_mw is not None:
        baseline_mw = np.asarray(baseline_mw, dtype=float)
        if len(baseline_mw) != len(heat_flow_mw):
            raise ValueError("baseline_mw must match heat_flow_mw length")
        signal = heat_flow_mw - baseline_mw

    trapz_fn = getattr(np, "trapezoid", None) or np.trapz
    area_mj = trapz_fn(np.abs(signal), time_s)  # mW * s = mJ
    return float(area_mj) / 1000.0  # -> J


def linear_baseline(time_s: np.ndarray, heat_flow_mw: np.ndarray,
                     peak_start_idx: int, peak_end_idx: int,
                     anchor_avg_points: int = 1) -> np.ndarray:
    """Construct a simple straight-line baseline under a DSC peak, connecting
    the heat-flow values at `peak_start_idx` and `peak_end_idx`, for use with
    `integrate_dsc_peak`. This is the simplest baseline convention (linear
    interpolation) -- some instrument software offers curved/sigmoidal
    baselines for asymmetric peaks; those are not implemented here since
    there is no single standard algorithm to cite. For a linear baseline
    this returns an array the same length as time_s/heat_flow_mw, valid
    over the [peak_start_idx, peak_end_idx] slice.

    `anchor_avg_points` (default 1, i.e. the old single-sample behavior):
    number of points averaged AT and going inward from each boundary to
    get the y0/y1 baseline anchor, instead of trusting the single raw
    sample exactly at peak_start_idx/peak_end_idx. Anchoring a baseline
    to one noisy sample is a well-known source of erratic DSC peak areas
    -- commercial DSC software (TA Universal Analysis, Netzsch Proteus,
    etc.) avoids this by averaging a small span of points at each
    flanking region rather than reading a single point.

    This is a genuine bias/variance trade-off, not a one-directional
    accuracy improvement: averaging more points suppresses anchor NOISE,
    but only helps if the flanking region is actually flat there -- if
    peak_start_idx/peak_end_idx still sit on the tail of the peak itself
    (a real risk with auto-detected boundaries, see detect_dsc_peak's
    caveat about peak-width heuristics), a larger average reaches further
    into that tail and systematically biases the baseline upward/
    downward instead. There is no single number that is always correct;
    always check the plotted baseline overlay to confirm the flanking
    region it's averaging over is actually flat before trusting a larger
    value here.
    """
    time_s = np.asarray(time_s, dtype=float)
    heat_flow_mw = np.asarray(heat_flow_mw, dtype=float)
    if not (0 <= peak_start_idx < peak_end_idx < len(time_s)):
        raise ValueError("Require 0 <= peak_start_idx < peak_end_idx < len(time_s)")
    if anchor_avg_points < 1:
        raise ValueError("anchor_avg_points must be >= 1")

    span = min(anchor_avg_points, peak_end_idx - peak_start_idx)  # never let the two anchor spans overlap
    t0, t1 = time_s[peak_start_idx], time_s[peak_end_idx]
    y0 = float(np.mean(heat_flow_mw[peak_start_idx:peak_start_idx + span]))
    y1 = float(np.mean(heat_flow_mw[peak_end_idx - span + 1:peak_end_idx + 1]))
    baseline = np.full_like(heat_flow_mw, np.nan)
    slice_t = time_s[peak_start_idx:peak_end_idx + 1]
    baseline[peak_start_idx:peak_end_idx + 1] = y0 + (y1 - y0) * (slice_t - t0) / (t1 - t0)
    return baseline


@dataclass
class PeakDetectionResult:
    peak_index: int
    start_index: int
    end_index: int
    peak_time_s: float
    peak_value_mw: float
    direction: str   # "endotherm-up" (positive-going) or "endotherm-down" (negative-going)


def detect_dsc_peak(time_s: np.ndarray, heat_flow_mw: np.ndarray,
                     prominence_fraction: float = 0.1,
                     boundary_rel_height: float = 0.97) -> PeakDetectionResult:
    """Auto-detect the most prominent peak in a DSC heat-flow curve and its
    integration boundaries, without requiring the user to manually pick a
    row range first.

    DSC instrument/software conventions differ on whether an endothermic
    event (e.g. ice/water melting) is plotted as a positive or a negative
    heat-flow excursion -- this function does not assume one: it searches
    for prominent peaks in BOTH the raw signal and its negation (via
    `scipy.signal.find_peaks` with a prominence threshold set as a fraction
    of the signal's total range, default 10%) and keeps whichever direction
    produced the single most prominent feature.

    Peak boundaries (`start_index`/`end_index`) come from
    `scipy.signal.peak_widths` at `boundary_rel_height` (default 0.97,
    i.e. 97% of the way down from the peak toward its local baseline on
    each side) -- a standard, reproducible way to locate where a peak
    "returns to baseline" without hand-tuning per curve. This is a
    practical heuristic, not a literature-sourced peak-boundary algorithm
    (there is no single agreed one) -- always check the plotted peak+
    baseline before trusting the auto-detected region, the same caveat
    that already applies to manual peak selection in this app.
    """
    from scipy.signal import find_peaks, peak_widths

    t = np.asarray(time_s, dtype=float)
    y = np.asarray(heat_flow_mw, dtype=float)
    n = len(y)
    if n < 5:
        raise ValueError("Need at least 5 points to auto-detect a peak")

    y_range = float(np.max(y) - np.min(y))
    if y_range <= 0:
        raise ValueError("Heat flow signal does not vary -- cannot auto-detect a peak")
    prominence = max(y_range * prominence_fraction, 1e-12)

    up_idx, up_props = find_peaks(y, prominence=prominence)
    down_idx, down_props = find_peaks(-y, prominence=prominence)

    best_idx, best_prom, direction, signal_for_widths = None, -1.0, None, None
    if len(up_idx):
        i = int(up_idx[np.argmax(up_props["prominences"])])
        p = float(np.max(up_props["prominences"]))
        if p > best_prom:
            best_idx, best_prom, direction, signal_for_widths = i, p, "endotherm-up", y
    if len(down_idx):
        i = int(down_idx[np.argmax(down_props["prominences"])])
        p = float(np.max(down_props["prominences"]))
        if p > best_prom:
            best_idx, best_prom, direction, signal_for_widths = i, p, "endotherm-down", -y

    if best_idx is None:
        raise ValueError(
            "No clear peak found (nothing stood out from the baseline by "
            f"more than {prominence_fraction:.0%} of the signal's range). "
            "Try a smaller prominence, or select the peak region manually."
        )

    widths_result = peak_widths(signal_for_widths, [best_idx], rel_height=boundary_rel_height)
    left_ip, right_ip = widths_result[2][0], widths_result[3][0]
    start_index = max(0, int(np.floor(left_ip)))
    end_index = min(n - 1, int(np.ceil(right_ip)))
    if end_index <= start_index:
        start_index, end_index = max(0, best_idx - 1), min(n - 1, best_idx + 1)

    return PeakDetectionResult(
        peak_index=best_idx, start_index=start_index, end_index=end_index,
        peak_time_s=float(t[best_idx]), peak_value_mw=float(y[best_idx]),
        direction=direction,
    )


@dataclass
class PeakSymmetryResult:
    symmetric_area_j: float   # area of the peak's symmetric ("bulk-like") core
    total_area_j: float       # full baseline-corrected peak area (same as integrate_dsc_peak)
    asymmetry_fraction: float  # (total - symmetric) / total; 0 = perfectly symmetric


def symmetric_and_total_peak_areas(time_s: np.ndarray, heat_flow_mw: np.ndarray,
                                    baseline_mw: np.ndarray, peak_index: int,
                                    start_index: int, end_index: int) -> PeakSymmetryResult:
    """Automatically split a (possibly asymmetric) DSC melting peak into a
    symmetric "bulk-like" core and the full/total peak area, for use as
    `symmetric_peak_area_j` / `total_peak_area_j` in classify_water_types
    (Eq. 4: W_fb = W_f * area_symmetric / area_total) WITHOUT requiring
    the user to separately measure or manually enter those two areas.

    Method: mirror the baseline-corrected peak about its own apex (the
    time of `peak_index`) and take the pointwise minimum of the peak and
    its mirror image as the "symmetric" component -- i.e. the largest
    subset of the peak that IS symmetric about its own apex. A truly
    symmetric peak (e.g. bulk water's sharp melting transition) has
    symmetric_area == total_area; a peak with a broader shoulder on one
    side (physically: a population of more weakly-bound water melting at
    a different temperature than the sharp/bulk-like population) has that
    shoulder excluded from the symmetric core, so symmetric_area <
    total_area and the gap is attributed to the asymmetric ("freezable
    bound") contribution.

    IMPORTANT CAVEAT: this is a general, assumption-light signal-symmetry
    heuristic implemented so the full water-type pipeline (Eqs. 1-6, see
    module docstring) can run end-to-end without manual area entry --
    it is NOT verified against the specific deconvolution procedure used
    in the source paper (Yousef et al., Chem. Eng. J. 526 (2025) 171441),
    which this app does not have machine-readable access to reproduce
    exactly. If your workflow requires matching that paper's exact
    methodology, treat this as a starting point and cross-check a few
    samples by hand before relying on it for publication-quality numbers.
    """
    t = np.asarray(time_s, dtype=float)
    y = np.asarray(heat_flow_mw, dtype=float)
    baseline_mw = np.asarray(baseline_mw, dtype=float)
    if not (len(t) == len(y) == len(baseline_mw)):
        raise ValueError("time_s, heat_flow_mw, and baseline_mw must be the same length")
    if not (0 <= start_index <= peak_index <= end_index < len(t)):
        raise ValueError("Require 0 <= start_index <= peak_index <= end_index < len(time_s)")
    if end_index - start_index < 2:
        raise ValueError("Need at least 3 points in the peak window to assess symmetry")

    t_win = t[start_index:end_index + 1]
    signal_win = np.abs(y[start_index:end_index + 1] - baseline_mw[start_index:end_index + 1])
    t_peak = t[peak_index]

    mirrored_t = 2.0 * t_peak - t_win
    y_mirror = np.interp(mirrored_t, t_win, signal_win, left=0.0, right=0.0)
    y_symmetric = np.minimum(signal_win, y_mirror)

    trapz_fn = getattr(np, "trapezoid", None) or np.trapz
    total_mj = float(trapz_fn(signal_win, t_win))
    symmetric_mj = float(trapz_fn(y_symmetric, t_win))
    total_j = total_mj / 1000.0
    symmetric_j = symmetric_mj / 1000.0
    asymmetry = (total_j - symmetric_j) / total_j if total_j > 0 else 0.0

    return PeakSymmetryResult(
        symmetric_area_j=symmetric_j, total_area_j=total_j,
        asymmetry_fraction=max(0.0, asymmetry),
    )


@dataclass
class ZeroSubzeroSplitResult:
    zero_area_j: float      # peak area at temperature >= threshold (default 0 degC) -- free water
    subzero_area_j: float   # peak area at temperature <  threshold -- freezable BOUND water
    total_area_j: float
    subzero_fraction: float  # subzero_area_j / total_area_j -- feed this * A_f as symmetric_peak_area_j


def zero_and_subzero_peak_areas(time_s: np.ndarray, heat_flow_mw: np.ndarray,
                                 baseline_mw: np.ndarray, temperature_c: np.ndarray,
                                 start_index: int, end_index: int,
                                 threshold_c: float = 0.0) -> ZeroSubzeroSplitResult:
    """Split a (baseline-corrected) DSC melting peak's area by a
    TEMPERATURE THRESHOLD (default 0 degC, the bulk-water melting point)
    -- the "zero" component (melting at or above the threshold: bulk-
    like, unconfined water) and the "subzero" component (melting below
    the threshold: freezing-point-DEPRESSED, i.e. water confined by or
    interacting with the polymer/gel matrix -- still freezable, just not
    at the normal temperature, the Gibbs-Thomson signature of "bound"
    water). This is the actual free/freezable-bound split used for Eq.4
    -- see classify_water_types's docstring -- verified directly against
    the source paper's own worked spreadsheet (matched to 5-6 significant
    figures across multiple real samples): freezable_bound_fraction =
    subzero_area / total_area; free_fraction = zero_area / total_area.

    This REPLACES symmetric_and_total_peak_areas (above) as the primary
    method: that function's curve-mirroring heuristic was an assumption-
    light stand-in built before this app had access to the source
    paper's actual worked numbers to validate against, and does not
    reproduce them -- it remains available for anyone who explicitly
    wants a shape-based split instead (e.g. no temperature axis
    available at all), but this temperature-threshold split has a direct
    physical basis (melting-point depression) and matches published,
    already-verified results, so the DSC tab now uses it whenever a
    temperature column is available.

    Requires the ramp to be a HEATING ramp (temperature increasing
    through the peak window) -- true for essentially every real DSC
    melting-endotherm measurement (melting is measured on heating, by
    definition); a cooling/crystallization exotherm is a different
    measurement this function is not intended for.
    """
    t = np.asarray(time_s, dtype=float)
    y = np.asarray(heat_flow_mw, dtype=float)
    baseline_mw = np.asarray(baseline_mw, dtype=float)
    temp_c = np.asarray(temperature_c, dtype=float)
    if not (len(t) == len(y) == len(baseline_mw) == len(temp_c)):
        raise ValueError("time_s, heat_flow_mw, baseline_mw, and temperature_c must be the same length")
    if not (0 <= start_index <= end_index < len(t)):
        raise ValueError("Require 0 <= start_index <= end_index < len(time_s)")
    if end_index - start_index < 2:
        raise ValueError("Need at least 3 points in the peak window")

    t_win = t[start_index:end_index + 1]
    temp_win = temp_c[start_index:end_index + 1]
    signal_win = np.abs(y[start_index:end_index + 1] - baseline_mw[start_index:end_index + 1])

    trapz_fn = getattr(np, "trapezoid", None) or np.trapz
    total_mj = float(trapz_fn(signal_win, t_win))
    if total_mj <= 0:
        raise ValueError("Total peak area is non-positive -- check the selected peak region")

    below = temp_win < threshold_c
    if not np.any(below):
        subzero_mj = 0.0
    elif np.all(below):
        subzero_mj = total_mj
    else:
        # A heating ramp's temperature increases (~)monotonically through
        # the peak window, so there is exactly one crossing -- find the
        # last still-below-threshold point, linearly interpolate the
        # EXACT crossing time/temperature/signal at the threshold (rather
        # than just cutting at the nearest sample point), and integrate
        # the below-threshold portion up to that interpolated boundary.
        below_idx = np.where(below)[0]
        i0 = below_idx[-1]
        i1 = i0 + 1
        temp0, temp1 = temp_win[i0], temp_win[i1]
        frac = (threshold_c - temp0) / (temp1 - temp0) if temp1 != temp0 else 0.0
        frac = float(np.clip(frac, 0.0, 1.0))
        t_cross = t_win[i0] + frac * (t_win[i1] - t_win[i0])
        y_cross = signal_win[i0] + frac * (signal_win[i1] - signal_win[i0])

        t_below = np.append(t_win[:i0 + 1], t_cross)
        y_below = np.append(signal_win[:i0 + 1], y_cross)
        subzero_mj = float(trapz_fn(y_below, t_below))

    total_j = total_mj / 1000.0
    subzero_j = subzero_mj / 1000.0
    zero_j = total_j - subzero_j

    return ZeroSubzeroSplitResult(
        zero_area_j=zero_j, subzero_area_j=subzero_j, total_area_j=total_j,
        subzero_fraction=(subzero_j / total_j if total_j > 0 else 0.0),
    )


@dataclass
class IntegrationAccuracyResult:
    trapezoid_area_j: float
    simpson_area_j: float
    method_difference_percent: float
    boundary_sensitivity_percent: float
    warnings: list


def check_integration_accuracy(time_s: np.ndarray, heat_flow_mw: np.ndarray,
                                start_index: int, end_index: int,
                                boundary_nudge_points: int = 3,
                                anchor_avg_points: int = 1) -> IntegrationAccuracyResult:
    """Self-consistency check for a DSC peak-area integration, giving an
    estimate of how much to trust the reported area -- NOT a replacement
    for looking at the plotted peak+baseline overlay, but a quick
    automated flag for the two most common sources of integration error:

    1. Method sensitivity: re-integrates the SAME (baseline-corrected)
       window with Simpson's rule and compares it to the trapezoidal
       result this app normally reports (integrate_dsc_peak). These
       should closely agree for a smoothly-sampled peak; a large
       difference usually means the peak is coarsely/unevenly sampled.
    2. Boundary sensitivity: nudges the start/end row by up to
       `boundary_nudge_points` points in each direction (re-drawing the
       linear baseline each time) and reports the resulting spread in
       area as a percentage of the original -- a peak whose area swings
       wildly for a +/-1-3 row change in where you clicked "start"/"end"
       has a poorly-anchored baseline (the flanking region isn't flat),
       and its absolute area should be treated as approximate.

    Returns warnings (empty list if both checks look fine) for direct
    display alongside the computed enthalpy, the same "quality flag"
    pattern already used for reduced chi-squared in the EIS circuit fit.
    """
    from scipy.integrate import simpson

    t = np.asarray(time_s, dtype=float)
    y = np.asarray(heat_flow_mw, dtype=float)
    n = len(y)
    if not (0 <= start_index < end_index < n):
        raise ValueError("Require 0 <= start_index < end_index < len(time_s)")

    def _area(s: int, e: int) -> float:
        baseline = linear_baseline(t, y, s, e, anchor_avg_points=anchor_avg_points)
        return integrate_dsc_peak(t[s:e + 1], y[s:e + 1], baseline_mw=baseline[s:e + 1])

    base_area = _area(start_index, end_index)

    baseline_full = linear_baseline(t, y, start_index, end_index, anchor_avg_points=anchor_avg_points)
    signal = np.abs(y[start_index:end_index + 1] - baseline_full[start_index:end_index + 1])
    simpson_area_j = float(simpson(signal, x=t[start_index:end_index + 1])) / 1000.0
    method_diff_pct = (100.0 * abs(base_area - simpson_area_j) / base_area
                        if base_area > 0 else float("nan"))

    areas = [base_area]
    for d in range(1, boundary_nudge_points + 1):
        for ds, de in ((-d, 0), (d, 0), (0, -d), (0, d)):
            s2, e2 = start_index + ds, end_index + de
            if 0 <= s2 < e2 < n:
                try:
                    areas.append(_area(s2, e2))
                except ValueError:
                    continue
    boundary_sensitivity_pct = (100.0 * (max(areas) - min(areas)) / base_area
                                 if base_area > 0 else float("nan"))

    warnings = []
    if not np.isnan(method_diff_pct) and method_diff_pct > 2.0:
        warnings.append(
            f"Trapezoidal vs. Simpson's-rule integration differ by {method_diff_pct:.2f}% -- "
            "the peak region may be too coarsely/unevenly sampled for a precise area."
        )
    if not np.isnan(boundary_sensitivity_pct) and boundary_sensitivity_pct > 5.0:
        warnings.append(
            f"Peak area is sensitive to the exact start/end row (±{boundary_sensitivity_pct:.1f}% "
            f"over a ±{boundary_nudge_points}-row nudge) -- the baseline endpoints may not sit on "
            "a flat part of the curve; check the plotted baseline before trusting this area."
        )

    return IntegrationAccuracyResult(
        trapezoid_area_j=base_area, simpson_area_j=simpson_area_j,
        method_difference_percent=method_diff_pct,
        boundary_sensitivity_percent=boundary_sensitivity_pct,
        warnings=warnings,
    )


def enthalpy_j_per_g(peak_area_j: float, sample_mass_g: float) -> float:
    """Specific enthalpy of a DSC transition (J/g):

        dH = peak_area_J / sample_mass_g

    This is the standard mass-normalized enthalpy reported for melting,
    crystallization, or other thermal transitions from DSC. `peak_area_j`
    should already be baseline-corrected (see integrate_dsc_peak).
    """
    if sample_mass_g <= 0:
        raise ValueError("sample_mass_g must be positive")
    return peak_area_j / sample_mass_g


def crystallinity_percent(enthalpy_sample_j_per_g: float, enthalpy_100pct_crystalline_j_per_g: float) -> float:
    """Percent crystallinity from a measured melting enthalpy relative to
    the reference enthalpy of a 100%-crystalline reference material:

        Xc (%) = 100 * dH_sample / dH_100%-crystalline

    `enthalpy_100pct_crystalline_j_per_g` is material-specific (e.g. for
    pure water/ice melting it is the heat of fusion of water, ~334 J/g in
    the convention used elsewhere in this module) -- you must supply the
    correct reference value for the material in question; I do not have a
    single universal constant to default this to across materials.
    """
    if enthalpy_100pct_crystalline_j_per_g <= 0:
        raise ValueError("enthalpy_100pct_crystalline_j_per_g must be positive")
    return 100.0 * enthalpy_sample_j_per_g / enthalpy_100pct_crystalline_j_per_g
