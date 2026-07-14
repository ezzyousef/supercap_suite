"""Generic equivalent-circuit engine + a ~50-circuit preset library for
supercapacitor EIS/PEIS complex nonlinear least-squares (CNLS) fitting.

Scope: supercapacitor-only. This library previously also carried a much
larger set of generic multi-time-constant Randles-type circuits
("Two time constants" / "Three time constants", a combinatorial sweep
not individually sourced for any specific system), a Gerischer-element
category (mixed ionic/electronic conduction -- battery/SOFC insertion
electrodes, not supercapacitors), and a "Miscellaneous" grab-bag of
single-element diagnostic circuits with no Rct term at all -- i.e. not
physically representable as a supercapacitor electrode. All three were
removed: every circuit remaining here is either a standard supercapacitor
charge-transfer model (Baseline, One-time-constant Randles-type), the
porous-electrode transmission-line model (a supercapacitor's actual
electrode geometry), or in the purpose-built, literature-and-EC-Lab-
sourced "Supercapacitor (recommended)" category (see that section below
for citations: Gamry/ScienceDirect Randles-derived models, Cruz-Manzo &
Greenwood 2020's bounded-Warburg model, the Zubieta-Bonert two-branch
leakage model, and BioLogic Application Note 34's own published
supercapacitor circuit). The six generalized EC-Lab elements (La, Winf,
Ma, Mg, Ga, Gb) added for EC-Lab ZFit cross-validation are still fully
implemented below (their formulas are still used inside the
Supercapacitor category's Ma-based circuits) even though the standalone
non-supercapacitor circuits that used to showcase Winf/Mg/Ga/Gb/La in
isolation were removed along with Gerischer/Miscellaneous.

Architecture
------------
Every circuit -- preset or (in the future) user-built -- is represented as
a small expression TREE of the same few node types, so ONE evaluator and
ONE fitting routine work for all of them (this is what lets the auto-fit
feature try every topology in the library without one hand-written
impedance function per circuit):

    ("elem", kind, prefix)      -- a leaf circuit element
    ("series", [child, ...])    -- Z = sum(Z_child)
    ("parallel", [child, ...])  -- 1/Z = sum(1/Z_child)

`kind` is one of the fifteen element primitives below (matching EC-Lab
ZFit's own 13-element set plus this app's own T/de-Levie addition -- see
"EC-Lab cross-validation" below); `prefix` becomes part of the fitted
parameter name(s) for that element instance (so the same circuit can
contain e.g. two independent resistors "Rct1"/"Rct2").

Element formulas (verified against a source independent of memory before
being finalized -- see citations below; conventions for CPE/Warburg vary
between sources, so the exact form used here is stated explicitly rather
than left implicit):

    R:   Z = R
    C:   Z = 1 / (j*w*C)
    L:   Z = j*w*L
    Q:   Z = 1 / (Y0 * (j*w)^n)                                  (CPE; n=1 -> ideal capacitor)
    W:   Z = 1 / (Y0 * sqrt(j*w))                                 (infinite/semi-infinite Warburg)
    Wo:  Z = coth(B*sqrt(j*w)) / (Y0*sqrt(j*w))                   (finite-length, REFLECTIVE/blocking
                                                                    boundary -- "Warburg open": low-
                                                                    frequency impedance DIVERGES,
                                                                    capacitor-like, matching a
                                                                    boundary nothing can cross)
    Ws:  Z = tanh(B*sqrt(j*w)) / (Y0*sqrt(j*w))                   (finite-length, TRANSMISSIVE
                                                                    boundary -- "Warburg short": low-
                                                                    frequency impedance SATURATES to
                                                                    a finite resistance B/Y0, matching
                                                                    a boundary species freely cross)
    T:   Z = sqrt(Rp/Ydl) * coth(sqrt(Rp*Ydl)),  Ydl = Yt*(j*w)^nt
                                                                   (de Levie transmission-line /
                                                                    porous-electrode element, lumped-
                                                                    parameter semi-infinite-pore form
                                                                    with a CPE interfacial admittance
                                                                    per unit length, i.e. a purely
                                                                    polarizable/blocking pore wall as
                                                                    in an EDLC porous carbon -- no
                                                                    parallel Faradaic leakage resistor.
                                                                    Reduces to a bare CPE at high
                                                                    frequency; at low frequency Re(Z)
                                                                    does NOT plateau (a pure CPE still
                                                                    blocks DC) -- instead the Nyquist
                                                                    trace's low-frequency tail becomes
                                                                    a straight near-vertical line whose
                                                                    extrapolated real-axis intercept is
                                                                    Rs + Rp/3, the textbook "de Levie
                                                                    one-third rule" -- confirmed to
                                                                    match this implementation to 5
                                                                    significant figures by linear
                                                                    extrapolation of the low-frequency
                                                                    tail in a numerical check.)
    G:   Z = R / sqrt(1 + j*w*tau)                                (Gerischer -- chemical reaction
                                                                    coupled to diffusion)

    The following six were added after directly cross-checking this
    module's element set against the locally-installed EC-Lab (BioLogic)
    software's own manual (13 ZFit element types) -- see "EC-Lab cross-
    validation" below and docs/EQUATIONS.md for the full sourcing:

    La:  Z = L*(j*w)^a                                            (CPE-generalized inductor;
                                                                    a=1 -> plain L)
    Winf: Z = Rd*sqrt(g^2 + tau*j*w) / (g + tau*j*w)              (Warburg for convective/RDE
                                                                    diffusion, analytical
                                                                    approximation)
    Ma:  Z = R*coth((tau*j*w)^(a/2)) / (tau*j*w)^(a/2)            (CPE-generalized restricted
                                                                    diffusion; a=1 -> plain Wo --
                                                                    accounts for a DISTRIBUTION of
                                                                    pore relaxation times rather
                                                                    than one sharp time constant)
    Mg:  Z = R*coth((tau*j*w)^(g/2)) / (tau*j*w)^(1-g/2)          (Bisquert/anomalous diffusion;
                                                                    g=1 -> same base form as Ma(a=1)/
                                                                    Wo, but asymmetric exponents
                                                                    diverge from Ma for g!=1)
    Ga:  Z = R / sqrt(1 + (j*w*tau)^a)                            (CPE-generalized Gerischer #1;
                                                                    a=1 -> plain G)
    Gb:  Z = R / (1 + j*w*tau)^(a/2)                              (CPE-generalized Gerischer #2;
                                                                    a=1 -> plain G, diverges from Ga
                                                                    for a!=1)

Q, W formulas: Gamry Instruments, "Physical Electrochemistry & Equivalent
Circuit Elements" (Basics of EIS, Part 2/3), which gives CPE admittance
Y0*(jw)^n and infinite-Warburg admittance Y0*sqrt(jw) (impedance = 1 /
admittance in both cases, consistent with this module).

Wo/Ws tanh vs. coth assignment: verified independently two ways rather
than trusted from a single paraphrase (a Gamry search-result summary and
a Wikipedia summary DISAGREED with each other on which finite-Warburg
variant uses tanh vs. coth -- exactly the kind of convention conflict
that has to be resolved by physical reasoning, not guessed): (1) the
electrical transmission-line analogy (an open-circuit-terminated lossy
line -> coth; a short-circuit-terminated line -> tanh), and (2) the
low-frequency physical limit of each (coth(x)~1/x as x->0 makes Wo's
impedance diverge at DC, correct for a REFLECTIVE/blocking boundary where
charge has nowhere to go, i.e. behaves like it's "open" at DC; tanh(x)~x
as x->0 makes Ws's impedance saturate to a finite resistance B/Y0 at DC,
correct for a TRANSMISSIVE boundary that freely passes current, i.e.
behaves like it's "shorted" at DC). Both checks agree with each other and
with Wikipedia's "Warburg element" article, which is the convention used
here.

de Levie TLM: functional form (sqrt(Rp*Zi)*coth(sqrt(Rp/Zi)-style
argument) cross-checked against de Levie's original result as summarized
in multiple porous-electrode EIS reviews; the low-frequency real-axis
offset of Rp/3 predicted by this exact form is the well-known "de Levie
one-third rule" reported in the porous-electrode literature, which is a
useful independent sanity check on the implementation (see the unit test
in tests/ or the smoke-test script that exercises this module).

This is, like the rest of this app's EIS formulas, a standard textbook
formalism rather than tied to one single citable paper for the base
element forms -- treat it with the same "standard-but-not-individually-
cited" caveat already documented for the simpler Randles/CPE formulas in
core/eis_analysis.py and docs/EQUATIONS.md.

Which Warburg-family element to use for a SUPERCAPACITOR specifically:
use the bounded/finite-length forms (Wo/Ws), never the plain semi-
infinite "W", for a full-spectrum fit -- W has a fixed 45-degree phase
angle all the way to omega->0 and cannot reproduce a supercapacitor's
characteristic near-vertical low-frequency capacitive turn, so fitting it
against full-spectrum data typically drives it toward its lower search
bound as the optimizer tries to suppress an element the model can't
represent (see Cruz-Manzo & Greenwood, J. Electrochem. Soc. 167 (2020),
on the frequency transition from diffusion-like to capacitive response in
a blocked/bounded-diffusion Warburg -- the same low-frequency-divergent
coth-type behavior as this module's "Wo"). The "Supercapacitor
(recommended)" category below builds the standard extended-Randles
topology for this: Rs-(Rct||C or Q)-Wo/Ws[-tail C or Q], with the bounded
Warburg and an optional bare low-frequency tail capacitance appended
DOWNSTREAM of the semicircle stage rather than nested inside it.
"""
from dataclasses import dataclass, field
import numpy as np


