"""
Cyclic voltammetry (CV) analysis.

Pure functions, no Qt imports.
"""
import numpy as np


def capacitance_from_cv(voltage_v: np.ndarray, current_a: np.ndarray,
                         scan_rate_v_per_s: float, mass_g: float,
                         voltage_window_v: float | None = None) -> float:
    """Specific capacitance (F/g) from one full CV cycle.

        C_s = INTEGRAL[I dV] / (2 * m * scan_rate * dV)

    `voltage_v`/`current_a` should be one closed cycle (forward + reverse
    sweep), aligned arrays; current in amps. `voltage_window_v` defaults to
    max(v) - min(v) of the supplied cycle.

    Computed numerically via the trapezoidal rule over the closed loop
    (the loop is closed automatically if the last point doesn't already
    equal the first).
    """
    voltage_v = np.asarray(voltage_v, dtype=float)
    current_a = np.asarray(current_a, dtype=float)
    if len(voltage_v) != len(current_a):
        raise ValueError("voltage_v and current_a must be the same length")
    if len(voltage_v) < 3:
        raise ValueError("Need at least 3 points to integrate a cycle")
    if mass_g <= 0 or scan_rate_v_per_s <= 0:
        raise ValueError("mass_g and scan_rate_v_per_s must be positive")

    dv = voltage_window_v if voltage_window_v is not None else (np.max(voltage_v) - np.min(voltage_v))
    if dv <= 0:
        raise ValueError("voltage_window_v must be positive")

    v = voltage_v if np.isclose(voltage_v[0], voltage_v[-1]) else np.append(voltage_v, voltage_v[0])
    i = current_a if len(v) == len(current_a) else np.append(current_a, current_a[0])

    trapz_fn = getattr(np, "trapezoid", None) or np.trapz
    enclosed_area = np.abs(trapz_fn(i, v))  # units: A*V

    return enclosed_area / (2.0 * mass_g * scan_rate_v_per_s * dv)


def specific_capacity_from_cv(voltage_v: np.ndarray, current_a: np.ndarray,
                               scan_rate_v_per_s: float, mass_g: float) -> float:
    """Specific capacity (C/g, coulombs per gram) from a CV cycle -- used for
    battery-type materials where reporting capacity (not capacitance) is the
    convention:

        Q_s = INTEGRAL[I dV] / (2 * m * scan_rate)

    (Same integral as capacitance_from_cv but without dividing by dV.)
    """
    voltage_v = np.asarray(voltage_v, dtype=float)
    current_a = np.asarray(current_a, dtype=float)
    if len(voltage_v) != len(current_a):
        raise ValueError("voltage_v and current_a must be the same length")
    if mass_g <= 0 or scan_rate_v_per_s <= 0:
        raise ValueError("mass_g and scan_rate_v_per_s must be positive")

    v = voltage_v if np.isclose(voltage_v[0], voltage_v[-1]) else np.append(voltage_v, voltage_v[0])
    i = current_a if len(v) == len(current_a) else np.append(current_a, current_a[0])

    trapz_fn = getattr(np, "trapezoid", None) or np.trapz
    enclosed_area = np.abs(trapz_fn(i, v))

    return enclosed_area / (2.0 * mass_g * scan_rate_v_per_s)


def b_value_from_log_log(scan_rates_v_per_s: np.ndarray, peak_currents_a: np.ndarray) -> float:
    """Power-law exponent b from i(v) = a * v**b (Dunn's method), fit as the
    slope of log(peak current) vs log(scan rate).

    b ~ 1   -> capacitive (EDLC-like) behavior
    b ~ 0.5 -> diffusion-controlled (battery-like) behavior
    """
    scan_rates_v_per_s = np.asarray(scan_rates_v_per_s, dtype=float)
    peak_currents_a = np.asarray(peak_currents_a, dtype=float)
    if len(scan_rates_v_per_s) < 2:
        raise ValueError("Need at least 2 scan rates to fit a slope")
    log_v = np.log(scan_rates_v_per_s)
    log_i = np.log(np.abs(peak_currents_a))
    slope, _intercept = np.polyfit(log_v, log_i, 1)
    return float(slope)


