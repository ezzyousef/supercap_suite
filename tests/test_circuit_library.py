"""Ground-truth tests for core.circuit_library's element formulas and the
generic CNLS fitting engine (core.eis_analysis), including the physical
asymptotic-limit checks used to verify the Warburg-open/short and
transmission-line conventions before they were finalized (see the module
docstring in circuit_library.py for the reasoning).

The production library was pruned to supercapacitor-only circuits (see
circuit_library.py's module docstring), removing the generic Miscellaneous
and Gerischer categories that a few of these tests used to pull minimal
diagnostic circuits (bare "Rs-element", no Rct) from. Those tests are
about ELEMENT FORMULA / FITTING-PIPELINE correctness, not about whether a
circuit is a supercapacitor model, so they build the same minimal trees
directly (via _bare_rs_element / _register_test_only_circuit below)
instead of depending on circuits that no longer exist in the production
registry -- this keeps the physics coverage without reintroducing
non-supercapacitor circuits into the app.
"""
import numpy as np
import pytest

from core import circuit_library as cl
from core import eis_analysis as eis


def _bare_rs_element(kind: str, prefix: str = "zw") -> tuple:
    """A minimal Rs-element series tree, e.g. what "misc_R_Wo" used to be
    before the library was pruned to supercapacitor-only circuits --
    built directly rather than looked up, since evaluate_circuit() works
    on any tree without requiring it to be registered."""
    return ("series", [("elem", "R", "Rs"), ("elem", kind, prefix)])


def _register_test_only_circuit(name: str, tree: tuple) -> None:
    """Register a minimal circuit under a name reserved for this test
    file only (never used by the production app, which only ever sees
    whatever core/circuit_library.py's own _build_library() registers at
    import time) -- needed for the handful of tests that exercise the
    FITTING pipeline (fit_equivalent_circuit takes a registered name, not
    a raw tree) rather than just evaluate_circuit(). No-op if already
    registered (pytest can import this module more than once in some
    run configurations)."""
    if name not in cl.CIRCUITS:
        cl._register(cl.CircuitSpec(name, name, "Test-only (not in production library)", tree))


def test_library_has_over_45_supercapacitor_circuits():
    assert len(cl.CIRCUITS) >= 45


def test_library_contains_only_supercapacitor_relevant_categories():
    """Regression for the library-pruning request: no generic
    battery/corrosion/fuel-cell (Gerischer) or unsourced combinatorial
    multi-time-constant categories should be present -- every PRODUCTION
    circuit (i.e. excluding this test file's own test-only diagnostic
    registrations, see _register_test_only_circuit) exposed to the EIS
    tab's category dropdown must be a supercapacitor model (Baseline,
    one-time-constant Randles-type, porous-electrode transmission line,
    or the purpose-built Supercapacitor category)."""
    categories = {c for c in cl.circuits_by_category().keys()
                  if not c.startswith("Test-only")}
    assert categories == {
        "Baseline",
        "One time constant (Randles-type)",
        "Transmission line (porous electrode)",
        "Supercapacitor (recommended)",
    }


@pytest.mark.parametrize("kind,generalized_params,base_kind,base_params", [
    ("La", {"x_L": 1e-6, "x_a": 1.0}, "L", {"x": 1e-6}),
    ("Ma", {"x_R": 50.0, "x_tau": 2.0, "x_a": 1.0}, "Wo",
     {"x_Y0": np.sqrt(2.0) / 50.0, "x_B": np.sqrt(2.0)}),
    ("Mg", {"x_R": 50.0, "x_tau": 2.0, "x_gamma": 1.0}, "Wo",
     {"x_Y0": np.sqrt(2.0) / 50.0, "x_B": np.sqrt(2.0)}),
    ("Ga", {"x_R": 50.0, "x_tau": 2.0, "x_a": 1.0}, "G", {"x_R": 50.0, "x_tau": 2.0}),
    ("Gb", {"x_R": 50.0, "x_tau": 2.0, "x_a": 1.0}, "G", {"x_R": 50.0, "x_tau": 2.0}),
])
def test_generalized_ec_lab_elements_reduce_to_base_element(kind, generalized_params, base_kind, base_params):
    """The six elements added after cross-checking EC-Lab's own ZFit
    element library (La, Winf, Ma, Mg, Ga, Gb) are each a generalization
    of a simpler element already in this library -- at their "neutral"
    exponent value (a=1 or gamma=1) they must reduce EXACTLY to that
    simpler element's impedance, not just approximately."""
    omega = np.logspace(-2, 4, 50)
    z_generalized = cl.evaluate_circuit(("elem", kind, "x"), omega, generalized_params)
    z_base = cl.evaluate_circuit(("elem", base_kind, "x"), omega, base_params)
    np.testing.assert_allclose(z_generalized, z_base, rtol=1e-6)


