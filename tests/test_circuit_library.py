"""Ground-truth tests for core.circuit_library's element formulas and the
generic CNLS fitting engine (core.eis_analysis), including the physical
asymptotic-limit checks used to verify the Warburg-open/short and
transmission-line conventions before they were finalized (see the module
docstring in circuit_library.py for the reasoning)."""
import numpy as np
import pytest

from core import circuit_library as cl
from core import eis_analysis as eis


def test_library_has_over_100_circuits():
    assert len(cl.CIRCUITS) >= 110


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
    true_values = {"R": 50.0, "C": 2e-4, "L": 1e-6, "Y0": 5e-3, "n": 0.9, "B": 2.0, "tau": 0.5}

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

    result = eis.fit_equivalent_circuit(freq, z_true.real, z_true.imag, model="misc_R_W")
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
    assert len(attempts) == len(cl.CIRCUITS)

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
    spec = cl.get_circuit("misc_R_Wo")
    z = cl.evaluate_circuit(spec.tree, omega, {"Rs": 1.0, "zw_Y0": 0.1, "zw_B": 5.0})
    assert abs(z[-1]) > abs(z[0]) * 100  # grows by orders of magnitude


def test_warburg_short_saturates_at_low_frequency():
    """Transmissive boundary -- Z must SATURATE to a finite resistance
    Rs + B/Y0 as omega -> 0 (species freely cross, so DC current flows)."""
    f = np.logspace(4, -6, 40)
    omega = 2 * np.pi * f
    Rs, Y0, B = 1.0, 0.1, 5.0
    spec = cl.get_circuit("misc_R_Ws")
    z = cl.evaluate_circuit(spec.tree, omega, {"Rs": Rs, "zw_Y0": Y0, "zw_B": B})
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