# ---------------------------------------------------------------------------
# Element evaluation
# ---------------------------------------------------------------------------

def _z_R(omega, p, prefix):
    return p[prefix] * np.ones_like(omega, dtype=complex)


def _z_C(omega, p, prefix):
    return 1.0 / (1j * omega * p[prefix])


def _z_L(omega, p, prefix):
    return 1j * omega * p[prefix]


def _z_Q(omega, p, prefix):
    Y0 = p[f"{prefix}_Y0"]
    n = p[f"{prefix}_n"]
    return 1.0 / (Y0 * (1j * omega) ** n)


def _z_W(omega, p, prefix):
    Y0 = p[f"{prefix}_Y0"]
    return 1.0 / (Y0 * np.sqrt(1j * omega))


def _z_Wo(omega, p, prefix):
    Y0 = p[f"{prefix}_Y0"]
    B = p[f"{prefix}_B"]
    x = _clip_arg(B * np.sqrt(1j * omega))
    return _coth(x) / (Y0 * np.sqrt(1j * omega))


def _z_Ws(omega, p, prefix):
    Y0 = p[f"{prefix}_Y0"]
    B = p[f"{prefix}_B"]
    x = _clip_arg(B * np.sqrt(1j * omega))
    return np.tanh(x) / (Y0 * np.sqrt(1j * omega))


