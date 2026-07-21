"""Tests for the EIS tab's Bode plot view (|Z| & phase vs. frequency),
the standard alternative to the Nyquist plot offered by every commercial
EIS tool. Also covers the twin-axis cleanup this required: the Bode view
uses a matplotlib twinx() secondary y-axis for phase, which ax.clear()
does not remove on its own -- every other draw path on the same plot
(Nyquist preview, circuit-fit overlay, Clear results) must tear it down
first or a stale phase axis/label would linger behind the next plot."""
import time

import pytest

pytest.importorskip("PySide6")

import numpy as np
import pandas as pd
from PySide6.QtWidgets import QApplication

from ui.eis_tab import EisTab
from core import circuit_library as cl


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_tab_with_synthetic_data():
    tab = EisTab()
    freq = np.logspace(4, -2, 40)
    omega = 2 * np.pi * freq
    spec = cl.get_circuit("randles1_C_none")
    z = cl.evaluate_circuit(spec.tree, omega, {"Rs": 2.0, "Rct": 50.0, "Rct_cap": 1e-5})
    df = pd.DataFrame({"freq": freq, "zre": z.real, "zim": z.imag})
    tab.df = df
    tab.table_model.set_dataframe(df)
    for combo, col in [(tab.freq_combo, "freq"), (tab.zre_combo, "zre"), (tab.zim_combo, "zim")]:
        combo.clear()
        combo.addItem("-- select --")
        combo.addItem(col)
        combo.setCurrentText(col)
    tab.zim_sign_combo.setCurrentIndex(1)  # our synthetic z.imag is already "as-measured" (negative)
    return tab


def test_preview_defaults_to_nyquist():
    tab = _make_tab_with_synthetic_data()
    tab.on_preview()
    assert tab.plot.ax.get_title() == "Nyquist plot"
    assert tab._bode_twin_ax is None
    assert len(tab.plot.fig.axes) == 1


def test_bode_checkbox_switches_to_a_log_log_bode_plot_with_a_phase_twin_axis():
    tab = _make_tab_with_synthetic_data()
    tab.on_preview()
    tab.bode_checkbox.setChecked(True)
    assert tab.plot.ax.get_title() == "Bode plot"
    assert tab.plot.ax.get_xscale() == "log"
    assert tab.plot.ax.get_yscale() == "log"
    assert tab._bode_twin_ax is not None
    assert len(tab.plot.fig.axes) == 2


def test_unchecking_bode_returns_to_nyquist_and_removes_the_twin_axis():
    tab = _make_tab_with_synthetic_data()
    tab.on_preview()
    tab.bode_checkbox.setChecked(True)
    assert len(tab.plot.fig.axes) == 2

    tab.bode_checkbox.setChecked(False)
    assert tab.plot.ax.get_title() == "Nyquist plot"
    assert tab._bode_twin_ax is None
    assert len(tab.plot.fig.axes) == 1


def test_running_a_circuit_fit_while_on_bode_view_cleans_up_the_twin_axis():
    tab = _make_tab_with_synthetic_data()
    tab.on_preview()
    tab.bode_checkbox.setChecked(True)
    assert tab._bode_twin_ax is not None

    tab._select_circuit("randles1_C_none")
    tab.on_fit()
    deadline = time.time() + 20
    app = QApplication.instance()
    while tab._fit_worker is not None and time.time() < deadline:
        app.processEvents()
    assert tab._fit_worker is None, "fit worker did not finish in time"

    assert tab._bode_twin_ax is None
    assert len(tab.plot.fig.axes) == 1
    assert "circuit fit" in tab.plot.ax.get_title()


def test_clear_results_cleans_up_the_bode_twin_axis():
    tab = _make_tab_with_synthetic_data()
    tab.on_preview()
    tab.bode_checkbox.setChecked(True)
    assert tab._bode_twin_ax is not None

    tab.on_clear_results()
    assert tab._bode_twin_ax is None
    assert len(tab.plot.fig.axes) == 1


def test_bode_toggle_without_loaded_data_does_not_raise():
    tab = EisTab()
    tab.bode_checkbox.setChecked(True)  # no df loaded yet -- must be a silent no-op, not an error
    assert tab._bode_twin_ax is None


def test_kramers_kronig_plots_residuals_and_cleans_up_a_prior_bode_twin_axis():
    tab = _make_tab_with_synthetic_data()
    tab.on_preview()
    tab.bode_checkbox.setChecked(True)
    assert tab._bode_twin_ax is not None

    tab.on_kramers_kronig()
    assert "Kramers-Kronig residuals" in tab.plot.ax.get_title()
    assert tab.plot.ax.get_xscale() == "log"
    assert tab._bode_twin_ax is None
    assert len(tab.plot.fig.axes) == 1
