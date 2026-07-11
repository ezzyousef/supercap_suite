"""
Galvanostatic charge/discharge (GCD) analysis.

Pure functions, no Qt imports, so this is unit-testable and reusable
headlessly. Equations and their sources are documented individually --
see docs/EQUATIONS.md in this project for the full literature list.

Two capacitance formulas are implemented, and the choice between them is
NOT arbitrary:

1. "Normal" (linear) formula -- valid ONLY when the discharge V(t) curve is
   (near-)linear, i.e. an ideal EDLC / near-ideal capacitive material:

       C_s = (I * dt) / (m * dV)

2. "Integral" formula -- required whenever the discharge curve is
   non-linear (pseudocapacitive / battery-type / asymmetric-hybrid
   materials with sloping or plateaued discharge):

       C_s = (2 * I * INTEGRAL[V dt]) / (m * dV**2)

   This is the form explicitly recommended in the literature "because the
   integral form ... accurately reflects the complex charge storage
   mechanisms ... thereby minimizing miscalculations" for non-linear
   discharge profiles (Mathis et al., as cited via the integral-capacitance
   review used in this project's source material).

Using the linear formula on a non-linear curve (or vice versa) silently
produces a wrong number, not an error -- that's exactly the mistake this
module is built to avoid, by testing the curve's linearity first
(`classify_discharge_linearity`) and picking the matching formula
automatically (`capacitance_gcd_auto`), while still exposing both formulas
directly so a user who disagrees with the automatic call can override it.
"""
from dataclasses import dataclass
import numpy as np


# ---------------------------------------------------------------------------
# Linearity classification -- decides normal vs integral form
# ---------------------------------------------------------------------------

@dataclass
class LinearityResult:
    r_squared: float
    is_linear: bool
    threshold: float