def _z_G(omega, p, prefix):
    """Gerischer element -- a chemical reaction coupled to diffusion
    (mixed ionic/electronic conductors, some battery insertion electrodes).
    Standard textbook form: Z = R / sqrt(1 + j*w*tau)."""
    R = p[f"{prefix}_R"]
    tau = p[f"{prefix}_tau"]
    return R / np.sqrt(1.0 + 1j * omega * tau)


def _z_T(omega, p, prefix):
    """de Levie transmission line, semi-infinite/lumped-finite pore,
    CPE interfacial admittance per unit length."""
    Rp = p[f"{prefix}_Rp"]
    Yt = p[f"{prefix}_Yt"]
    nt = p[f"{prefix}_nt"]
    Ydl = Yt * (1j * omega) ** nt
    x = _clip_arg(np.sqrt(Rp * Ydl))
    return np.sqrt(Rp / Ydl) * _coth(x)


def _z_La(omega, p, prefix):
    """Modified (CPE-style) inductor -- EC-Lab "La": Z = L*(jw)^a,
    a=1 reduces to the ideal inductor "L" above. Used to represent an
    unusual/non-ideal inductive high-frequency loop."""
    L = p[f"{prefix}_L"]
    a = p[f"{prefix}_a"]
    return L * (1j * omega) ** a


def _z_Winf(omega, p, prefix):
    """Warburg element for convective diffusion, analytical approximation
    (EC-Lab "Winf") -- a better approximation than the Nernst-hypothesis
    "Wd"/Ws form for a rotating-disk-electrode redox reaction; leads
    directly to the diffusing species' diffusion coefficient. Mainly
    relevant to RDE/redox-couple systems rather than porous supercapacitor
    electrodes, but included here for completeness of the EC-Lab element
    set: Z = Rd*sqrt(gamma^2 + tau*jw) / (gamma + tau*jw)."""
    Rd = p[f"{prefix}_Rd"]
    gamma = p[f"{prefix}_gamma"]
    tau = p[f"{prefix}_tau"]
    x = tau * 1j * omega
    return Rd * np.sqrt(gamma ** 2 + x) / (gamma + x)


def _z_Ma(omega, p, prefix):
    """Modified restricted (finite-length) diffusion -- EC-Lab "Ma": a
    CPE-generalized version of this module's "Wo" (a=1 reduces exactly to
    Wo), replacing Wo's fixed sqrt(j*w) frequency dependence with a
    variable-exponent (j*w)^(a/2) -- appropriate for a porous electrode
    with a DISTRIBUTION of pore relaxation times rather than one sharp
    time constant, which is the more realistic case for most real
    supercapacitor carbons. Z = R*coth((tau*jw)^(a/2)) / (tau*jw)^(a/2)."""
    R = p[f"{prefix}_R"]
    tau = p[f"{prefix}_tau"]
    a = p[f"{prefix}_a"]
    half_power = (tau * 1j * omega) ** (a / 2.0)
    x = _clip_arg(half_power)
    return R * _coth(x) / half_power


def _z_Mg(omega, p, prefix):
    """Anomalous (Bisquert) diffusion -- EC-Lab "Mg": a second, differently
    -asymmetric generalization of the restricted-diffusion element (the
    coth argument's power gamma/2 differs from the outer denominator's
    power 1-gamma/2, unlike "Ma" which uses the same exponent in both
    places) -- gamma=1 reduces to the same base form as Ma(a=1)/Wo. Used
    for anomalous/fractal transport in mesoporous films (originally
    developed for dye-sensitized solar cell electrodes).
    Z = R*coth((tau*jw)^(gamma/2)) / (tau*jw)^(1-gamma/2)."""
    R = p[f"{prefix}_R"]
    tau = p[f"{prefix}_tau"]
    gamma = p[f"{prefix}_gamma"]
    base = tau * 1j * omega
    x = _clip_arg(base ** (gamma / 2.0))
    return R * _coth(x) / (base ** (1.0 - gamma / 2.0))


def _z_Ga(omega, p, prefix):
    """Modified Gerischer #1 -- EC-Lab "Ga": generalizes this module's "G"
    by raising the (j*w*tau) term itself to a variable exponent a (a=1
    reduces exactly to G). Z = R / sqrt(1 + (j*w*tau)^a)."""
    R = p[f"{prefix}_R"]
    tau = p[f"{prefix}_tau"]
    a = p[f"{prefix}_a"]
    return R / np.sqrt(1.0 + (1j * omega * tau) ** a)


def _z_Gb(omega, p, prefix):
    """Modified Gerischer #2 -- EC-Lab "Gb": a second generalization of
    "G", applying the variable exponent a/2 to the WHOLE (1+j*w*tau) term
    instead of to (j*w*tau) alone (a=1 reduces exactly to G, same as Ga,
    but the two behave differently for a != 1).
    Z = R / (1 + j*w*tau)^(a/2)."""
    R = p[f"{prefix}_R"]
    tau = p[f"{prefix}_tau"]
    a = p[f"{prefix}_a"]
    return R / (1.0 + 1j * omega * tau) ** (a / 2.0)


