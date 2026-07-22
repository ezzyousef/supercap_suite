"""Functional (headless, real-widget) tests for the DRT tab UI wiring:
loading data, running the background DRT worker, and populating the
plot/results/export state -- see tests/test_drt_analysis.py for the
underlying core.drt_analysis correctness tests."""
import time

import pytest

pytest.importorskip("PySide6")

import numpy as np
import pandas as pd
from PySide6.QtWidgets import QApplication, QMessageBox

from ui.drt_tab import DrtTab


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_tab_with_synthetic_zarc_data():
    tab = DrtTab()
    rs, rct, tau_zarc, phi = 2.0, 50.0, 1e-3, 0.8
    freq = np.logspace(5, -3, 50)
    omega = 2 * np.pi * freq
    z = rs + rct / (1 + (1j * omega * tau_zarc) ** phi)
    df = pd.DataFrame({"freq": freq, "zre": z.real, "zim": z.imag})
    tab.df = df
    for combo, col in [(tab.freq_combo, "freq"), (tab.zre_combo, "zre"), (tab.zim_combo, "zim")]:
        combo.clear()
        combo.addItem("-- select --")
        combo.addItem(col)
        combo.setCurrentText(col)
    tab.zim_sign_combo.setCurrentIndex(1)  # our synthetic z.imag is already "as-measured" (negative)
    return tab, rs, rct, tau_zarc


def _run_and_wait(tab, timeout_s=30):
    tab.on_run()
    app = QApplication.instance()
    deadline = time.time() + timeout_s
    while tab._worker is not None and time.time() < deadline:
        app.processEvents()
    assert tab._worker is None, "DRT worker did not finish in time"


def test_run_populates_results_plot_and_export_state():
    tab, rs, rct, tau_zarc = _make_tab_with_synthetic_zarc_data()
    _run_and_wait(tab)

    assert tab.last_result is not None
    assert tab.last_raw_df is not None
    assert tab.export_btn.isEnabled()
    assert "DRT" in tab.plot.ax.get_title()
    assert tab.last_result["R_inf (ohmic resistance, Ω)"] == pytest.approx(rs, rel=0.05)
    assert tab.last_result["Peaks detected"] >= 1


def test_detected_peak_has_a_region_explanation_in_the_results_text():
    tab, rs, rct, tau_zarc = _make_tab_with_synthetic_zarc_data()
    _run_and_wait(tab)

    text = tab.results_text.toPlainText()
    assert "Region:" in text
    # at least one of the three standard region labels must appear
    assert any(label in text for label in ("High frequency", "Mid frequency", "Low frequency"))


def test_run_without_columns_selected_shows_no_crash_and_no_result(monkeypatch):
    # QMessageBox.warning() is a real modal dialog -- mocked out here (as
    # other tests in this suite do for QMessageBox.question) so the
    # "missing columns" warning path can be exercised headlessly instead
    # of blocking forever waiting for a click that never comes.
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))

    tab = DrtTab()
    df = pd.DataFrame({"freq": [1.0, 2.0], "zre": [1.0, 2.0], "zim": [1.0, 2.0]})
    tab.df = df
    for combo, col in [(tab.freq_combo, "freq"), (tab.zre_combo, "zre"), (tab.zim_combo, "zim")]:
        combo.clear()
        combo.addItem("-- select --")
        combo.addItem(col)
        # deliberately leave the placeholder selected, as a freshly loaded file would start
    tab.on_run()  # columns still "-- select --" -- must warn and return, not raise
    assert tab.last_result is None


def test_inductive_loop_checkbox_actually_crops_points_before_drt_runs():
    tab, rs, rct, tau_zarc = _make_tab_with_synthetic_zarc_data()
    # Inject an inductive loop (Im(Z) > 0) at the highest frequencies into
    # the loaded dataframe, then confirm enabling the checkbox changes the
    # arrays _get_eis_arrays() returns (proving the crop is actually wired
    # into the DRT tab's data path, not just present as an inert checkbox).
    df = tab.df.copy()
    df.loc[df["freq"].nlargest(3).index, "zim"] = 5.0
    tab.df = df

    tab.inductance_checkbox.setChecked(False)
    freq_raw, _, _ = tab._get_eis_arrays()
    tab.inductance_checkbox.setChecked(True)
    freq_cropped, _, _ = tab._get_eis_arrays()

    assert len(freq_cropped) < len(freq_raw)


def test_loading_a_file_auto_detects_frequency_and_z_columns(tmp_path):
    freq = np.logspace(4, -2, 30)
    omega = 2 * np.pi * freq
    z = 2.0 + 50.0 / (1 + 1j * omega * 1e-3)
    df = pd.DataFrame({"freq/Hz": freq, "z_re/ohm": z.real, "-z_im/ohm": -z.imag})
    csv_path = tmp_path / "auto_detect.csv"
    df.to_csv(csv_path, index=False)

    tab = DrtTab()
    tab._load_dataframe(str(csv_path), sheet_name=0)

    assert tab.freq_combo.currentText() != "-- select --"
    assert tab.zre_combo.currentText() != "-- select --"
    assert tab.zim_combo.currentText() != "-- select --"
    assert tab.zim_sign_combo.currentIndex() == 0  # "-z_im" column name should select the "-Im(Z)" convention