def classify_discharge_linearity(t: np.ndarray, v: np.ndarray, r2_threshold: float = 0.98) -> LinearityResult:
    """Classify a discharge segment as linear (EDLC-like) or non-linear
    (pseudocapacitive/battery-like) by fitting V = a*t + b and checking R^2.

    r2_threshold default of 0.98 is a practical cutoff, not a universal
    physical constant -- there is no single agreed threshold in the
    literature for "linear enough". Treat this as a tunable heuristic and
    always let the user see the R^2 value and the plotted curve, rather
    than trusting the boolean alone for borderline cases.
    """
    t = np.asarray(t, dtype=float)
    v = np.asarray(v, dtype=float)
    if len(t) < 3:
        raise ValueError("Need at least 3 points to assess linearity")

    # Linear least-squares fit
    coeffs = np.polyfit(t, v, 1)
    v_fit = np.polyval(coeffs, t)
    ss_res = np.sum((v - v_fit) ** 2)
    ss_tot = np.sum((v - np.mean(v)) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0

    return LinearityResult(r_squared=r2, is_linear=(r2 >= r2_threshold), threshold=r2_threshold)


# ---------------------------------------------------------------------------
# Charge/discharge segment auto-detection
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    kind: str            # "charge" or "discharge"
    start: int            # row index, inclusive
    end: int              # row index, inclusive
    duration_s: float
    voltage_window_v: float

    @property
    def label(self) -> str:
        return (f"{self.kind.capitalize()} — rows {self.start}–{self.end}  "
                f"(Δt={self.duration_s:.4g} s, ΔV={self.voltage_window_v:.4g} V)")


def detect_charge_discharge_segments(t_s: np.ndarray, v_v: np.ndarray,
                                      prominence_fraction: float = 0.02,
                                      min_segment_points: int = 5) -> list[Segment]:
    """Split ONE continuous (time, voltage) series that records both charge
    and discharge half-cycles back to back -- e.g. a file with no separate
    'cycle number' column -- into alternating charge/discharge segments,
    purely from the shape of V(t).

    Segment boundaries are the local peaks and troughs of V(t), found with
    `scipy.signal.find_peaks` using a *prominence* threshold (a fraction of
    the overall voltage range, default 2%) rather than a raw sign-of-slope
    check -- this makes the split robust to sample-to-sample measurement
    noise, which would otherwise trigger spurious boundaries on almost
    every point. `min_segment_points` additionally discards/merges any
    resulting sliver segments shorter than that many rows.

    This is a shape-based heuristic (not a literature-sourced formula) --
    always check the plotted segment before trusting it, the same as the
    manual row-range selection this feature complements rather than
    replaces.
    """
    t = np.asarray(t_s, dtype=float)
    v = np.asarray(v_v, dtype=float)
    n = len(v)
    if n < min_segment_points * 2:
        raise ValueError(f"Need at least {min_segment_points * 2} points to auto-detect segments")

    v_range = float(np.max(v) - np.min(v))
    if v_range <= 0:
        raise ValueError("Voltage does not vary over this series -- cannot detect charge/discharge segments")

    from scipy.signal import find_peaks
    prominence = max(v_range * prominence_fraction, 1e-12)
    peak_idx, _ = find_peaks(v, prominence=prominence)
    trough_idx, _ = find_peaks(-v, prominence=prominence)

    boundaries = sorted(set([0, n - 1]) | set(int(i) for i in peak_idx) | set(int(i) for i in trough_idx))
    merged = [boundaries[0]]
    for b in boundaries[1:]:
        if b - merged[-1] >= min_segment_points:
            merged.append(b)
        else:
            merged[-1] = b  # too close to the previous boundary -- extend instead of a tiny sliver segment
    if merged[-1] != n - 1:
        merged[-1] = n - 1
    if len(merged) < 2:
        merged = [0, n - 1]

    segments = []
    for i in range(len(merged) - 1):
        s, e = merged[i], merged[i + 1]
        kind = "discharge" if v[e] < v[s] else "charge"
        segments.append(Segment(
            kind=kind, start=s, end=e,
            duration_s=float(t[e] - t[s]),
            voltage_window_v=float(np.max(v[s:e + 1]) - np.min(v[s:e + 1])),
        ))
    return segments


# ---------------------------------------------------------------------------
# Capacitance formulas
# ---------------------------------------------------------------------------

def capacitance_gcd_normal(current_a: float, discharge_time_s: float,
                            voltage_window_v: float, mass_g: float) -> float:
    """Specific capacitance (F/g), linear/normal form.

        C_s = (I * dt) / (m * dV)

    Use only when the discharge curve is (near-)linear -- see
    classify_discharge_linearity. Caller is responsible for:
      - current already in amps (not mA)
      - discharge_time_s / voltage_window_v measured after excluding the
        initial IR drop, if that convention is being followed (see
        `estimate_ir_drop`)
      - mass_g on the intended basis (single electrode vs total active mass
        of both electrodes) -- see `convert_cell_to_electrode_capacitance`
    """
    if mass_g <= 0 or voltage_window_v <= 0:
        raise ValueError("mass_g and voltage_window_v must be positive")
    if discharge_time_s < 0 or current_a < 0:
        raise ValueError("discharge_time_s and current_a must be non-negative")
    return (current_a * discharge_time_s) / (mass_g * voltage_window_v)


def capacitance_gcd_integral(t_s: np.ndarray, v_v: np.ndarray, current_a: float,
                              mass_g: float, voltage_window_v: float | None = None) -> float:
    """Specific capacitance (F/g), integral form for non-linear discharge.

        C_s = (2 * I * INTEGRAL[V dt]) / (m * dV**2)

    `t_s`, `v_v` must be the discharge segment only (fully charged point to
    fully discharged point), time-ordered. `voltage_window_v` defaults to
    max(v) - min(v) of the supplied segment if not given explicitly (e.g. to
    exclude an IR drop deliberately).
    """
    t_s = np.asarray(t_s, dtype=float)
    v_v = np.asarray(v_v, dtype=float)
    if len(t_s) != len(v_v):
        raise ValueError("t_s and v_v must be the same length")
    if len(t_s) < 2:
        raise ValueError("Need at least 2 points to integrate")
    if mass_g <= 0 or current_a < 0:
        raise ValueError("mass_g must be positive and current_a non-negative")

    dv = voltage_window_v if voltage_window_v is not None else (np.max(v_v) - np.min(v_v))
    if dv <= 0:
        raise ValueError("voltage_window_v must be positive")

    trapz_fn = getattr(np, "trapezoid", None) or np.trapz
    integral_v_dt = trapz_fn(v_v, t_s)  # units: V*s

    return (2.0 * current_a * integral_v_dt) / (mass_g * dv ** 2)


def capacitance_gcd_auto(t_s: np.ndarray, v_v: np.ndarray, current_a: float,
                          mass_g: float, r2_threshold: float = 0.98):
    """Pick normal vs integral formula automatically based on discharge
    curve linearity, and return both the value and which method was used
    plus the R^2 that drove the decision, so the choice is always visible
    to the caller rather than hidden.

    Returns a dict: {capacitance_f_per_g, method, r_squared, voltage_window_v,
    discharge_time_s}
    """
    t_s = np.asarray(t_s, dtype=float)
    v_v = np.asarray(v_v, dtype=float)
    lin = classify_discharge_linearity(t_s, v_v, r2_threshold=r2_threshold)
    dv = float(np.max(v_v) - np.min(v_v))
    dt = float(t_s[-1] - t_s[0])

    if lin.is_linear:
        c = capacitance_gcd_normal(current_a, dt, dv, mass_g)
        method = "normal (linear discharge)"
    else:
        c = capacitance_gcd_integral(t_s, v_v, current_a, mass_g, voltage_window_v=dv)
        method = "integral (non-linear discharge)"

    return {
        "capacitance_f_per_g": c,
        "method": method,
        "r_squared": lin.r_squared,
        "voltage_window_v": dv,
        "discharge_time_s": dt,
    }


# ---------------------------------------------------------------------------
# ESR / IR drop
# ---------------------------------------------------------------------------

def estimate_ir_drop(t_s: np.ndarray, v_v: np.ndarray) -> float:
    """Estimate the IR drop (V) at the charge->discharge transition as the
    vertical voltage step at the start of the discharge segment, using the
    first two points of the supplied discharge-segment arrays.

    This is a simple two-point estimate. For noisy data, prefer fitting a
    line to the initial ~1-5% of the discharge and extrapolating to t=0
    (the "steady-state resistance" approach) instead -- that is NOT what
    this function does; it is a deliberately simple first estimate and
    should be reviewed against the plotted curve, not trusted blindly.
    """
    t_s = np.asarray(t_s, dtype=float)
    v_v = np.asarray(v_v, dtype=float)
    if len(v_v) < 2:
        raise ValueError("Need at least 2 points")
    return float(v_v[0] - v_v[1]) if v_v[0] > v_v[1] else float(v_v[1] - v_v[0])


def esr_from_ir_drop(ir_drop_v: float, current_a: float) -> float:
    """ESR (ohm) = IR-drop (V) / I (A).

    Note: some labs report ESR using IR-drop / (2*I) for a full charge-
    discharge cycle convention. This function uses the single-step
    IR-drop/I convention; state clearly in any report which convention was
    used, since the two differ by a factor of 2.
    """
    if current_a <= 0:
        raise ValueError("current_a must be positive")
    return ir_drop_v / current_a


# ---------------------------------------------------------------------------
# Energy & power density
# ---------------------------------------------------------------------------

def energy_density_wh_per_kg(capacitance_f_per_g: float, voltage_window_v: float) -> float:
    """Specific energy (Wh/kg).

        E = (C_s * dV**2) / 7.2

    Derived from E(J/g) = 0.5 * C_s * dV**2, converted J/g -> Wh/kg
    (divide by 3600 for Wh, multiply by 1000 for /kg => divide by 7.2 net).
    """
    if capacitance_f_per_g < 0 or voltage_window_v < 0:
        raise ValueError("Inputs must be non-negative")
    return (capacitance_f_per_g * voltage_window_v ** 2) / 7.2


def power_density_w_per_kg(energy_density_wh_per_kg_: float, discharge_time_s: float) -> float:
    """Specific power (W/kg).

        P = E * 3600 / dt
    """
    if discharge_time_s <= 0:
        raise ValueError("discharge_time_s must be positive")
    return energy_density_wh_per_kg_ * 3600.0 / discharge_time_s


# ---------------------------------------------------------------------------
# Two-electrode <-> single-electrode conversions
# ---------------------------------------------------------------------------

def symmetric_cell_to_electrode_capacitance(c_spec_cell: float) -> float:
    """For a SYMMETRIC two-electrode cell with equal-mass, equal-capacitance
    electrodes:

        C_spec,electrode = 4 * C_spec,cell

    This factor-of-4 is a documented consequence of (a) two capacitors in
    series roughly halving total capacitance, and (b) specific capacitance
    being normalized by total mass (both electrodes) for the cell vs single
    electrode mass for C_elec. It is NOT universal -- it assumes equal mass
    and equal capacitance on both electrodes. For asymmetric/hybrid cells
    use `asymmetric_cell_to_electrode_capacitance` instead.
    """
    if c_spec_cell < 0:
        raise ValueError("c_spec_cell must be non-negative")
    return 4.0 * c_spec_cell


def three_electrode_to_two_electrode_estimate(c_spec_three_electrode: float) -> float:
    """Rough estimate of symmetric two-electrode cell capacitance from a
    three-electrode (single-electrode) capacitance measurement:

        C_spec,cell(2-electrode) = C_spec,electrode(3-electrode) / 4

    This is the inverse of the factor-of-4 relationship above and carries
    the same equal-mass/equal-capacitance assumption. It is a common
    literature approximation for predicting device-level performance from
    single-electrode (three-electrode) testing, not a substitute for an
    actual two-electrode measurement.
    """
    if c_spec_three_electrode < 0:
        raise ValueError("c_spec_three_electrode must be non-negative")
    return c_spec_three_electrode / 4.0


def asymmetric_electrode_mass_balance(c_spec_pos: float, delta_v_pos: float,
                                       c_spec_neg: float, delta_v_neg: float) -> float:
    """Mass ratio m+ / m- for balancing an asymmetric (hybrid) two-electrode
    cell so both electrodes utilize their full capacitance over their own
    working potential window:

        m+ / m- = (C_spec,neg * dV_neg) / (C_spec,pos * dV_pos)

    Both C_spec values (F/g) should come from three-electrode CV or GCD
    testing of each electrode material individually over its own
    optimal/stable potential window.
    """
    if c_spec_pos <= 0 or delta_v_pos <= 0:
        raise ValueError("c_spec_pos and delta_v_pos must be positive")
    return (c_spec_neg * delta_v_neg) / (c_spec_pos * delta_v_pos)


def cell_capacitance_series(c_pos_f: float, c_neg_f: float) -> float:
    """Absolute cell capacitance (F) of two electrodes in series (general
    asymmetric or symmetric two-electrode device):

        1/C_cell = 1/C_pos + 1/C_neg
    """
    if c_pos_f <= 0 or c_neg_f <= 0:
        raise ValueError("c_pos_f and c_neg_f must be positive")
    return 1.0 / (1.0 / c_pos_f + 1.0 / c_neg_f)


# ---------------------------------------------------------------------------
# Rate capability: capacitance / energy / power across current densities
# ---------------------------------------------------------------------------

def rate_capability_series(segments: list[dict], mass_g: float, r2_threshold: float = 0.98) -> list[dict]:
    """Run capacitance_gcd_auto + energy/power density across a series of
    GCD discharge segments recorded at different currents (a "rate
    capability" study), returning one summary dict per segment plus the
    current density (A/g) for plotting capacitance/energy/power vs. rate.

    `segments`: list of {"current_a": float, "t_s": array, "v_v": array}.
    Segments should already be individual discharge-only cuts (fully
    charged -> fully discharged), time-ordered, one per current tested.
    """
    if mass_g <= 0:
        raise ValueError("mass_g must be positive")
    results = []
    for seg in segments:
        current_a = seg["current_a"]
        t_s = np.asarray(seg["t_s"], dtype=float)
        v_v = np.asarray(seg["v_v"], dtype=float)
        t_s = t_s - t_s[0]
        r = capacitance_gcd_auto(t_s, v_v, current_a, mass_g, r2_threshold=r2_threshold)
        e = energy_density_wh_per_kg(r["capacitance_f_per_g"], r["voltage_window_v"])
        p = power_density_w_per_kg(e, r["discharge_time_s"])
        results.append({
            "current_a": current_a,
            "current_density_a_per_g": current_a / mass_g,
            "capacitance_f_per_g": r["capacitance_f_per_g"],
            "method": r["method"],
            "r_squared": r["r_squared"],
            "voltage_window_v": r["voltage_window_v"],
            "discharge_time_s": r["discharge_time_s"],
            "energy_density_wh_per_kg": e,
            "power_density_w_per_kg": p,
        })
    return results


def capacitance_retention_percent(capacitance_f_per_g_series: np.ndarray) -> np.ndarray:
    """Capacitance retention (%) relative to the FIRST value in a series
    (e.g. vs. increasing current density, or vs. cycle number):

        retention(%) = 100 * C_i / C_1

    Standard normalization used throughout the rate-capability and
    cycling-stability literature; simply expresses each value as a
    percentage of the first.
    """
    c = np.asarray(capacitance_f_per_g_series, dtype=float)
    if len(c) == 0:
        raise ValueError("capacitance_f_per_g_series must be non-empty")
    if c[0] == 0:
        raise ValueError("First capacitance value is zero -- cannot normalize retention")
    return 100.0 * c / c[0]