def _coth(x):
    return 1.0 / np.tanh(x)


def _clip_arg(x, max_real: float = 20.0):
    """tanh/coth of a complex argument saturate to +-1 once the real part
    exceeds ~20 -- clip it there before calling np.tanh so large-|Z|
    high-frequency evaluations (routine during CNLS fitting, which probes
    parameter values far from any sensible physical range while searching)
    can't overflow the internal exp() and emit spurious RuntimeWarnings or
    NaNs. Purely a numerical-stability guard; does not change the returned
    value anywhere tanh/coth wouldn't already be saturated."""
    return np.clip(x.real, -max_real, max_real) + 1j * x.imag


_ELEMENT_FUNCS = {"R": _z_R, "C": _z_C, "L": _z_L, "Q": _z_Q, "W": _z_W, "Wo": _z_Wo, "Ws": _z_Ws,
                   "T": _z_T, "G": _z_G, "La": _z_La, "Winf": _z_Winf, "Ma": _z_Ma, "Mg": _z_Mg,
                   "Ga": _z_Ga, "Gb": _z_Gb}

# (param suffix, guess-kind) per element type -- guess-kind feeds
# _initial_value_and_bounds() below. Elements with one param have suffix "".
_ELEMENT_PARAMS = {
    "R": [("", "R")],
    "C": [("", "C")],
    "L": [("", "L")],
    "Q": [("_Y0", "Y0"), ("_n", "n")],
    "W": [("_Y0", "Y0")],
    "Wo": [("_Y0", "Y0"), ("_B", "B")],
    "Ws": [("_Y0", "Y0"), ("_B", "B")],
    "T": [("_Rp", "R"), ("_Yt", "Y0"), ("_nt", "n")],
    "G": [("_R", "R"), ("_tau", "tau")],
    "La": [("_L", "L"), ("_a", "n")],
    "Winf": [("_Rd", "R"), ("_gamma", "gamma"), ("_tau", "tau")],
    "Ma": [("_R", "R"), ("_tau", "tau"), ("_a", "n")],
    "Mg": [("_R", "R"), ("_tau", "tau"), ("_gamma", "n")],
    "Ga": [("_R", "R"), ("_tau", "tau"), ("_a", "n")],
    "Gb": [("_R", "R"), ("_tau", "tau"), ("_a", "n")],
}


def element_param_names(kind: str, prefix: str) -> list[str]:
    """Public accessor for the ordered parameter names belonging to ONE
    element instance (kind + prefix) -- e.g. element_param_names("Q",
    "Rct_cap") -> ["Rct_cap_Y0", "Rct_cap_n"]. Used by the schematic
    diagram renderer (ui/circuit_diagram.py) to label each drawn symbol
    with just its own fitted values, without reaching into this module's
    private _ELEMENT_PARAMS table directly."""
    return [f"{prefix}{suffix}" for suffix, _ in _ELEMENT_PARAMS[kind]]


def evaluate_circuit(tree, omega: np.ndarray, params: dict) -> np.ndarray:
    """Recursively evaluate a circuit tree's complex impedance at each
    angular frequency in `omega`, given a flat {param_name: value} dict."""
    node_type = tree[0]
    if node_type == "elem":
        _, kind, prefix = tree
        return _ELEMENT_FUNCS[kind](omega, params, prefix)
    if node_type == "series":
        _, children = tree
        total = np.zeros_like(omega, dtype=complex)
        for child in children:
            total = total + evaluate_circuit(child, omega, params)
        return total
    if node_type == "parallel":
        _, children = tree
        total_y = np.zeros_like(omega, dtype=complex)
        for child in children:
            total_y = total_y + 1.0 / evaluate_circuit(child, omega, params)
        return 1.0 / total_y
    raise ValueError(f"Unknown circuit tree node type: {node_type!r}")


def collect_params(tree) -> list[tuple[str, str]]:
    """Walk a circuit tree and return an ordered list of (param_name,
    guess_kind) for every free parameter, in a stable (depth-first) order.
    """
    out: list[tuple[str, str]] = []
    node_type = tree[0]
    if node_type == "elem":
        _, kind, prefix = tree
        for suffix, guess_kind in _ELEMENT_PARAMS[kind]:
            out.append((f"{prefix}{suffix}", guess_kind))
    else:
        _, children = tree
        for child in children:
            out.extend(collect_params(child))
    return out


# Generic per-guess-kind default value / lower bound / upper bound. Not
# tuned per circuit -- deliberately generic so the SAME function works for
# any of the ~100 library circuits (and future custom-built ones) without
# per-circuit hand-tuning; nonlinear least squares only needs to start in
# the right order of magnitude, and the fit-quality/convergence reporting
# already tells the user when that wasn't good enough.
_GUESS_DEFAULTS = {
    "C": (1e-4, 1e-12, 10.0),
    "L": (1e-6, 0.0, 10.0),
    "Y0": (1e-4, 1e-12, 10.0),
    "n": (0.85, 0.3, 1.0),
    "B": (1.0, 1e-6, 1e6),
    # "tau" is handled by its own data-scaled branch in
    # initial_guess_and_bounds below, not this generic table.
    "gamma": (1.0, 1e-3, 1e3),
}


