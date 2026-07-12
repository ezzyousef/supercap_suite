"""Generic equivalent-circuit engine + a ~100-circuit preset library for
EIS/PEIS complex nonlinear least-squares (CNLS) fitting.

Architecture
------------
Every circuit -- preset or (in the future) user-built -- is represented as
a small expression TREE of the same few node types, so ONE evaluator and
ONE fitting routine work for all of them (this is what lets the auto-fit
feature try ~100 topologies without ~100 hand-written impedance
functions):

    ("elem", kind, prefix)      -- a leaf circuit element
    ("series", [child, ...])    -- Z = sum(Z_child)
    ("parallel", [child, ...])  -- 1/Z = sum(1/Z_child)

`kind` is one of the seven element primitives below; `prefix` becomes part
of the fitted parameter name(s) for that element instance (so the same
circuit can contain e.g. two independent resistors "Rct1"/"Rct2").

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
                   "T": _z_T, "G": _z_G}

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
    "tau": (1.0, 1e-6, 1e6),
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
    - any other resistor is seeded from half the real-axis span (a rough
      charge-transfer-resistance scale);
    - all other kinds (C, L, Y0/CPE-admittance, n, Warburg B, Gerischer
      tau) use fixed generic defaults in `_GUESS_DEFAULTS`.
    """
    rs_guess = float(z_re_ohm[np.argmax(frequency_hz)])
    r_span = max(float(np.max(z_re_ohm) - np.min(z_re_ohm)), 1e-6)

    param_kinds = spec.param_kinds
    x0, lo, hi = [], [], []
    for name in spec.param_order:
        kind = param_kinds[name]
        if kind == "R":
            if name == "Rs":
                x0.append(max(rs_guess, 1e-6))
            elif name.endswith("_Rp"):
                x0.append(r_span)
            else:
                x0.append(max(r_span / 2, 1e-6))
            lo.append(0.0)
            hi.append(np.inf)
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

    # --- C. Two time constants ----------------------------------------------
    for cap1 in cap_opts:
        for cap2 in cap_opts:
            for wb in warburg_opts:
                for with_l in (False, True):
                    wb_tag = wb or "none"
                    name = f"randles2_{cap1}_{cap2}_{wb_tag}" + ("_L" if with_l else "")
                    branch1 = _randles_branch("R1", cap1, None)
                    branch2 = _randles_branch("R2", cap2, wb)
                    tree = _maybe_L(_series(_e("R", "Rs"), branch1, branch2), with_l)
                    wb_disp = "" if wb is None else f"-{wb}"
                    disp = f"{'L-' if with_l else ''}Rs(R1{cap1})(R2({cap2}{wb_disp}))"
                    _register(CircuitSpec(name, disp, "Two time constants", tree))

    # --- D. Three time constants (curated stage patterns) -------------------
    patterns = [("C", "C", "C"), ("Q", "Q", "Q"), ("C", "Q", "C"), ("Q", "C", "Q")]
    for pat in patterns:
        for wb in warburg_opts:
            for with_l in (False, True):
                wb_tag = wb or "none"
                name = f"randles3_{'_'.join(pat)}_{wb_tag}" + ("_L" if with_l else "")
                branch1 = _randles_branch("R1", pat[0], None)
                branch2 = _randles_branch("R2", pat[1], None)
                branch3 = _randles_branch("R3", pat[2], wb)
                tree = _maybe_L(_series(_e("R", "Rs"), branch1, branch2, branch3), with_l)
                wb_disp = "" if wb is None else f"-{wb}"
                disp = f"{'L-' if with_l else ''}Rs(R1{pat[0]})(R2{pat[1]})(R3({pat[2]}{wb_disp}))"
                _register(CircuitSpec(name, disp, "Three time constants", tree))

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

    # --- G. Gerischer element (mixed ionic/electronic conduction, battery-
    #        type insertion electrodes with a coupled chemical reaction) ----
    _register(CircuitSpec("gerischer_R", "Rs-G", "Gerischer (mixed conduction)",
                           _series(_e("R", "Rs"), _e("G", "G"))))
    for cap in cap_opts:
        for with_l in (False, True):
            name = f"gerischer_{cap}" + ("_L" if with_l else "")
            branch = _parallel(_e("R", "Rct"), _series(_e(cap, "Rct_cap"), _e("G", "zg")))
            tree = _maybe_L(_series(_e("R", "Rs"), branch), with_l)
            disp = f"{'L-' if with_l else ''}Rs(Rct({cap}-G))"
            _register(CircuitSpec(name, disp, "Gerischer (mixed conduction)", tree))

    # --- F. Miscellaneous / composite ---------------------------------------
    for wb in ("W", "Wo", "Ws"):
        _register(CircuitSpec(f"misc_R_{wb}", f"Rs-{wb}", "Miscellaneous",
                               _series(_e("R", "Rs"), _e(wb, "zw"))))
    _register(CircuitSpec("misc_RL", "Rs-L", "Miscellaneous",
                           _series(_e("R", "Rs"), _e("L", "L"))))
    _register(CircuitSpec("misc_RLC", "L-Rs-C", "Miscellaneous",
                           _series(_e("L", "L"), _e("R", "Rs"), _e("C", "C"))))
    _register(CircuitSpec("misc_RLQ", "L-Rs-Q", "Miscellaneous",
                           _series(_e("L", "L"), _e("R", "Rs"), _e("Q", "Q"))))


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