def test_winf_element_is_finite_and_well_defined():
    """Winf (RDE convective-diffusion, analytical approximation) has no
    simpler-element reduction to check against, so this just confirms it
    evaluates to a finite, non-degenerate impedance across a realistic
    frequency sweep."""
    omega = np.logspace(-2, 4, 50)
    z = cl.evaluate_circuit(("elem", "Winf", "x"), omega, {"x_Rd": 10.0, "x_gamma": 1.0, "x_tau": 1.0})
    assert np.all(np.isfinite(z.real)) and np.all(np.isfinite(z.imag))
    assert np.any(np.abs(z) > 1e-6)


# gerischer_R_Ga/Gb, misc_R_La/Winf/Mg no longer exist in the pruned
# (supercapacitor-only) production library -- registered as test-only
# circuits below purely to keep exercising the FITTING PIPELINE against
# these element formulas (evaluate_circuit's own correctness is already
# covered by test_generalized_ec_lab_elements_reduce_to_base_element).
_TEST_ONLY_TREES = {
    "gerischer_R_Ga": _bare_rs_element("Ga", "G"),
    "gerischer_R_Gb": _bare_rs_element("Gb", "G"),
    "misc_R_La": _bare_rs_element("La", "La"),
    "misc_R_Winf": _bare_rs_element("Winf", "zw"),
    "misc_R_Mg": _bare_rs_element("Mg", "zw"),
}


@pytest.mark.parametrize("name,true_params", [
    ("supercap_Q_Ma", {"Rs": 50.0, "Rct": 50.0, "Rct_cap_Y0": 5e-3, "Rct_cap_n": 0.9,
                        "Mb_R": 40.0, "Mb_tau": 2.0, "Mb_a": 0.8}),
    ("gerischer_R_Ga", {"Rs": 20.0, "G_R": 50.0, "G_tau": 2.0, "G_a": 0.9}),
    ("gerischer_R_Gb", {"Rs": 20.0, "G_R": 50.0, "G_tau": 2.0, "G_a": 0.9}),
    ("misc_R_La", {"Rs": 20.0, "La_L": 1e-6, "La_a": 0.9}),
    ("misc_R_Winf", {"Rs": 20.0, "zw_Rd": 30.0, "zw_gamma": 1.0, "zw_tau": 1.0}),
    ("misc_R_Mg", {"Rs": 20.0, "zw_R": 30.0, "zw_tau": 1.0, "zw_gamma": 0.8}),
])
def test_new_ec_lab_sourced_circuits_recover_true_parameters(name, true_params):
    """Preset circuits built from the six new EC-Lab-sourced elements must
    actually be fittable, not just evaluable -- fit each to its own
    noise-free synthetic data (with multistart, matching what the EIS
    tab's "Fit this circuit" button does) and confirm it recovers the
    true parameters, not a local-minimum near-miss."""
    if name in _TEST_ONLY_TREES:
        _register_test_only_circuit(name, _TEST_ONLY_TREES[name])
    freq = np.logspace(4, -3, 60)
    omega = 2 * np.pi * freq
    spec = cl.get_circuit(name)
    assert set(spec.param_order) == set(true_params.keys())
    z_true = cl.evaluate_circuit(spec.tree, omega, true_params)

    result = eis.fit_equivalent_circuit(freq, z_true.real, z_true.imag, model=name, multistart=True)
    assert result.reduced_chi_squared < 1e-6
    for pname, true_val in true_params.items():
        assert result.params[pname] == pytest.approx(true_val, rel=0.02)


def test_two_branch_zubieta_bonert_model_recovers_true_parameters():
    """The "two-branch" supercapacitor model (Zubieta & Bonert, IEEE Trans.
    Ind. Appl. 36(1):199-205, 2000; corroborated as a standard EIS-circuit
    entry by Shen et al., J. Microelectromech. Syst. 26:949-965, 2017):
    Z = Rs + [C1 || Rleak || (R2-C2 series)] -- a fast/immediate branch
    (C1) and a slow/delayed branch (R2-C2), both in parallel with a
    leakage resistance. A physically realistic leakage resistance (kOhm-
    MOhm range, much larger than Rs/R2) must be recoverable -- this is a
    regression test for a real convergence failure found during
    self-consistency testing (Rleak's initial guess was being seeded from
    the same scale as every other resistor, leaving the optimizer unable
    to find the correct, much-larger value)."""
    freq = np.logspace(4, -3, 60)
    omega = 2 * np.pi * freq
    spec = cl.get_circuit("supercap_twobranch_CC")
    true_params = {"Rs": 50.0, "C1": 2e-4, "Rleak": 5000.0, "R2": 50.0, "C2": 2e-4}
    z_true = cl.evaluate_circuit(spec.tree, omega, true_params)

    result = eis.fit_equivalent_circuit(freq, z_true.real, z_true.imag,
                                         model="supercap_twobranch_CC", multistart=True)
    assert result.reduced_chi_squared < 1e-6
    for name, true_val in true_params.items():
        assert result.params[name] == pytest.approx(true_val, rel=0.01)


