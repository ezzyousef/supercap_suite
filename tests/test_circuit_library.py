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
    assert len(cl.CIRCUITS) >= 100


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
