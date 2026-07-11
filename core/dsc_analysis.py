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
    W_f   = A_f / (334 * m_d)                           (freezable water,   Eq.2)
    W_nb  = W_t - W_f                                   (non-freezable bound water, Eq.3)
    W_fb  = W_f * (area_symmetric_peak / total_peak_area) (freezable bound water, Eq.4)
    W_b   = W_nb + W_fb                                 (total bound water, Eq.5)
    W_free= W_f - W_fb                                  (free water,        Eq.6)

where m_w = mass of water in the sample (g), m_d = mass of the dry sample
(g), A_f = melting endotherm peak area (J), and 334 J/g is the specific
latent heat of fusion of water used in that scheme. Note: the literature
value for the heat of fusion of pure bulk water is commonly cited as
~333.5-334 J/g (~79.7-80 cal/g); 334 J/g is the value explicitly used in
the source equation set above, so it is kept as the default here, but you
may need to verify which value (e.g. 333.55 J/g, an alternative commonly
cited figure) is appropriate for your specific reference method.
"""
from dataclasses import dataclass
import numpy as np


DEFAULT_HEAT_OF_FUSION_WATER_J_PER_G = 334.0


@dataclass
class WaterContentResult:
    total_water_content: float          # W_t  (g water / g dry sample)
    freezable_water_content: float      # W_f
    non_freezable_bound_water: float    # W_nb
    freezable_bound_water: float        # W_fb
    total_bound_water: float            # W_b
    free_water: float                   # W_free

    def as_percent_of_total_water(self) -> dict:
        """Convenience view: each freezable/bound/free fraction expressed as
        a percentage of the FREEZABLE water content (W_f), matching how
        results are often tabulated in papers (e.g. 'freezable bound water
        (% of freezable water)'). Guards against division by zero."""
        if self.freezable_water_content == 0:
            return {"non_freezable_bound_pct": None, "freezable_bound_pct": None, "free_pct": None}
        return {
            "non_freezable_bound_pct": 100 * self.non_freezable_bound_water / self.total_water_content
            if self.total_water_content else None,
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
    symmetric_peak_area_j : integrated area of the symmetric (sharp,
        bulk-like) component of the melting peak (J) -- used to separate
        freezable bound water from free water within the freezable fraction
    total_peak_area_j : total integrated area of all melting peak
        components (J); symmetric_peak_area_j / total_peak_area_j is the
        fraction of freezable water that is "freezable bound"
    heat_of_fusion_j_per_g : specific heat of fusion of water used to
        convert peak area to mass of freezable water; defaults to 334 J/g
        as used in the source equation set -- verify against your chosen
        reference if precision matters.
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
                     peak_start_idx: int, peak_end_idx: int) -> np.ndarray:
    """Construct a simple straight-line baseline under a DSC peak, connecting
    the heat-flow values at `peak_start_idx` and `peak_end_idx`, for use with
    `integrate_dsc_peak`. This is the simplest baseline convention (linear
    interpolation) -- some instrument software offers curved/sigmoidal
    baselines for asymmetric peaks; those are not implemented here since
    there is no single standard algorithm to cite. For a linear baseline
    this returns an array the same length as time_s/heat_flow_mw, valid
    over the [peak_start_idx, peak_end_idx] slice.
    """
    time_s = np.asarray(time_s, dtype=float)
    heat_flow_mw = np.asarray(heat_flow_mw, dtype=float)
    if not (0 <= peak_start_idx < peak_end_idx < len(time_s)):
        raise ValueError("Require 0 <= peak_start_idx < peak_end_idx < len(time_s)")

    t0, t1 = time_s[peak_start_idx], time_s[peak_end_idx]
    y0, y1 = heat_flow_mw[peak_start_idx], heat_flow_mw[peak_end_idx]
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