def test_two_branch_model_all_cpe_variants_registered():
    for c1 in ("C", "Q"):
        for c2 in ("C", "Q"):
            name = f"supercap_twobranch_{c1}{c2}"
            spec = cl.get_circuit(name)
            assert spec.category == "Supercapacitor (recommended)"


def test_three_branch_model_recovers_true_parameters():
    """Three-branch supercapacitor model (Zubieta-Bonert two-branch
    extended with a third, slower RC branch -- Buller et al., IEEE Trans.
    Ind. Appl. 38(6), 2002): Z = Rs + [C1 || Rleak || (R2-C2) || (R3-C3)].
    A physically realistic ordering (R2 << R3, C2 vs C3 giving a slower
    third time constant) must be recoverable from noise-free synthetic
    data, same self-consistency standard as every other preset here."""
    freq = np.logspace(4, -4, 70)
    omega = 2 * np.pi * freq
    spec = cl.get_circuit("supercap_threebranch_C")
    true_params = {"Rs": 30.0, "C1": 1e-3, "Rleak": 8000.0, "R2": 20.0, "C2": 5e-3, "R3": 100.0, "C3": 5e-2}
    z_true = cl.evaluate_circuit(spec.tree, omega, true_params)

    result = eis.fit_equivalent_circuit(freq, z_true.real, z_true.imag,
                                         model="supercap_threebranch_C", multistart=True)
    assert result.reduced_chi_squared < 1e-6
    for name, true_val in true_params.items():
        assert result.params[name] == pytest.approx(true_val, rel=0.02)


def test_charge_transfer_diffusion_and_leakage_model_recovers_true_parameters():
    """Combined charge-transfer + bounded-diffusion + self-discharge model
    (this library's own H/H2 conventions combined): Z = Rs + [(Rct||Q)-Wo]
    || Rleak."""
    freq = np.logspace(4, -3, 70)
    omega = 2 * np.pi * freq
    spec = cl.get_circuit("supercap_Q_Wo_leak")
    true_params = {
        "Rs": 2.0, "Rct": 20.0, "Rct_cap_Y0": 1e-3, "Rct_cap_n": 0.9,
        "Wb_Y0": 0.05, "Wb_B": 2.0, "Rleak": 3000.0,
    }
    z_true = cl.evaluate_circuit(spec.tree, omega, true_params)

    result = eis.fit_equivalent_circuit(freq, z_true.real, z_true.imag,
                                         model="supercap_Q_Wo_leak", multistart=True)
    assert result.reduced_chi_squared < 1e-6
    for name, true_val in true_params.items():
        assert result.params[name] == pytest.approx(true_val, rel=0.02)


def test_two_stage_plus_warburg_model_recovers_true_parameters():
    """Two resolvable interfacial time constants + a bounded-diffusion
    tail (composite/hybrid electrode with two distinct interfaces):
    Z = Rs + (Rct1||Q1) + (Rct2||Q2) + Wo."""
    freq = np.logspace(4, -3, 70)
    omega = 2 * np.pi * freq
    spec = cl.get_circuit("supercap_twostage_Q_Wo")
    true_params = {
        "Rs": 1.0, "Rct1": 5.0, "Rct1_cap_Y0": 2e-3, "Rct1_cap_n": 0.95,
        "Rct2": 15.0, "Rct2_cap_Y0": 5e-4, "Rct2_cap_n": 0.85,
        "Wb_Y0": 0.03, "Wb_B": 3.0,
    }
    z_true = cl.evaluate_circuit(spec.tree, omega, true_params)

    result = eis.fit_equivalent_circuit(freq, z_true.real, z_true.imag,
                                         model="supercap_twostage_Q_Wo", multistart=True)
    assert result.reduced_chi_squared < 1e-6
    for name, true_val in true_params.items():
        assert result.params[name] == pytest.approx(true_val, rel=0.03)


def test_new_supercapacitor_families_are_registered_in_the_right_categories():
    for c1 in ("C", "Q"):
        assert cl.get_circuit(f"supercap_threebranch_{c1}").category == "Supercapacitor (recommended)"
    for cap in ("C", "Q"):
        for wb in ("Wo", "Ws"):
            assert cl.get_circuit(f"supercap_{cap}_{wb}_leak").category == "Supercapacitor (recommended)"
            assert cl.get_circuit(f"supercap_twostage_{cap}_{wb}").category == "Supercapacitor (recommended)"