def initial_guess_and_bounds(spec: CircuitSpec, frequency_hz: np.ndarray,
                              z_re_ohm: np.ndarray) -> tuple[list, list, list]:
    """Build (x0, lower_bounds, upper_bounds) for every parameter in
    `spec.param_order`, in order, from the data's own scale:
    - a parameter literally named "Rs" (the series/ohmic resistance every
      circuit in this library starts with) is seeded from the highest-
      frequency real-axis value;
    - a parameter ending "_Rp" (transmission-line pore resistance) is
      seeded from the full real-axis span (pore resistance is typically
      comparable in scale to the other charge-transfer resistances);
    - any other resistor (e.g. Rct) is seeded from half the real-axis span
      of the HIGH-to-MID frequency portion of the spectrum only (the top
      60% by frequency), not the full sweep: a low-frequency Warburg/CPE
      tail can dominate the full real-axis span (its impedance diverges
      toward DC), which made the plain full-span estimate badly overshoot
      Rct for any circuit with such a tail -- confirmed by a self-
      consistency check (fit a circuit to its own noise-free synthetic
      data) that only converged once Rct's initial guess stopped being
      thrown off by that low-frequency divergence;
    - Y0 (CPE/Warburg admittance) and B (finite-Warburg length parameter)
      are seeded from the data's OWN impedance and frequency scale (see
      below) rather than a fixed constant -- a fixed Y0=1e-4/B=1.0 default
      regardless of whether the spectrum spans milliohms or kilohms, or
      millihertz or megahertz, was the root cause of finite-Warburg (Wo/
      Ws) fits landing on wildly wrong B values (self-consistency testing
      against synthetic data with a known B showed >10x, sometimes
      >1000x, recovered-vs-true error): the search started and was bounded
      many orders of magnitude from where the data actually lives.
    - all other kinds (C, L, n, Gerischer tau) use fixed generic defaults
      in `_GUESS_DEFAULTS`.
    """
    rs_guess = float(z_re_ohm[np.argmax(frequency_hz)])
    r_span = max(float(np.max(z_re_ohm) - np.min(z_re_ohm)), 1e-6)

    # High-to-mid-frequency-only real-axis span, for the Rct-like guess --
    # excludes the low-frequency portion where a Warburg/CPE tail's
    # impedance can diverge and swamp the semicircle's own scale.
    freq_arr = np.asarray(frequency_hz, dtype=float)
    hf_order = np.argsort(-freq_arr)
    n_hf = max(4, int(len(hf_order) * 0.6))
    hf_idx = hf_order[:n_hf]
    zre_hf = np.asarray(z_re_ohm, dtype=float)[hf_idx]
    r_span_hf = max(float(np.max(zre_hf) - np.min(zre_hf)), 1e-6)

    omega_data = 2 * np.pi * np.asarray(frequency_hz, dtype=float)
    # geometric mean angular frequency -- the natural "center" of a
    # log-swept EIS spectrum, used to scale Y0, C, and B to the data's own
    # timescale instead of a fixed constant.
    omega_mid = float(np.sqrt(np.min(omega_data) * np.max(omega_data)))
    # Y0/C guesses use r_span_hf (not the full-spectrum r_span) for the
    # same reason the Rct-like resistor guess above does: a low-frequency
    # Warburg/CPE tail dominates the FULL real-axis span, which -- for a
    # circuit with more than one capacitive-ish element (a semicircle
    # capacitance AND a downstream Warburg, say) -- was seeding every one
    # of them from the same tail-dominated scale and left the optimizer
    # unable to tell them apart; self-consistency testing (fitting a
    # circuit to its own noise-free synthetic data) only converged once
    # each element's guess used the frequency range where ITS OWN
    # contribution actually dominates the spectrum shape.
    # Y0 guess: for Z = 1/(Y0*(jw)^n), |Z| ~ r_span_hf at the mid-frequency
    # point implies Y0 ~ 1/(r_span_hf * omega_mid^0.5) (n=0.5-0.85 covers
    # both CPE and Warburg-like elements reasonably as an order-of-
    # magnitude seed -- exact n is itself a free fit parameter).
    y0_guess = 1.0 / max(r_span_hf * np.sqrt(omega_mid), 1e-12)
    # C guess: for Z = 1/(jwC), |Z| ~ r_span_hf at the mid-frequency point
    # implies C ~ 1/(r_span_hf * omega_mid) -- same reasoning as Y0 above,
    # with n=1 (ideal capacitor) instead of a general CPE exponent.
    c_guess = 1.0 / max(r_span_hf * omega_mid, 1e-12)
    # B guess: the tanh/coth argument is B*sqrt(jw), dimensionless only if
    # B ~ 1/sqrt(omega) -- seeding B so its crossover lands near the
    # middle of the measured frequency window puts the search where the
    # curvature that actually constrains B lives, rather than off the
    # edge of the measured spectrum entirely.
    b_guess = 1.0 / np.sqrt(omega_mid)
    # tau guess: Gerischer/restricted-diffusion time constants appear as
    # (j*w*tau) or similar, dimensionless only if tau ~ 1/omega -- seeded
    # from the data's own mid-frequency scale for the same reason as B
    # above (a fixed tau=1.0 s default was only ever right by coincidence
    # for whatever frequency range a given spectrum happened to use).
    tau_guess = 1.0 / omega_mid

    param_kinds = spec.param_kinds
    x0, lo, hi = [], [], []
    for name in spec.param_order:
        kind = param_kinds[name]
        if kind == "R":
            if name == "Rs":
                x0.append(max(rs_guess, 1e-6))
            elif name.endswith("_Rp"):
                x0.append(r_span)
            elif name == "Rleak":
                # A leakage/self-discharge resistance is physically
                # expected to be LARGE (self-discharge time constants of
                # hours-to-days imply kOhm-MOhm, orders of magnitude above
                # the other resistors in the same circuit) -- seeding it
                # from the same r_span_hf/2 scale as a charge-transfer-like
                # resistor left the optimizer starting many orders of
                # magnitude away from realistic leakage values and unable
                # to converge (confirmed via self-consistency testing with
                # a physically realistic Rleak >> Rs/R2).
                x0.append(max(r_span_hf * 100, 1e3))
            else:
                x0.append(max(r_span_hf / 2, 1e-6))
            lo.append(0.0)
            hi.append(np.inf)
        elif kind == "Y0":
            x0.append(y0_guess)
            lo.append(y0_guess * 1e-4)
            hi.append(y0_guess * 1e4)
        elif kind == "B":
            x0.append(b_guess)
            lo.append(b_guess * 1e-3)
            hi.append(b_guess * 1e3)
        elif kind == "tau":
            x0.append(tau_guess)
            lo.append(tau_guess * 1e-3)
            hi.append(tau_guess * 1e3)
        elif kind == "C":
            _, low, high = _GUESS_DEFAULTS[kind]
            # c_guess can blow past these FIXED bounds for a circuit with
            # no real-axis variation to scale from (e.g. a bare Rs-C with
            # no semicircle, where r_span_hf collapses to its floor value)
            # -- clip rather than let scipy reject an out-of-bounds guess.
            x0.append(float(np.clip(c_guess, low, high)))
            lo.append(low)
            hi.append(high)
        else:
            default, low, high = _GUESS_DEFAULTS[kind]
            x0.append(default)
            lo.append(low)
            hi.append(high)
    return x0, lo, hi