def test_loading_a_file_with_a_cycle_column_populates_cycle_selection(tmp_path):
    freq = np.logspace(4, -2, 20)
    omega = 2 * np.pi * freq
    rows = []
    for cyc, rct in [(1, 50.0), (2, 60.0)]:
        z = 2.0 + rct / (1 + 1j * omega * 1e-3)
        for f, zre, zim in zip(freq, z.real, z.imag):
            rows.append({"cycle number": cyc, "freq": f, "zre": zre, "zim": zim})
    df = pd.DataFrame(rows)
    csv_path = tmp_path / "cycles.csv"
    df.to_csv(csv_path, index=False)

    tab = DrtTab()
    tab._load_dataframe(str(csv_path), sheet_name=0)

    assert tab.cycle_col_combo.currentText() == "cycle number"
    assert tab.cycle_value_combo.count() == 3  # "-- all rows --" + 2 distinct cycles

    tab.zre_combo.setCurrentText("zre")
    tab.zim_combo.setCurrentText("zim")
    tab.freq_combo.setCurrentText("freq")
    tab.zim_sign_combo.setCurrentIndex(1)

    tab.cycle_value_combo.setCurrentIndex(1)
    freq_c1, zre_c1, _ = tab._get_eis_arrays()
    tab.cycle_value_combo.setCurrentIndex(2)
    freq_c2, zre_c2, _ = tab._get_eis_arrays()

    assert len(freq_c1) == 20 and len(freq_c2) == 20
    assert not np.allclose(zre_c1, zre_c2)  # different Rct per cycle -> genuinely different data selected


def test_running_drt_on_one_cycle_uses_only_that_cycles_data():
    freq = np.logspace(4, -2, 20)
    omega = 2 * np.pi * freq
    rows = []
    for cyc, rct in [(1, 50.0), (2, 60.0)]:
        z = 2.0 + rct / (1 + 1j * omega * 1e-3)
        for f, zre, zim in zip(freq, z.real, z.imag):
            rows.append({"cycle number": cyc, "freq": f, "zre": zre, "zim": zim})
    df = pd.DataFrame(rows)

    tab = DrtTab()
    tab.df = df
    tab.cycle_col_combo.clear()
    tab.cycle_col_combo.addItem("-- none / single spectrum --")
    tab.cycle_col_combo.addItem("cycle number")
    tab.cycle_col_combo.setCurrentText("cycle number")  # triggers _on_cycle_column_changed
    for combo, col in [(tab.freq_combo, "freq"), (tab.zre_combo, "zre"), (tab.zim_combo, "zim")]:
        combo.clear()
        combo.addItem("-- select --")
        combo.addItem(col)
        combo.setCurrentText(col)
    tab.zim_sign_combo.setCurrentIndex(1)
    tab.cycle_value_combo.setCurrentIndex(1)  # Cycle 1 only

    freq_sel, zre_sel, _ = tab._get_eis_arrays()
    assert len(freq_sel) == 20  # not 40 -- the other cycle's rows are excluded


def test_dct_method_selection_runs_dct_and_populates_dct_specific_results():
    tab = DrtTab()
    g_inf, gct, tau_yarc, phi = 0.05, 0.2, 1e-3, 0.8
    freq = np.logspace(4, -3, 60)
    omega = 2 * np.pi * freq
    y = g_inf + gct / (1 + (1j * omega * tau_yarc) ** phi)
    z = 1.0 / y
    df = pd.DataFrame({"freq": freq, "zre": z.real, "zim": z.imag})
    tab.df = df
    for combo, col in [(tab.freq_combo, "freq"), (tab.zre_combo, "zre"), (tab.zim_combo, "zim")]:
        combo.clear()
        combo.addItem("-- select --")
        combo.addItem(col)
        combo.setCurrentText(col)
    tab.zim_sign_combo.setCurrentIndex(1)
    tab.method_combo.setCurrentIndex(tab.method_combo.findData("dct"))

    _run_and_wait(tab)

    assert "DCT" in tab.plot.ax.get_title()
    assert tab.last_result is not None
    assert tab.last_result["G0, zero-frequency conductance (S)"] == pytest.approx(g_inf, rel=0.2)
    assert "C0, instantaneous capacitance (F)" in tab.last_result
    assert tab.export_btn.isEnabled()
    assert "graph_y_gamma_s" in tab.last_raw_df.columns


def test_drt_method_is_the_default_selection():
    tab = DrtTab()
    assert tab.method_combo.currentData() == "drt"