def test_an34_model_recovers_biologic_own_published_fit_values():
    """supercap_an34_C_L (Z = L + Rs + [C2 || (R2-M2)]) is BioLogic's own
    worked example for full-spectrum supercapacitor EIS fitting (EC-Lab
    Application Note #34, "Supercapacitors Investigations Part II: Time
    Constant", 2010/2019) -- this test uses the ACTUAL fitted values
    BioLogic reported for a real commercial 22 F supercapacitor (not just
    a synthetic self-consistency draw), converting their Rd2/taud2
    (EC-Lab's "M" element convention: Z = Rd*coth(sqrt(taud*jw))/
    sqrt(taud*jw)) to this library's Wo parameterization (Y0, B)."""
    freq = np.logspace(5, -2, 60)  # AN34 measured 200 kHz down to 10 mHz
    omega = 2 * np.pi * freq
    spec = cl.get_circuit("supercap_an34_C_L")

    rd2, taud2 = 37.89e-3, 1.044  # BioLogic AN34's own reported values
    true_params = {
        "L": 98.45e-9, "Rs": 31.61e-3, "C2": 15.59e-3, "R2": 4.23e-3,
        "M2_B": np.sqrt(taud2), "M2_Y0": np.sqrt(taud2) / rd2,
    }
    z_true = cl.evaluate_circuit(spec.tree, omega, true_params)

    result = eis.fit_equivalent_circuit(freq, z_true.real, z_true.imag,
                                         model="supercap_an34_C_L", multistart=True)
    assert result.reduced_chi_squared < 1e-6
    for name, true_val in true_params.items():
        assert result.params[name] == pytest.approx(true_val, rel=0.01)


def test_every_circuit_evaluates_to_finite_impedance_and_has_unique_param_names():
    """Structural self-consistency sweep across the WHOLE library (not just
    a handful of hand-picked circuits): every registered circuit must (1)
    have no duplicate parameter names within itself, (2) have no other
    circuit with an identical tree (an accidental exact duplicate), and
    (3) evaluate to a finite (non-NaN, non-inf) impedance across a
    realistic frequency sweep at a plausible parameter draw. This is the
    automated version of the manual "check all 100+ circuits" audit."""
    freq = np.logspace(4, -2, 40)
    omega = 2 * np.pi * freq
    true_values = {"R": 50.0, "C": 2e-4, "L": 1e-6, "Y0": 5e-3, "n": 0.9, "B": 2.0, "tau": 0.5, "gamma": 1.0}

    seen_trees = {}
    for name, spec in cl.CIRCUITS.items():
        param_names = spec.param_order
        assert len(param_names) == len(set(param_names)), f"{name}: duplicate param names"

        tree_key = repr(spec.tree)
        assert tree_key not in seen_trees, f"{name}: identical tree to {seen_trees.get(tree_key)}"
        seen_trees[tree_key] = name

        params = {n: true_values[k] for n, k in spec.param_kinds.items()}
        z = cl.evaluate_circuit(spec.tree, omega, params)
        assert np.all(np.isfinite(z.real)) and np.all(np.isfinite(z.imag)), f"{name}: non-finite Z"


def test_supercapacitor_category_uses_bounded_warburg_not_semiinfinite():
    """The dedicated "Supercapacitor (recommended)" category holds several
    distinct standard supercapacitor topologies (the extended-Randles
    semicircle+Warburg form, and the two-branch Zubieta-Bonert form) --
    NONE of them may use the plain semi-infinite Warburg "W" (it cannot
    reproduce a supercapacitor's near-vertical low-frequency capacitive
    turn, see circuit_library.py's module docstring), though not every
    entry in the category uses a Warburg element at all (the two-branch
    model has none)."""
    supercap_specs = [s for s in cl.CIRCUITS.values() if s.category == "Supercapacitor (recommended)"]
    assert len(supercap_specs) >= 16  # 8 Warburg-based + 8 two-branch

    def element_kinds(node):
        if node[0] == "elem":
            return {node[1]}
        out = set()
        for child in node[1]:
            out |= element_kinds(child)
        return out

    spec_kinds = {spec.name: element_kinds(spec.tree) for spec in supercap_specs}
    warburg_based = [name for name, kinds in spec_kinds.items() if kinds & {"Wo", "Ws"}]
    assert len(warburg_based) >= 8
    for name, kinds in spec_kinds.items():
        assert "W" not in kinds, f"{name}: uses semi-infinite Warburg, should use Wo/Ws"