# ---------------------------------------------------------------------------
# Circuit specs (preset library)
# ---------------------------------------------------------------------------

@dataclass
class CircuitSpec:
    name: str          # stable machine id, e.g. "randles_Q_Wo_L"
    display: str       # Boukamp-CDC-style human string, e.g. "L-Rs(Rct(Q-Wo))"
    category: str      # for UI grouping
    tree: tuple
    param_order: list = field(default_factory=list)

    def __post_init__(self):
        if not self.param_order:
            self.param_order = [name for name, _ in collect_params(self.tree)]

    @property
    def param_kinds(self) -> dict:
        return dict(collect_params(self.tree))

    @property
    def n_params(self) -> int:
        return len(self.param_order)


def _e(kind: str, prefix: str) -> tuple:
    return ("elem", kind, prefix)


def _series(*children) -> tuple:
    return ("series", list(children))


def _parallel(*children) -> tuple:
    return ("parallel", list(children))


def _maybe_L(tree, with_l: bool, l_prefix: str = "L"):
    return _series(_e("L", l_prefix), tree) if with_l else tree


def _randles_branch(prefix: str, cap_kind: str, warburg_kind: str | None) -> tuple:
    """Rct-parallel-branch of a Randles-type stage: (Rct) || (cap [+ warburg]).
    cap_kind in {"C","Q"}; warburg_kind in {None,"W","Wo","Ws"}."""
    cap = _e(cap_kind, f"{prefix}_cap")
    branch = cap if warburg_kind is None else _series(cap, _e(warburg_kind, f"{prefix}_zw"))
    return _parallel(_e("R", prefix), branch)


CIRCUITS: dict[str, CircuitSpec] = {}


def _register(spec: CircuitSpec) -> None:
    if spec.name in CIRCUITS:
        raise ValueError(f"Duplicate circuit name: {spec.name}")
    CIRCUITS[spec.name] = spec