def capacitance_from_cv_direct(current_a: float, mass_g: float, scan_rate_v_per_s: float) -> float:
    """Specific capacitance (F/g), DIRECT form for a near-ideal RECTANGULAR
    CV curve (EDLC behavior, current roughly constant across the sweep):

        C_s = I / (m * scan_rate)

    Derived from the basic capacitor relation I = C * (dV/dt) = C * scan_rate
    for a linear voltage ramp -- i.e. for an ideal capacitor the CV current is
    constant and directly proportional to scan rate. This is the appropriate
    formula ONLY when the CV curve is close to a rectangle (current roughly
    flat vs. potential, no humps/peaks); for non-rectangular / pseudocapacitive
    curves with redox features, use `capacitance_from_cv` (the integral form)
    instead -- using this direct form on a non-rectangular curve will
    silently under- or over-estimate capacitance depending on which current
    value you pick as "I".

    `current_a` should be a representative (e.g. average magnitude) current
    from the flat/rectangular portion of the curve.
    """
    if mass_g <= 0 or scan_rate_v_per_s <= 0:
        raise ValueError("mass_g and scan_rate_v_per_s must be positive")
    if current_a < 0:
        raise ValueError("current_a must be non-negative")
    return current_a / (mass_g * scan_rate_v_per_s)


def assess_cv_rectangularity(voltage_v: np.ndarray, current_a: np.ndarray) -> float:
    """Heuristic rectangularity score (0-1) for one CV cycle, used to decide
    between the direct/rectangular formula and the integral formula: the
    ratio of the current's standard deviation to its mean absolute value
    over the cycle, inverted and clipped to [0, 1] (1 = perfectly flat
    current => ideal rectangle; lower values indicate humps/peaks/slope
    consistent with pseudocapacitive or battery-type behavior).

    This is a practical heuristic, not a value taken from a specific paper
    -- there is no single agreed numeric "rectangularity" threshold in the
    literature; always inspect the plotted CV curve for redox humps rather
    than trusting this score alone.
    """
    current_a = np.asarray(current_a, dtype=float)
    if len(current_a) < 3:
        raise ValueError("Need at least 3 points")
    mean_abs = np.mean(np.abs(current_a))
    if mean_abs == 0:
        return 0.0
    cv_coefficient = np.std(current_a) / mean_abs  # coefficient of variation
    score = 1.0 / (1.0 + cv_coefficient)
    return float(np.clip(score, 0.0, 1.0))


def capacitance_vs_scan_rate(cycles: list[dict], mass_g: float) -> list[dict]:
    """Compute specific capacitance for each of several CV cycles recorded
    at different scan rates -- a "rate capability" / Trasatti-input series.

    `cycles`: list of {"scan_rate_v_per_s": float, "voltage_v": array, "current_a": array},
    each one full closed CV cycle. Returns one dict per cycle with the scan
    rate and resulting specific capacitance, ready to feed into
    `core.trasatti_method.trasatti_analysis` or for plotting C vs. scan rate.
    """
    if mass_g <= 0:
        raise ValueError("mass_g must be positive")
    results = []
    for cyc in cycles:
        v = np.asarray(cyc["voltage_v"], dtype=float)
        i = np.asarray(cyc["current_a"], dtype=float)
        rate = cyc["scan_rate_v_per_s"]
        c = capacitance_from_cv(v, i, rate, mass_g)
        results.append({
            "scan_rate_v_per_s": rate,
            "capacitance_f_per_g": c,
            "voltage_window_v": float(np.max(v) - np.min(v)),
        })
    return results
    """Compute specific capacitance for each of several CV cycles recorded
    at different scan rates -- a "rate capability" / Trasatti-input series.

    `cycles`: list of {"scan_rate_v_per_s": float, "voltage_v": array, "current_a": array},
    each one full closed CV cycle. Returns one dict per cycle with the scan
    rate and resulting specific capacitance, ready to feed into
    `core.trasatti_method.trasatti_analysis` or for plotting C vs. scan rate.
    """
    if mass_g <= 0:
        raise ValueError("mass_g must be positive")
    results = []
    for cyc in cycles:
        v = np.asarray(cyc["voltage_v"], dtype=float)
        i = np.asarray(cyc["current_a"], dtype=float)
        rate = cyc["scan_rate_v_per_s"]
        c = capacitance_from_cv(v, i, rate, mass_g)
        results.append({
            "scan_rate_v_per_s": rate,
            "capacitance_f_per_g": c,
            "voltage_window_v": float(np.max(v) - np.min(v)),
        })
    return results