def test_multistart_recovers_true_parameters_for_a_previously_hard_case():
    """Regression test: supercap_C_Ws (semicircle + bounded Warburg) used
    to converge to a WRONG local minimum from the standard heuristic guess
    even with zero noise (confirmed not a bad-guess-only issue -- starting
    the optimizer exactly at the true parameters recovered them exactly).
    multistart=True must escape that local minimum via alternate starting
    points."""
    freq = np.logspace(4, -2, 60)
    omega = 2 * np.pi * freq
    spec = cl.get_circuit("supercap_C_Ws")
    true_params = {"Rs": 50.0, "Rct": 50.0, "Rct_cap": 2e-4, "Wb_Y0": 5e-3, "Wb_B": 2.0}
    z_true = cl.evaluate_circuit(spec.tree, omega, true_params)

    result = eis.fit_equivalent_circuit(freq, z_true.real, z_true.imag,
                                         model="supercap_C_Ws", multistart=True)
    assert result.reduced_chi_squared < 1e-6
    for name, true_val in true_params.items():
        assert result.params[name] == pytest.approx(true_val, rel=0.01)


def test_bare_rs_c_baseline_does_not_crash_multistart():
    """Regression test: a circuit with no real-axis variation to scale
    from (baseline_RC has no semicircle at all) previously made the
    data-scaled C initial guess blow past the fixed C search bounds,
    raising 'Initial guess is outside of provided bounds' instead of
    fitting."""
    freq = np.logspace(4, -2, 40)
    omega = 2 * np.pi * freq
    spec = cl.get_circuit("baseline_RC")
    z_true = cl.evaluate_circuit(spec.tree, omega, {"Rs": 10.0, "C": 1e-4})
    result = eis.fit_equivalent_circuit(freq, z_true.real, z_true.imag,
                                         model="baseline_RC", multistart=True)
    assert result.reduced_chi_squared < 1e-6


def test_semiinfinite_warburg_is_flagged_when_fit_against_a_capacitive_tail():
    """The exact user-facing symptom this was built to explain: fitting
    the plain semi-infinite Warburg "W" against data with a genuine
    low-frequency CAPACITIVE turn (which W cannot represent) should drive
    its Y0 toward the search's lower bound -- and fit_equivalent_circuit
    must say so explicitly via result.warnings, rather than silently
    reporting a tiny/strange Y0 with no explanation."""
    freq = np.logspace(4, -3, 60)
    omega = 2 * np.pi * freq
    # generate data from the CORRECT bounded-Warburg supercapacitor model
    # (near-vertical low-frequency turn), then fit the WRONG "W" model to it.
    true_spec = cl.get_circuit("supercap_Q_Wo")
    true_params = {"Rs": 20.0, "Rct": 30.0, "Rct_cap_Y0": 5e-3, "Rct_cap_n": 0.9,
                    "Wb_Y0": 5e-3, "Wb_B": 0.05}
    z_true = cl.evaluate_circuit(true_spec.tree, omega, true_params)

    _register_test_only_circuit("test_only_rs_w", _bare_rs_element("W"))
    result = eis.fit_equivalent_circuit(freq, z_true.real, z_true.imag, model="test_only_rs_w")
    assert any("lower search bound" in w for w in result.warnings)


def test_all_circuits_have_unique_names_and_nonempty_param_lists():
    names = list(cl.CIRCUITS.keys())
    assert len(names) == len(set(names))
    for spec in cl.CIRCUITS.values():
        assert len(spec.param_order) >= 1


def test_fit_recovers_known_randles_parameters():
    rng = np.random.RandomState(0)
    f = np.logspace(4, -2, 40)
    omega = 2 * np.pi * f
    spec = cl.get_circuit("randles1_C_none")
    true_params = {"Rs": 2.0, "Rct": 15.0, "Rct_cap": 5e-4}
    z_true = cl.evaluate_circuit(spec.tree, omega, true_params)
    noise = (rng.randn(len(f)) + 1j * rng.randn(len(f))) * 0.02
    z_meas = z_true + noise

    result = eis.fit_equivalent_circuit(f, z_meas.real, z_meas.imag, model="randles1_C_none")
    assert result.params["Rs"] == pytest.approx(2.0, rel=0.05)
    assert result.params["Rct"] == pytest.approx(15.0, rel=0.05)
    assert result.reduced_chi_squared < 1.0


