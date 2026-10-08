"""Regression tests for the findings of the independent science review (docs/REVIEW_LOG.md)."""
import numpy as np
import pytest

from core import circuit_library as cl
from core import cv_analysis as cv
from core import eis_analysis as eis
from core import gcd_analysis as gcd


def _discharge(c_f=0.5, i_a=0.01, r_ohm=2.0, v_top=1.0, v_bottom=0.2, reversal=True):
    t = np.linspace(0, 200, 4001)
    step = (2 if reversal else 1) * i_a * r_ohm
    v = v_top - step - i_a * t / c_f
    t = np.concatenate([[0.0], t + 0.05])
    v = np.concatenate([[v_top], v])
    keep = v >= v_bottom
    return t[keep], v[keep]


def test_integral_capacitance_does_not_depend_on_where_the_window_ends():
    t = np.linspace(0, 100, 2001)
    for v_end in (0.0, 0.5, -1.0):              # e.g. a three-electrode window vs. a reference
        v = (v_end + 1.0) - t / 100.0           # 1 V linear discharge, C = I*dt/dV = 0.01*100/1
        assert gcd.total_capacitance_gcd_integral(t, v, 0.01) == pytest.approx(1.0, rel=1e-6)


def test_ir_drop_is_excluded_from_the_voltage_window():
    t, v = _discharge()
    r = gcd.total_capacitance_gcd_auto(t, v, 0.01)
    assert r["capacitance_f"] == pytest.approx(0.5, rel=1e-3)
    assert r["ir_drop_excluded_v"] == pytest.approx(0.04, rel=1e-3)
    kept = gcd.total_capacitance_gcd_auto(t, v, 0.01, exclude_ir_drop=False)
    assert kept["voltage_window_v"] > r["voltage_window_v"]


def test_esr_convention_for_a_current_reversal():
    t, v = _discharge(reversal=True)
    drop = gcd.estimate_ir_drop(t, v)
    assert gcd.esr_from_ir_drop(drop, 0.01, current_reverses=True) == pytest.approx(2.0, rel=1e-3)
    t, v = _discharge(reversal=False)
    drop = gcd.estimate_ir_drop(t, v)
    assert gcd.esr_from_ir_drop(drop, 0.01) == pytest.approx(2.0, rel=1e-3)


def test_cv_cycle_counter_sees_stacked_cycles():
    one = np.concatenate([np.linspace(0, 1, 100), np.linspace(1, 0, 100)[1:]])
    rng = np.random.default_rng(0)
    for n in (1, 2, 3):
        v = np.tile(one, n) + rng.normal(0, 0.003, one.size * n)
        assert cv.count_cycles(v) == pytest.approx(n, abs=0.25)


def test_classic_randles_is_in_the_library_and_recovers_its_parameters():
    spec = cl.get_circuit("randles_classic_C_W")
    f = np.logspace(5, -2, 60)
    true = {"Rs": 1.0, "Cdl": 2e-5, "Rct": 40.0, "Zw_Y0": 0.02}
    assert set(true) == set(spec.param_order)
    z = cl.evaluate_circuit(spec.tree, 2 * np.pi * f, true)
    fit = eis.fit_equivalent_circuit(f, z.real, z.imag, model="randles_classic_C_W", multistart=True)
    for k, val in true.items():
        assert fit.params[k] == pytest.approx(val, rel=0.02)


def test_a_large_device_capacitance_is_not_pinned_at_ten_farads():
    f = np.logspace(3, -2, 40)
    z = 0.02 + 1 / (1j * 2 * np.pi * f * 300.0)            # a 300 F cell
    fit = eis.fit_equivalent_circuit(f, z.real, z.imag, model="baseline_RC")
    assert fit.params["C"] == pytest.approx(300.0, rel=0.01)
    assert not any("upper search bound" in w for w in fit.warnings)


def test_modulus_weighting_reports_a_unit_free_residual():
    spec = cl.get_circuit("randles1_C_none")
    f = np.logspace(5, -1, 40)
    true = {"Rs": 2.0, "Rct": 50.0, "Rct_cap": 1e-5}
    z = cl.evaluate_circuit(spec.tree, 2 * np.pi * f, true)
    rng = np.random.default_rng(0)
    zn = z * (1 + 0.01 * rng.standard_normal(z.size))
    a = eis.fit_equivalent_circuit(f, zn.real, zn.imag, model="randles1_C_none")
    b = eis.fit_equivalent_circuit(f, zn.real * 1000, zn.imag * 1000, model="randles1_C_none")
    assert a.rel_rms_percent == pytest.approx(b.rel_rms_percent, rel=1e-3)   # mΩ vs kΩ: same
    assert a.rel_rms_percent < 2.0
    assert np.isfinite(a.aicc)


def test_kramers_kronig_accepts_a_valid_supercapacitor_spectrum():
    f = np.logspace(5, -2, 60)
    w = 2 * np.pi * f
    z = 0.5 + 1 / (1 / 2.0 + 1j * w * 1e-3) + 1 / (1j * w * 0.5)   # with a capacitive tail
    rng = np.random.default_rng(1)
    zn = z * (1 + 0.002 * rng.standard_normal(f.size))
    r = eis.kramers_kronig_test(f, zn.real, zn.imag)
    assert r.passed and r.max_residual_percent < 1.0
    assert r.series_capacitance_f == pytest.approx(0.5, rel=0.02)


def test_appending_rows_keeps_the_header_under_a_source_note(tmp_path):
    import pandas as pd
    from core import export_io

    path = tmp_path / "log.xlsx"
    first = pd.DataFrame({"File": ["a"], "C (F/g)": [100.0]})
    sheet = export_io.export_table(str(path), "Log", first, source_note="GCD — test suite")
    export_io.append_table_rows(str(path), sheet, pd.DataFrame({"File": ["b"], "C (F/g)": [110.0]}))
    back = pd.read_excel(path, sheet_name=sheet, header=2)
    assert list(back.columns) == ["File", "C (F/g)"]
    assert back["File"].tolist() == ["a", "b"]
    note = pd.read_excel(path, sheet_name=sheet, header=None).iloc[0, 0]
    assert note == "GCD — test suite"


def test_dsc_heat_flow_units():
    from core import dsc_analysis as dsc
    assert dsc.guess_heat_flow_unit("Heat Flow (W/g)") == "W/g (normalised)"
    assert dsc.guess_heat_flow_unit("Heat flow/mW") == "mW"
    assert dsc.heat_flow_to_mw([1.0], "W")[0] == pytest.approx(1000.0)
    assert dsc.heat_flow_to_mw([0.5], "W/g (normalised)", 0.010)[0] == pytest.approx(5.0)
    with pytest.raises(ValueError):
        dsc.heat_flow_to_mw([0.5], "W/g (normalised)", None)


def test_european_semicolon_csv_reads_numbers(tmp_path):
    from core import data_io
    path = tmp_path / "eu.csv"
    path.write_text("time/s;Ewe/V;<I>/mA\n0,0;0,10;1,5\n1,0;0,20;1,5\n\n2,0;0,30;1,5\n", encoding="utf-8")
    df = data_io.load_data_file(str(path))
    assert list(df.columns) == ["time/s", "Ewe/V", "<I>/mA"]
    assert df["Ewe/V"].tolist() == pytest.approx([0.1, 0.2, 0.3])
    assert len(df) == 3