def _build_library() -> None:
    # --- A. Baselines -----------------------------------------------------
    _register(CircuitSpec("baseline_R", "Rs", "Baseline",
                           _e("R", "Rs")))
    _register(CircuitSpec("baseline_RC", "Rs-C", "Baseline",
                           _series(_e("R", "Rs"), _e("C", "C"))))
    _register(CircuitSpec("baseline_RQ", "Rs-Q", "Baseline",
                           _series(_e("R", "Rs"), _e("Q", "Q"))))

    # --- B. Single time-constant (Randles-type) ----------------------------
    warburg_opts = [None, "W", "Wo", "Ws"]
    cap_opts = ["C", "Q"]
    for cap in cap_opts:
        for wb in warburg_opts:
            for with_l in (False, True):
                wb_tag = wb or "none"
                name = f"randles1_{cap}_{wb_tag}" + ("_L" if with_l else "")
                branch = _randles_branch("Rct", cap, wb)
                tree = _maybe_L(_series(_e("R", "Rs"), branch), with_l)
                wb_disp = "" if wb is None else f"-{wb}"
                disp = f"{'L-' if with_l else ''}Rs(Rct({cap}{wb_disp}))"
                _register(CircuitSpec(name, disp, "One time constant (Randles-type)", tree))

    # --- E. Transmission line (de Levie, porous electrode) -----------------
    for with_l in (False, True):
        name = f"tlm_semiinf" + ("_L" if with_l else "")
        tree = _maybe_L(_series(_e("R", "Rs"), _e("T", "TLM")), with_l)
        disp = f"{'L-' if with_l else ''}Rs-TLM(semi-infinite pore)"
        _register(CircuitSpec(name, disp, "Transmission line (porous electrode)", tree))

        name = f"tlm_blocking" + ("_L" if with_l else "")
        tree = _maybe_L(_series(_e("R", "Rs"), _e("T", "TLM"), _e("R", "Rterm")), with_l)
        disp = f"{'L-' if with_l else ''}Rs-TLM-Rterm(blocked pore end)"
        _register(CircuitSpec(name, disp, "Transmission line (porous electrode)", tree))

        name = f"tlm_plus_randles" + ("_L" if with_l else "")
        branch = _randles_branch("Rct", "Q", None)
        tree = _maybe_L(_series(_e("R", "Rs"), _e("T", "TLM"), branch), with_l)
        disp = f"{'L-' if with_l else ''}Rs-TLM-(Rct-Q) (pore + outer-surface charge transfer)"
        _register(CircuitSpec(name, disp, "Transmission line (porous electrode)", tree))

        # Two porous electrodes in series -- the actual geometry of a
        # symmetric 2-electrode supercapacitor cell (this app's most common
        # real use case), each electrode's pore network as its own TLM.
        name = f"tlm_two_electrode" + ("_L" if with_l else "")
        tree = _maybe_L(_series(_e("R", "Rs"), _e("T", "TLM1"), _e("T", "TLM2")), with_l)
        disp = f"{'L-' if with_l else ''}Rs-TLM1-TLM2 (symmetric 2-electrode cell, two porous electrodes)"
        _register(CircuitSpec(name, disp, "Transmission line (porous electrode)", tree))

    # --- H. Supercapacitor (recommended): resolvable contact/charge-
    #        transfer semicircle in series with a BOUNDED (finite-length,
    #        blocking-boundary) Warburg -- Wo or Ws, never the plain
    #        semi-infinite "W" -- appended DOWNSTREAM of the semicircle
    #        stage (not nested inside the Rct-parallel branch the way the
    #        "One/Two/Three time constant" categories build it). This is
    #        the standard "modified/extended Randles circuit for
    #        supercapacitors" reported in the literature, and it was
    #        previously MISSING from this library: every circuit generated
    #        by the "One/Two/Three time constant" categories above wraps
    #        every capacitor/CPE in a parallel resistor, so there was no
    #        way to express a plain downstream Warburg stage.
    #
    #        Plain semi-infinite Warburg "W" is deliberately NOT offered
    #        here: W has a fixed 45-degree phase angle all the way to
    #        omega->0 and cannot reproduce a supercapacitor's near-vertical
    #        low-frequency capacitive turn, so fitting it against full-
    #        spectrum supercapacitor data typically drives its Y0 toward
    #        the fit's lower bound as the optimizer tries to suppress an
    #        element the model can't actually use -- which looks like "the
    #        Warburg element didn't show up in the fit," but is really a
    #        modeling-choice mismatch, not a bug. (Consistent with
    #        Cruz-Manzo & Greenwood, J. Electrochem. Soc. 167 (2020), on
    #        the frequency transition from diffusion-like to capacitive
    #        response in a blocked/bounded-diffusion Warburg -- the same
    #        coth-type low-frequency-divergent behavior as this module's
    #        "Wo" element, documented above.) eis_analysis.
    #        fit_equivalent_circuit also now flags a Warburg (or any)
    #        parameter that lands pinned at its lower/upper search bound,
    #        so that suppression is reported explicitly rather than left
    #        for the user to notice as a suspiciously tiny/huge number.
    #
    #        A further "-tail" variant (an extra bare capacitor/CPE
    #        appended after the Warburg, representing a separate low-
    #        frequency bulk/mass capacitance) was tried and DELIBERATELY
    #        DROPPED: self-consistency testing (fitting a circuit to its
    #        own noise-free synthetic data) showed it reliably converges
    #        to a WRONG local minimum from any realistic starting guess --
    #        confirmed not a simple bad-initial-guess problem, since
    #        starting the optimizer exactly at the true parameters DOES
    #        recover them perfectly (chi2=0); a Warburg element and a
    #        trailing CPE/capacitor both produce increasingly capacitive-
    #        like impedance toward low frequency and are too easily
    #        confused for each other by a single-start least-squares fit.
    #        Shipping a preset that systematically fits to the wrong
    #        answer would be worse than not offering it.
    for cap in cap_opts:
        for wb in ("Wo", "Ws"):
            for with_l in (False, True):
                name = f"supercap_{cap}_{wb}" + ("_L" if with_l else "")
                semicircle = _parallel(_e("R", "Rct"), _e(cap, "Rct_cap"))
                tree = _maybe_L(_series(_e("R", "Rs"), semicircle, _e(wb, "Wb")), with_l)
                disp = f"{'L-' if with_l else ''}Rs(Rct-{cap})-{wb}"
                _register(CircuitSpec(name, disp, "Supercapacitor (recommended)", tree))

    # --- H1b. Generalized (CPE-exponent) restricted-diffusion variant ------
    #        Z = Rs + (Rct || cap) + Ma -- EC-Lab's "Ma" (modified
    #        restricted diffusion) is this library's "Wo" generalized from
    #        a fixed sqrt(j*w) frequency dependence to a variable-exponent
    #        (j*w)^(a/2), directly relevant to a real porous supercapacitor
    #        electrode with a DISTRIBUTION of pore relaxation times rather
    #        than one sharp time constant. a=1 reduces exactly to the
    #        plain Wo-based entries above -- offering Ma lets the fit
    #        itself discover whether that idealization is adequate for a
    #        given electrode, at the cost of one extra free parameter.
    for cap in cap_opts:
        for with_l in (False, True):
            name = f"supercap_{cap}_Ma" + ("_L" if with_l else "")
            semicircle = _parallel(_e("R", "Rct"), _e(cap, "Rct_cap"))
            tree = _maybe_L(_series(_e("R", "Rs"), semicircle, _e("Ma", "Mb")), with_l)
            disp = f"{'L-' if with_l else ''}Rs(Rct-{cap})-Ma"
            _register(CircuitSpec(name, disp, "Supercapacitor (recommended)", tree))

    # --- H2. Two-branch (Zubieta-Bonert) supercapacitor model -------------
    #        Z = Rs + [C1 || Rleak || (R2-C2 series)]
    #        Source: L. Zubieta and R. Bonert, "Characterization of
    #        double-layer capacitors for power electronics applications,"
    #        IEEE Trans. Ind. Appl., vol. 36, no. 1, pp. 199-205, 2000 --
    #        the canonical "two-branch" supercapacitor model: a fast/
    #        immediate branch (C1, the Helmholtz/EDL capacitance) and a
    #        slow/delayed branch (R2 in series with C2, the diffuse-layer
    #        capacitance, reached only after charge redistributes through
    #        R2), both in parallel with a leakage resistance Rleak,
    #        downstream of the series/solution resistance Rs. Corroborated
    #        as a standard supercapacitor EIS-equivalent-circuit entry
    #        (described there as exactly this 5-parameter, 2-capacitor/
    #        3-resistor structure: ESR + leakage resistance + a diffusion/
    #        redistribution resistance) by C. Shen, S. Xu, Y. Xie, M.
    #        Sanghadasa, X. Wang, L. Lin, "A Review of On-Chip Micro
    #        Supercapacitors for Integrated Self-Powering Systems," J.
    #        Microelectromech. Syst., vol. 26, pp. 949-965, 2017 (fig. 2e).
    #        The original Zubieta-Bonert model uses a voltage-dependent
    #        (nonlinear) C1 for time-domain pulse-response prediction; this
    #        implementation uses the linearized small-signal form (C1, C2
    #        each optionally a CPE) appropriate for EIS/CNLS fitting.
    for c1 in cap_opts:
        for c2 in cap_opts:
            for with_l in (False, True):
                name = f"supercap_twobranch_{c1}{c2}" + ("_L" if with_l else "")
                fast_branch = _e(c1, "C1")
                slow_branch = _series(_e("R", "R2"), _e(c2, "C2"))
                node = _parallel(fast_branch, _e("R", "Rleak"), slow_branch)
                tree = _maybe_L(_series(_e("R", "Rs"), node), with_l)
                disp = f"{'L-' if with_l else ''}Rs({c1}||Rleak||(R2-{c2}))  [two-branch]"
                _register(CircuitSpec(name, disp, "Supercapacitor (recommended)", tree))

    # --- H3. BioLogic Application Note #34 full-spectrum model -------------
    #        Z = L + Rs + [C2 || (R2-M2)]   (M2 = restricted/bounded
    #        diffusion, i.e. this library's "Wo" -- confirmed identical
    #        formula to EC-Lab's own "M" element, cross-checked directly
    #        against BioLogic's EC-Lab software manual)
    #        Source: BioLogic, EC-Lab Application Note #34, "Supercapacitors
    #        Investigations Part II: Time Constant" (2010, rev. 2019) --
    #        BioLogic's own worked example fitting a REAL commercial 22 F
    #        supercapacitor's full-spectrum EIS data, explicitly presented
    #        as the circuit needed once a plain series R+C model stops
    #        working above ~1 Hz (where the Nyquist trace's phase shifts
    #        from 45 degrees toward 90 degrees). Reported fitted result:
    #        R1=31.61 mOhm, L1=98.45 nH, C2=15.59 mF, R2=4.23 mOhm,
    #        Rd2=37.89 mOhm, taud2=1.044 s. Two PARALLEL current paths
    #        after Rs+L: a purely capacitive double-layer path (C2 alone,
    #        no series resistance) and a resistive-then-diffusive Faradaic/
    #        charge-transfer path (R2 in series with the restricted-
    #        diffusion element) -- the mirror image of this library's other
    #        semicircle+Warburg entries, which put the bare RESISTOR (not
    #        the bare capacitor) in its own branch.
    for cap in cap_opts:
        for with_l in (False, True):
            name = f"supercap_an34_{cap}" + ("_L" if with_l else "")
            branch = _parallel(_e(cap, "C2"), _series(_e("R", "R2"), _e("Wo", "M2")))
            tree = _maybe_L(_series(_e("R", "Rs"), branch), with_l)
            disp = f"{'L-' if with_l else ''}Rs({cap}2||(R2-M2))  [BioLogic AN34]"
            _register(CircuitSpec(name, disp, "Supercapacitor (recommended)", tree))


_build_library()


def all_circuit_names() -> list[str]:
    return list(CIRCUITS.keys())


def get_circuit(name: str) -> CircuitSpec:
    return CIRCUITS[name]


def circuits_by_category() -> dict[str, list[CircuitSpec]]:
    out: dict[str, list[CircuitSpec]] = {}
    for spec in CIRCUITS.values():
        out.setdefault(spec.category, []).append(spec)
    return out