def test_auto_fit_finds_a_near_perfect_fit_for_the_true_generating_circuit():
    """auto_fit_equivalent_circuit ranks purely by reduced chi-squared with
    no complexity penalty (documented in its own docstring: "models with
    more free parameters will often fit numerically better even when not
    physically more correct"), so a higher-parameter-count circuit CAN
    edge out the true simpler one on a particular noise draw -- that is
    expected overfitting behavior, not a bug, and this test must not
    assume literal rank-1 equality. What the engine DOES guarantee: the
    true generating circuit is found and fits the data almost perfectly
    (near-zero reduced chi-squared), and it appears in the ranked results.
    """
    rng = np.random.RandomState(1)
    f = np.logspace(4, -2, 40)
    omega = 2 * np.pi * f
    spec = cl.get_circuit("randles1_Q_none")
    true_params = {"Rs": 3.0, "Rct": 20.0, "Rct_cap_Y0": 4e-4, "Rct_cap_n": 0.88}
    z_true = cl.evaluate_circuit(spec.tree, omega, true_params)
    noise = (rng.randn(len(f)) + 1j * rng.randn(len(f))) * 0.01
    z_meas = z_true + noise

    best, attempts = eis.auto_fit_equivalent_circuit(f, z_meas.real, z_meas.imag)
    # Compare against eis.CIRCUIT_MODELS (what auto_fit_equivalent_circuit
    # actually iterates over by default -- a snapshot taken once at
    # core.eis_analysis's import time), not the live cl.CIRCUITS dict --
    # other tests in this module register a few extra test-only circuits
    # into cl.CIRCUITS after that snapshot was taken (see
    # _register_test_only_circuit above), which would make cl.CIRCUITS
    # larger than what a real auto-fit run ever actually tries.
    assert len(attempts) == len(eis.CIRCUIT_MODELS)

    true_model_result = next(r for m, r, _ in attempts if m == "randles1_Q_none")
    assert true_model_result is not None
    assert true_model_result.reduced_chi_squared < 0.01
    assert true_model_result.params["Rs"] == pytest.approx(3.0, rel=0.05)
    assert true_model_result.params["Rct"] == pytest.approx(20.0, rel=0.05)
    # the winner (whichever it is) must fit at least as well as the true model
    assert best.reduced_chi_squared <= true_model_result.reduced_chi_squared


def test_warburg_open_diverges_at_low_frequency():
    """Reflective/blocking boundary -- |Z| must grow without bound as
    omega -> 0 (capacitive-like, nothing can escape)."""
    f = np.logspace(4, -6, 40)
    omega = 2 * np.pi * f
    tree = _bare_rs_element("Wo")
    z = cl.evaluate_circuit(tree, omega, {"Rs": 1.0, "zw_Y0": 0.1, "zw_B": 5.0})
    assert abs(z[-1]) > abs(z[0]) * 100  # grows by orders of magnitude


def test_warburg_short_saturates_at_low_frequency():
    """Transmissive boundary -- Z must SATURATE to a finite resistance
    Rs + B/Y0 as omega -> 0 (species freely cross, so DC current flows)."""
    f = np.logspace(4, -6, 40)
    omega = 2 * np.pi * f
    Rs, Y0, B = 1.0, 0.1, 5.0
    tree = _bare_rs_element("Ws")
    z = cl.evaluate_circuit(tree, omega, {"Rs": Rs, "zw_Y0": Y0, "zw_B": B})
    expected_dc_resistance = Rs + B / Y0
    assert abs(z[-1]) == pytest.approx(expected_dc_resistance, rel=1e-3)


def test_transmission_line_high_frequency_limit_is_bare_cpe():
    f = np.array([1e9, 1e10])
    omega = 2 * np.pi * f
    Rs, Rp, Yt, nt = 2.0, 30.0, 1e-3, 0.9
    spec = cl.get_circuit("tlm_semiinf")
    z_tlm = cl.evaluate_circuit(spec.tree, omega, {"Rs": Rs, "TLM_Rp": Rp, "TLM_Yt": Yt, "TLM_nt": nt})
    z_cpe = Rs + 1.0 / (Yt * (1j * omega) ** nt)
    np.testing.assert_allclose(z_tlm, z_cpe, rtol=0.05)


def test_transmission_line_low_frequency_asymptote_matches_de_levie_one_third_rule():
    """The textbook de Levie result: the low-frequency Nyquist tail's
    linear extrapolation crosses the real axis at Rs + Rp/3."""
    f = np.logspace(-4, -6, 25)
    omega = 2 * np.pi * f
    Rs, Rp, Yt, nt = 2.0, 30.0, 1e-3, 0.9
    spec = cl.get_circuit("tlm_semiinf")
    z = cl.evaluate_circuit(spec.tree, omega, {"Rs": Rs, "TLM_Rp": Rp, "TLM_Yt": Yt, "TLM_nt": nt})

    a_mat = np.vstack([z.imag, np.ones_like(z.imag)]).T
    slope, intercept = np.linalg.lstsq(a_mat, z.real, rcond=None)[0]
    assert intercept == pytest.approx(Rs + Rp / 3.0, rel=1e-3)


def test_cpe_reduces_to_ideal_capacitor_when_n_equals_one():
    omega = np.array([1.0, 10.0, 100.0])
    z_q = cl.evaluate_circuit(("elem", "Q", "x"), omega, {"x_Y0": 1e-4, "x_n": 1.0})
    z_c = cl.evaluate_circuit(("elem", "C", "x"), omega, {"x": 1e-4})
    np.testing.assert_allclose(z_q, z_c, rtol=1e-9)


# ---------------------------------------------------------------- inductance removal

def test_fit_inductance_from_high_frequency_recovers_known_inductance():
    """A Randles-type circuit with a REAL series inductance large enough to
    make Im(Z) cross positive at high frequency (the physically-required
    signature of inductance -- a capacitor/CPE alone can never do this)
    should have that inductance recovered by fit_inductance_from_high_frequency,
    which restricts its fit to exactly the Im(Z) > 0 points."""
    freq = np.logspace(5, -1, 80)
    omega = 2 * np.pi * freq
    L_true = 2e-6  # 2 microhenries -- large enough to show a visible loop
    spec = cl.get_circuit("randles1_Q_none")
    z = cl.evaluate_circuit(
        spec.tree, omega,
        {"Rs": 2.0, "Rct": 50.0, "Rct_cap_Y0": 5e-4, "Rct_cap_n": 0.92},
    )
    z_im_with_L = z.imag + omega * L_true
    assert np.any(z_im_with_L > 0), "test setup should produce a visible inductive loop"

    fitted_L = eis.fit_inductance_from_high_frequency(freq, z_im_with_L)
    assert fitted_L == pytest.approx(L_true, rel=0.1)


def test_fit_inductance_from_high_frequency_raises_without_an_inductive_loop():
    """No positive Im(Z) anywhere (a pure capacitive/CPE spectrum, no stray
    inductance) must raise rather than silently returning a meaningless
    (and previously observed to be wrong-signed) number."""
    freq = np.logspace(5, -1, 80)
    omega = 2 * np.pi * freq
    spec = cl.get_circuit("randles1_Q_none")
    z = cl.evaluate_circuit(
        spec.tree, omega,
        {"Rs": 2.0, "Rct": 50.0, "Rct_cap_Y0": 5e-4, "Rct_cap_n": 0.92},
    )
    assert not np.any(z.imag > 0)
    with pytest.raises(ValueError, match="No inductive loop"):
        eis.fit_inductance_from_high_frequency(freq, z.imag)


def test_fit_inductance_ignores_an_isolated_low_frequency_noise_point():
    """A single stray Im(Z) > 0 point far from the high-frequency end
    (plausible on a noisy real spectrum near the low-frequency baseline)
    must NOT be treated as part of the inductive loop -- only a
    CONTIGUOUS run starting from the highest frequency counts. Before
    this was enforced, an isolated low-frequency positive point could
    pull into the same zero-intercept regression as the real
    high-frequency inductive points, which is what let the fitted L (and
    therefore the "corrected" curve) drift wrong even though the loop
    itself was fit from mostly-good points -- this test locks in that the
    isolated point is excluded entirely, not merely down-weighted."""
    freq = np.logspace(5, -3, 80)
    omega = 2 * np.pi * freq
    L_true = 2e-6
    spec = cl.get_circuit("randles1_Q_none")
    z = cl.evaluate_circuit(
        spec.tree, omega,
        {"Rs": 2.0, "Rct": 50.0, "Rct_cap_Y0": 5e-4, "Rct_cap_n": 0.92},
    )
    z_im = z.imag + omega * L_true

    # Inject one isolated positive "noise" point far into the low-frequency
    # tail (index near the END of a high-to-low-frequency-sorted array),
    # well away from the contiguous high-frequency inductive run.
    low_freq_idx = len(freq) - 5
    assert z_im[low_freq_idx] < 0  # sanity: genuinely part of the capacitive tail beforehand
    z_im_contaminated = z_im.copy()
    z_im_contaminated[low_freq_idx] = 0.05  # a small noise-driven positive blip

    n_clean = eis.inductive_point_count(freq, z_im)
    n_contaminated = eis.inductive_point_count(freq, z_im_contaminated)
    assert n_clean == n_contaminated  # the isolated point must not extend the counted run

    fitted_L_clean = eis.fit_inductance_from_high_frequency(freq, z_im)
    fitted_L_contaminated = eis.fit_inductance_from_high_frequency(freq, z_im_contaminated)
    assert fitted_L_contaminated == pytest.approx(fitted_L_clean)


def test_inductive_point_count_matches_the_fit():
    freq = np.logspace(5, -1, 80)
    omega = 2 * np.pi * freq
    L_true = 2e-6
    spec = cl.get_circuit("randles1_Q_none")
    z = cl.evaluate_circuit(
        spec.tree, omega,
        {"Rs": 2.0, "Rct": 50.0, "Rct_cap_Y0": 5e-4, "Rct_cap_n": 0.92},
    )
    z_im = z.imag + omega * L_true
    n = eis.inductive_point_count(freq, z_im)
    assert n >= 3
    # refitting using only the first n (highest-frequency) points by hand
    # should recover essentially the same L as the full function
    order = np.argsort(-freq)
    f_sorted, zi_sorted = freq[order], z_im[order]
    manual_omega = 2 * np.pi * f_sorted[:n]
    manual_L = np.sum(manual_omega * zi_sorted[:n]) / np.sum(manual_omega ** 2)
    assert eis.fit_inductance_from_high_frequency(freq, z_im) == pytest.approx(manual_L)


def test_remove_inductance_zeroes_out_a_pure_inductive_contribution():
    freq = np.array([1e3, 1e4, 1e5])
    omega = 2 * np.pi * freq
    L = 5e-7
    z_re = np.array([2.0, 2.0, 2.0])
    z_im_baseline = np.array([-1.0, -0.5, -0.2])
    z_im_with_L = z_im_baseline + omega * L

    re_out, im_out = eis.remove_inductance(freq, z_re, z_im_with_L, L)
    np.testing.assert_allclose(re_out, z_re)
    np.testing.assert_allclose(im_out, z_im_baseline, atol=1e-9)


def test_missing_warburg_produces_flagged_rct_overestimation():
    """Regression for a real user-reported "Rct is overestimated" bug:
    fitting a circuit with NO Warburg/diffusion element to data that has
    a genuine low-frequency diffusion tail which hasn't fully resolved
    within the measured frequency range (a truncated, realistic
    frequency sweep -- stops at 0.1 Hz, not true DC) makes Rct blow up
    to many multiples of its true value, converging to a genuine (non-
    boundary) local optimum that the existing bound-pinning warning
    cannot catch. fit_equivalent_circuit must flag this via a dedicated
    resistance-overestimation warning; the correct (Warburg-containing)
    circuit fit to the same data must NOT trigger it."""
    freq = np.logspace(5, -1, 50)  # truncated -- stops well short of true DC
    omega = 2 * np.pi * freq
    spec = cl.get_circuit("supercap_Q_Wo")
    true_params = {"Rs": 2.0, "Rct": 50.0, "Rct_cap_Y0": 5e-4, "Rct_cap_n": 0.85,
                    "Wb_Y0": 0.01, "Wb_B": 5.0}
    z = cl.evaluate_circuit(spec.tree, omega, true_params)
    rng = np.random.default_rng(3)
    noise = 0.005
    z_re_n = z.real * (1 + noise * rng.standard_normal(len(z)))
    z_im_n = z.imag * (1 + noise * rng.standard_normal(len(z)))

    bad = eis.fit_equivalent_circuit(freq, z_re_n, z_im_n, model="randles1_Q_none", multistart=True)
    assert bad.params["Rct"] > 10 * true_params["Rct"]  # confirms the failure actually reproduces
    assert any("real-axis span" in w for w in bad.warnings)

    good = eis.fit_equivalent_circuit(freq, z_re_n, z_im_n, model="supercap_Q_Wo", multistart=True)
    assert good.params["Rct"] == pytest.approx(true_params["Rct"], rel=0.05)
    assert not any("real-axis span" in w for w in good.warnings)


def test_resistance_overestimation_warning_does_not_misfire_on_legitimate_large_rct():
    """A genuinely large but well-RESOLVED Rct (the frequency range
    actually reaches low enough for the semicircle to close) must NOT
    trigger the overestimation warning -- only a resistance many
    multiples of the data's own real-axis span should."""
    freq = np.logspace(4, -4, 60)
    omega = 2 * np.pi * freq
    spec = cl.get_circuit("randles1_Q_none")
    true_params = {"Rs": 5.0, "Rct": 500.0, "Rct_cap_Y0": 2e-4, "Rct_cap_n": 0.9}
    z = cl.evaluate_circuit(spec.tree, omega, true_params)
    rng = np.random.default_rng(2)
    noise = 0.003
    z_re_n = z.real * (1 + noise * rng.standard_normal(len(z)))
    z_im_n = z.imag * (1 + noise * rng.standard_normal(len(z)))

    result = eis.fit_equivalent_circuit(freq, z_re_n, z_im_n, model="randles1_Q_none", multistart=True)
    assert result.params["Rct"] == pytest.approx(true_params["Rct"], rel=0.05)
    assert not any("real-axis span" in w for w in result.warnings)
